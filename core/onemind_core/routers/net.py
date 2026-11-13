# SPDX-License-Identifier: Apache-2.0
"""Networking in the gateway (CORE-NET-12): fabric joins (§12.11), the mesh view, the box CA
(§12.7), forward-auth, and the app proxy for <app>.<box>.local (NETWORKING.md §9).

One registry line in app.py. What it registers:
- the `node.join` action handler (fabric.py) and its background loop;
- the app reverse proxy as an ASGI middleware (proxy.py: sign-in first, then the app's access);
- the mDNS publisher for onemind.local and the app names, when ONEMIND_NET_MDNS=1 (lan.py);
- routes under /v1/fabric, /v1/mesh, /v1/tls and /v1/auth.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

from fastapi import Body, Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse

from ..auth import Principal
from ..ca import BoxCA, box_name_from_hostname
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..fabric import FabricDeps, FabricService, JoinRequestBody, K3sBootstrapTokens, TicketRequest
from ..lan import AvahiPublisher, desired_names
from ..mesh import TAG_HUB, HeadscaleClient, HeadscaleError, MeshService, tls_transport
from ..netconf import FabricSettings, MeshSettings, NetSettings
from ..proxy import SESSION_COOKIE, AppProxy, AppProxyMiddleware, KubectlServiceResolver, token_session_resolver

log = logging.getLogger("onemind.net")

TICK_S = 5.0
LAN_SYNC_S = 10.0
APP_COOKIE_MAX_AGE = 12 * 3600


def _source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _is_loopback(request: Request) -> bool:
    try:
        return ipaddress.ip_address(_source(request)).is_loopback
    except ValueError:
        return False


def web_apps(gw: Gateway) -> list[str]:
    """Installed apps with a web port: the ones that get names and links."""
    states = gw.repo.list_app_states()
    out = []
    for app_id, entry in gw.catalog.load().items():
        st = states.get(app_id)
        web = (entry.manifest.get("spec") or {}).get("web")
        if st and st.status == "installed" and isinstance(web, dict) and isinstance(web.get("port"), int):
            out.append(app_id)
    return sorted(out)


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    net = settings.section(NetSettings)
    mesh_cfg = settings.section(MeshSettings)
    fab_cfg = settings.section(FabricSettings)
    box = net.box()
    box_ca = BoxCA(net.tls_dir or settings.audit_path.parent / "tls", box, clock=gw.clock)
    mesh: MeshService | None = None
    if mesh_cfg.enabled:
        assert mesh_cfg.headscale_key_file is not None  # MeshSettings.validate
        extra = {}
        if mesh_cfg.headscale_url.startswith("https:"):  # Headscale's own TLS, verified with the box CA
            extra["transport"] = tls_transport(box_ca.dir / "ca.crt", urlsplit(mesh_cfg.control_url).hostname or "")
        mesh = MeshService(HeadscaleClient.from_key_file(mesh_cfg.headscale_url, mesh_cfg.headscale_key_file, **extra),
                           gw.audit, gw.clock)
    fabric = FabricService(FabricDeps(
        actions=gw.actions, audit=gw.audit, events=gw.events, registry=gw.registry, db=gw.db, clock=gw.clock,
        box_ca=box_ca, net=net, mesh_settings=mesh_cfg, fabric=fab_cfg, mesh=mesh,
        k3s=K3sBootstrapTokens(settings.kubectl, fab_cfg.k3s_ca_hash) if fab_cfg.k3s else None,
        hub_node_id=settings.node_id,
    ))
    gw.actions.register_handler("node.join", fabric)

    # ---- the app proxy: <app>.<box>.local, <app>.onemind.local, <app>.apps.onemind.internal ----------
    proxy = AppProxy(
        gw.catalog, lambda i: (st := gw.repo.get_app_state(i)) and st.status,
        token_session_resolver(gw.tokens), KubectlServiceResolver(settings.kubectl),
        box_domains=net.box_domains(), audit=gw.audit.append, path_routes=net.path_routes,
    )
    app.add_middleware(AppProxyMiddleware, proxy=proxy)

    # ---- background work ----------------------------------------------------------------------------
    tasks: list[asyncio.Task] = []
    publisher: AvahiPublisher | None = None

    async def fabric_loop() -> None:
        while True:
            try:
                await asyncio.to_thread(fabric.tick)
            except Exception:
                log.exception("fabric tick failed")
            await asyncio.sleep(TICK_S)

    async def lan_loop() -> None:
        assert publisher is not None
        hostname = box_name_from_hostname(socket.gethostname())
        while True:
            try:
                names = desired_names(box, web_apps(gw), hostname_label=hostname)
                await asyncio.to_thread(publisher.sync, names)
            except Exception:
                log.exception("mDNS sync failed")
            await asyncio.sleep(LAN_SYNC_S)

    def conflict(name: str) -> None:
        gw.events.publish_event("lan", "name_conflict", {"name": name, "fallback": f"{box}.local"},
                                severity="warning", dedupe_key=f"lan:{name}")

    def push_policy() -> None:
        """The mesh access rules from OneMind roles (NETWORKING §6). lan mode has no people's devices
        yet, so only the machine grants; a rejected policy leaves the old one in force (audited)."""
        assert mesh is not None
        try:
            digest = mesh.push_policy([])
            log.info("mesh policy applied (%s)", digest[:12])
        except Exception as exc:
            log.warning("mesh policy not applied: %s", exc)

    def start() -> None:
        nonlocal publisher
        fabric.reconcile()
        tasks.append(asyncio.ensure_future(fabric_loop()))
        if mesh is not None:
            tasks.append(asyncio.ensure_future(asyncio.to_thread(push_policy)))
        if net.mdns and net.lan_addr:
            publisher = AvahiPublisher(net.lan_addr, on_conflict=conflict)
            tasks.append(asyncio.ensure_future(lan_loop()))

    async def stop() -> None:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        if publisher is not None:
            publisher.stop_all()

    gw.on_startup(start)
    gw.on_shutdown(stop)
    principal = gw.principal

    # ---- fabric (§12.11) ------------------------------------------------------------------------------
    @app.post("/v1/fabric/join-tickets", operation_id="fabric.ticket_create", tags=["fabric"], status_code=201, responses=error_responses(401, 403, 422))
    def create_ticket(body: TicketRequest = Body(default_factory=TicketRequest), p: Principal = Depends(principal)):
        return fabric.create_ticket(p, body)

    @app.get("/v1/fabric/join-tickets", operation_id="fabric.ticket_list", tags=["fabric"], responses=error_responses(401, 403))
    def list_tickets(p: Principal = Depends(principal)):
        return fabric.list_tickets(p)

    @app.delete("/v1/fabric/join-tickets/{ticket_id}", operation_id="fabric.ticket_revoke", tags=["fabric"], status_code=204,
                responses=error_responses(401, 403, 404, 409))
    def revoke_ticket(ticket_id: str, p: Principal = Depends(principal)):
        fabric.revoke_ticket(p, ticket_id)
        return Response(status_code=204)

    @app.post("/v1/fabric/join-requests", operation_id="fabric.join_request", tags=["fabric"], status_code=202,
              responses=error_responses(401, 409, 422, 429))
    def create_join_request(body: JoinRequestBody, request: Request):
        """No session: the one-time join code authenticates. Files node.join and nothing else."""
        out = fabric.create_request(_source(request), body)
        return JSONResponse(status_code=202, content=out, headers={"Location": out["poll"]})

    @app.get("/v1/fabric/join-requests/{request_id}", operation_id="fabric.join_status", tags=["fabric"], responses=error_responses(401, 404, 429, 503))
    def poll_join_request(request_id: str, request: Request,
                          onemind_join_code: str = Header(default=""), onemind_join_proof: str = Header(default="")):
        """The joining node polls with its code and a signature by its own key; credentials come once."""
        out = fabric.poll(_source(request), request_id, onemind_join_code, onemind_join_proof)
        return JSONResponse(content=out, headers={"Cache-Control": "no-store"})

    @app.get("/v1/fabric", operation_id="fabric.get", tags=["fabric"], responses=error_responses(401))
    def fabric_summary(_: Principal = Depends(principal)):
        return fabric.summary()

    # ---- box CA and HTTPS (§12.7) -----------------------------------------------------------------------
    @app.get("/v1/tls", operation_id="tls.get", tags=["tls"], responses=error_responses(401))
    def tls_info(_: Principal = Depends(principal)):
        cert = box_ca.ensure_https_cert() if net.tls else None
        return {"ca_sha256": box_ca.ca_fingerprint(), "names": list(box_ca.https_names()),
                "not_after": cert.not_after.isoformat().replace("+00:00", "Z") if cert else None,
                "https": net.tls, "acme": None}

    @app.get("/v1/tls/ca.crt", operation_id="tls.ca", tags=["tls"])
    def ca_cert(format: str = "der"):
        """Open, like /healthz: a phone or a joining node needs the CA before it can sign in. It is
        public data; clients pin it by the sha256 shown in the pairing QR."""
        if format == "pem":
            return Response(box_ca.ca_pem(), media_type="application/x-pem-file")
        return Response(box_ca.ca_der(), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": f'attachment; filename="onemind-{box}-ca.crt"'})

    # ---- mesh view (NETWORKING §15, proposed §12.16) ----------------------------------------------------
    @app.get("/v1/mesh", operation_id="mesh.get", tags=["mesh"], responses=error_responses(401))
    def mesh_view(addresses: bool = False, p: Principal = Depends(principal)):
        show_ips = addresses and p.is_owner  # owner-only toggle, never the default (contract §2)
        scheme = "https" if net.tls else "http"
        apps = [{"app_id": a, "lan": f"{scheme}://{a}.{box}.local", "lan_alias": f"{scheme}://{a}.onemind.local",
                 "mesh": f"{scheme}://{a}.apps.onemind.internal"} for a in web_apps(gw)]
        out: dict = {
            "mode": "lan" if mesh_cfg.enabled else "off", "box": box,
            "control": {"state": "off", "checked_at": None},
            "relay": None, "nodes": [], "devices": [],
            "names": {"lan": ["onemind.local", f"{box}.local"], "mesh": ["hub.onemind.internal"] if mesh_cfg.enabled else []},
            "apps": apps, "https": net.tls, "ca_sha256": box_ca.ca_fingerprint(),
        }
        if mesh is None:
            return out
        checked = gw.clock().isoformat().replace("+00:00", "Z")
        try:
            hs_nodes = mesh.client.list_nodes()
            out["control"] = {"state": "up", "checked_at": checked}
        except HeadscaleError:
            out["control"] = {"state": "down", "checked_at": checked}
            return out
        for n in hs_nodes:
            node_id = n.name[5:] if n.name.startswith("node-") else None
            if TAG_HUB in n.tags:
                node_id = settings.node_id
            if not n.tags:  # people's devices: user-owned, never tagged
                out["devices"].append({"id": n.id, "label": n.name, "online": n.online,
                                       **({"mesh_ip": (n.ip_addresses or [None])[0]} if show_ips else {})})
                continue
            hb = gw.registry.get(node_id) if node_id else None
            hb_mesh = (hb or {}).get("mesh") or {}
            role = "hub" if TAG_HUB in n.tags else ("leaf" if "tag:onemind-leaf" in n.tags else "worker")
            out["nodes"].append({
                "node_id": node_id, "name": n.name, "role": role, "online": n.online,
                "state": hb_mesh.get("state", "up" if n.online else "down"),
                "path": hb_mesh.get("path", "none"),
                **({"mesh_ip": (n.ip_addresses or [None])[0]} if show_ips else {}),
            })
        return out

    # ---- forward-auth for an edge in front of the gateway (§9.3) ---------------------------------------
    @app.get("/v1/auth/forward", operation_id="auth.forward", tags=["auth"], status_code=204, responses=error_responses(401, 403, 404))
    def forward_auth(request: Request, x_forwarded_host: str = Header(default="")):
        """Loopback only. The same decision the in-gateway proxy makes: sign-in first, then access."""
        if not _is_loopback(request):
            raise ApiError(404, "not_found", "no such resource")
        host = x_forwarded_host.split(":", 1)[0].lower()
        matched = proxy.match({"type": "http", "headers": [(b"host", host.encode())], "path": "/"})
        if matched is None:
            raise ApiError(404, "not_found", "not an app host")
        headers = {k.lower(): v for k, v in request.headers.items()}
        status, who, _route = proxy.decide(headers, matched[0])
        if status == 204 and who is not None:
            return Response(status_code=204, headers={"X-OneMind-Principal": f"person:{who.id}", "X-OneMind-Role": who.role})
        code = {401: "unauthenticated", 403: "permission_denied", 404: "not_found"}[status]
        raise ApiError(status, code, {401: "sign in first", 403: "no access to this app", 404: "no such app"}[status])

    # ---- the app-host session cookie (v0 bridge until CORE-SEC sessions) --------------------------------
    def _cookie_domain(request: Request) -> str | None:
        host = (request.headers.get("host") or "").split(":", 1)[0].lower()
        for d in net.box_domains():
            if host == d or host.endswith("." + d):
                return d
        return None

    @app.post("/v1/auth/app-session", operation_id="auth.app_session_set", tags=["auth"], status_code=204, responses=error_responses(401, 403))
    def app_session(request: Request, p: Principal = Depends(principal)):
        """Set the HttpOnly cookie app hosts accept, for the box domain this request came in on.

        Bearer-only (a cookie cannot call it), so a cross-site page cannot plant a session. The proxy
        strips this cookie before a request reaches an app (proxy.py).
        """
        if p.kind != "person":
            raise ApiError(403, "permission_denied", "only people open apps")
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        resp = Response(status_code=204)
        resp.set_cookie(SESSION_COOKIE, token.strip(), max_age=APP_COOKIE_MAX_AGE, path="/",
                        domain=_cookie_domain(request), secure=True, httponly=True, samesite="lax")
        gw.audit.append("auth.app_session.set", p.as_dict(), None, {"domain": _cookie_domain(request)})
        return resp

    @app.delete("/v1/auth/app-session", operation_id="auth.app_session_clear", tags=["auth"], status_code=204)
    def app_session_clear(request: Request):
        resp = Response(status_code=204)
        resp.delete_cookie(SESSION_COOKIE, path="/", domain=_cookie_domain(request), secure=True, httponly=True,
                           samesite="lax")
        return resp
