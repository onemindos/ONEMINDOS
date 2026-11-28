# SPDX-License-Identifier: Apache-2.0
"""Networking in the gateway (CORE-NET-12): fabric joins (§12.11), the mesh view, the box CA
(§12.7), forward-auth, and the app proxy for <app>.<box>.local (NETWORKING.md §9).

One registry line in app.py. What it registers:
- the `node.join` action handler (fabric.py) and its background loop;
- the app reverse proxy as an ASGI middleware (proxy.py: sign-in first, then the app's access);
- the mDNS publisher for onemind.local and the app names, when ONEMIND_NET_MDNS=1 (lan.py);
- routes under /v1/fabric, /v1/mesh, /v1/tls and /v1/auth;
- the owner's mesh state (CORE-NET-8): PUT /v1/mesh/settings stores it (mesh.py, table mesh_state),
  audits the change and applies it at once: the coordinator client, the box CA and the join bundle
  follow it. With no provider chosen the mesh answers 'not set up' with the next step.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import plistlib
import socket
import threading
import uuid
from dataclasses import replace
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Body, Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field, field_validator

from ..auth import Principal
from ..ca import BoxCA, box_name_from_hostname
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..fabric import FabricDeps, FabricService, JoinRequestBody, K3sBootstrapTokens, TicketRequest
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..lan import AvahiPublisher, desired_names
from ..mesh import (
    NEXT_PICK, TAG_HUB, HeadscaleClient, HeadscaleError, MeshService, MeshState, MeshStateRepository, setup_view,
    tls_transport,
)
from ..netconf import FabricSettings, MeshSettings, NetSettings
from ..netpath import PathClassifier, parse_networks
from ..proxy import (
    SESSION_COOKIE, AppProxy, AppProxyMiddleware, KubectlServiceResolver, gateway_session_resolver, sharing_check,
)


def trust_profile(box: str, ca_der: bytes) -> bytes:
    """An unsigned Apple configuration profile holding only the box CA as a root certificate.

    Apple shows it as "Not Verified", which is honest: the box signs nothing for Apple. The ids
    derive from the CA bytes, so installing a profile for the same CA twice replaces, not stacks.
    The profile cannot set anything but trust; the person still enables full trust in Settings on
    iOS (the instructions on the sign-in page say so)."""
    seed = uuid.uuid5(uuid.NAMESPACE_URL, "onemind-ca:" + ca_der.hex())
    cert_uuid = str(uuid.uuid5(seed, "cert")).upper()
    doc = {
        "PayloadType": "Configuration", "PayloadVersion": 1, "PayloadScope": "System",
        "PayloadIdentifier": f"com.onemindos.ca.{box}", "PayloadUUID": str(seed).upper(),
        "PayloadDisplayName": f"OneMind box {box}: trust this box",
        "PayloadDescription": "Lets this device trust the OneMind box at its own address, so passkeys and the dashboard work with no certificate warning.",
        "PayloadContent": [{
            "PayloadType": "com.apple.security.root", "PayloadVersion": 1,
            "PayloadIdentifier": f"com.onemindos.ca.{box}.cert", "PayloadUUID": cert_uuid,
            "PayloadDisplayName": f"OneMind box {box} CA", "PayloadContent": ca_der,
        }],
    }
    return plistlib.dumps(doc, fmt=plistlib.FMT_XML)

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


def relay_view(cfg: MeshSettings, show_addr: bool = False) -> dict:
    """What the box says about the owner's relay: plainly, never an error (NETWORKING §4.3).

    The mesh works on the home network with or without a relay, and with no internet at all; the
    relay only adds reach from outside. The address is an internet-facing machine, so like every
    address it is left out unless the owner asks (?addresses=1, contract §2)."""
    if cfg.relay_addr:
        return {"state": "configured", **({"addr": cfg.relay_addr} if show_addr else {}),
                "detail": "Your relay's address is saved, but reaching this box from outside does not work yet: "
                          "the relay cannot reach a box behind a home router until the box dials out to it "
                          "(a later step). At home and off grid everything works as before."}
    return {"state": "none",
            "detail": "No relay is set up. Everything works on your home network, with or without internet. "
                      "To reach this box from outside, turn one of your own machines into a relay."}


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 270

# Changing the mesh is the owner's (fabric:admin is in no other role's defaults); the handler checks too.
register_route_scope("PUT", r"/v1/mesh/settings", ("fabric:admin",))


class MeshSettingsBody(JsonBody):
    """The owner's mesh choice. Fields left out keep their value; provider "none" clears the choice."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    provider: Literal["headscale", "none"] | None = None
    control_url: str | None = Field(default=None, max_length=255,
                                    description="The https URL machines and phones reach the coordinator at")

    @field_validator("control_url")
    @classmethod
    def _https(cls, v: str | None) -> str | None:
        if v is not None:
            u = urlsplit(v)
            if u.scheme != "https" or not u.hostname:
                raise ValueError("control_url must be an https URL")
        return v


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    net = settings.section(NetSettings)
    env_mesh = settings.section(MeshSettings)  # what the installer wrote; the owner's stored state wins
    fab_cfg = settings.section(FabricSettings)
    box = net.box()
    box_ca = BoxCA(net.tls_dir or settings.audit_path.parent / "tls", box, clock=gw.clock)
    if net.tls:  # H-05: agent app pods verify the gateway's HTTPS with this CA (ONEMIND_GATEWAY_CA)
        gw.actions.gateway_ca = lambda: box_ca.ca_pem().decode()
    state_repo = MeshStateRepository(gw.db)
    state_lock = threading.Lock()
    # The provider's pieces are on this box: Headscale's 0600 key file and the hub's mesh address.
    installed = env_mesh.headscale_key_file is not None and env_mesh.hub_ip is not None

    def mesh_state() -> MeshState:
        return state_repo.get() or MeshState(enabled=env_mesh.enabled,
                                             provider="headscale" if env_mesh.enabled or installed else None,
                                             control_url=env_mesh.control_url)

    def build(state: MeshState) -> tuple[MeshSettings, MeshService | None]:
        """The settings and the coordinator client for `state`. Raises before anything changes."""
        on = state.enabled and state.provider == "headscale" and installed
        cfg = replace(env_mesh, enabled=on, control_url=state.control_url)
        if not on:
            return cfg, None
        assert cfg.headscale_key_file is not None  # installed
        box_ca.ensure()  # the box CA starts with the mesh: Headscale's TLS and every node pin it
        extra = {}
        if cfg.headscale_url.startswith("https:"):  # Headscale's own TLS, verified with the box CA
            extra["transport"] = tls_transport(box_ca.dir / "ca.crt", urlsplit(cfg.control_url).hostname or "")
        return cfg, MeshService(HeadscaleClient.from_key_file(cfg.headscale_url, cfg.headscale_key_file, **extra),
                                gw.audit, gw.clock)

    mesh_cfg, mesh = build(mesh_state())
    app.state.mesh = mesh  # read by GET /v1/status (FD-01)
    fabric = FabricService(FabricDeps(
        actions=gw.actions, audit=gw.audit, events=gw.events, registry=gw.registry, db=gw.db, clock=gw.clock,
        box_ca=box_ca, net=net, mesh_settings=mesh_cfg, fabric=fab_cfg, mesh=mesh,
        k3s=K3sBootstrapTokens(settings.kubectl, fab_cfg.k3s_ca_hash) if fab_cfg.k3s else None,
        hub_node_id=settings.node_id,
    ))
    gw.actions.register_handler("node.join", fabric)

    def apply(cfg: MeshSettings, svc: MeshService | None) -> None:
        """Swap the running mesh: the view, GET /v1/status and fabric joins read these on every request."""
        nonlocal mesh_cfg, mesh
        old = mesh
        mesh_cfg, mesh = cfg, svc
        app.state.mesh = svc
        fabric.d.mesh_settings, fabric.d.mesh = cfg, svc
        if old is not None and svc is None:
            # Off: joins handed a key can no longer be bind-checked (§5.1), so they fail now, cleaned up
            # with the old client. Members that already joined stay (setup_view says so).
            stopped = fabric.mesh_switched_off(old)
            if stopped:
                log.info("mesh turned off: %d join(s) awaiting the mesh check were stopped", stopped)

    def mesh_settings_json() -> dict:
        state = mesh_state()
        return {"settings": state.to_json(), "setup": setup_view(state, installed)}

    # ---- the app proxy: <app>.<box>.local, <app>.onemind.local, <app>.apps.onemind.internal ----------
    def exposure_of(app_id: str) -> str:
        """The app's tier (§12.22, default private), read when a request arrives on a mesh name."""
        return app.state.appstore.repo.get_exposure(app_id)[0]

    classify = PathClassifier(parse_networks(net.trusted_proxies))  # the tier is enforced by network path too (#285)
    proxy = AppProxy(
        gw.catalog, lambda i: (st := gw.repo.get_app_state(i)) and st.status,
        gateway_session_resolver(gw.tokens, gw.authenticators), KubectlServiceResolver(settings.kubectl),
        box_domains=net.box_domains(), audit=gw.audit.append, path_routes=net.path_routes,
        exposure=exposure_of, shared=sharing_check(gw.authenticators, gw.app_filters),
        classify=classify, path_aware_sessions=True,
        browsers=getattr(app.state, "browsers", None),  # routers/browsers.py (#692)
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
        svc = mesh
        if svc is None:
            return
        try:
            digest = svc.push_policy([])
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
    @app.post("/v1/fabric/join-tickets", operation_id="fabric.ticket_create", tags=["fabric"], status_code=201, responses=error_responses(401, 403, 409, 422))
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

    @app.get("/v1/tls/ca.crt", operation_id="tls.ca", tags=["tls"], response_class=Response,
             responses={200: {"description": "The box CA certificate: DER by default, PEM with ?format=pem",
                              "content": {"application/x-x509-ca-cert": {"schema": {"type": "string", "format": "binary"}},
                                          "application/x-pem-file": {"schema": {"type": "string"}}}}})
    def ca_cert(format: str = "der"):
        """Open, like /healthz: a phone or a joining node needs the CA before it can sign in. It is
        public data; clients pin it by the sha256 shown in the pairing QR."""
        if format == "pem":
            return Response(box_ca.ca_pem(), media_type="application/x-pem-file")
        return Response(box_ca.ca_der(), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": f'attachment; filename="onemind-{box}-ca.crt"'})

    @app.get("/v1/tls/onemind.mobileconfig", operation_id="tls.profile", tags=["tls"], response_class=Response,
             responses={200: {"description": "Apple configuration profile that makes an iPhone, iPad or Mac trust the box CA",
                              "content": {"application/x-apple-aspen-config": {"schema": {"type": "string", "format": "binary"}}}}})
    def ca_profile():
        """Open, like ca.crt: it carries only the public CA certificate. Same trust, one tap on Apple devices."""
        return Response(trust_profile(box, box_ca.ca_der()), media_type="application/x-apple-aspen-config",
                        headers={"Content-Disposition": f'attachment; filename="onemind-{box}-trust.mobileconfig"'})

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
            "relay": relay_view(mesh_cfg, show_ips), "nodes": [], "devices": [],
            "names": {"lan": ["onemind.local", f"{box}.local"], "mesh": ["hub.onemind.internal"] if mesh_cfg.enabled else []},
            "apps": apps, "https": net.tls,
            # Reading the view never creates the CA: it starts with the mesh, HTTPS or a join ticket.
            "ca_sha256": box_ca.ca_fingerprint() if mesh_cfg.enabled or net.tls or box_ca.started() else "",
            **mesh_settings_json(),
        }
        svc = mesh
        if svc is None:
            return out
        checked = gw.clock().isoformat().replace("+00:00", "Z")
        try:
            hs_nodes = svc.client.list_nodes()
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

    @app.put("/v1/mesh/settings", operation_id="mesh.settings_update", tags=["mesh"],
             responses=error_responses(401, 403, 409, 422))
    def put_mesh_settings(body: MeshSettingsBody, p: Principal = Depends(principal)):
        """Change the mesh (owner only, audited): on or off, the provider, the control URL. It applies at once.

        Turning the mesh on with no provider chosen is refused with the next step. A provider that is
        chosen but not installed on this box is stored, and GET /v1/mesh says how to install it.
        Turning it off stops minting keys and fails joins still waiting for their mesh check; it does not
        stop the coordinator or disconnect machines and phones that already joined."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "change the mesh settings", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not change the mesh settings")
        with state_lock:
            before = mesh_state()
            after = before.values()
            if body.enabled is not None:
                after["enabled"] = body.enabled
            if body.provider is not None:
                after["provider"] = None if body.provider == "none" else body.provider
            if body.control_url is not None:
                after["control_url"] = body.control_url
            if after["enabled"] and after["provider"] is None:
                raise ApiError(409, "conflict", f"No mesh provider is chosen. {NEXT_PICK}", reason="mesh_no_provider")
            if after != before.values():
                try:
                    cfg, svc = build(MeshState(**after, saved=True))
                except (OSError, ValueError) as exc:  # the key file went missing or lost its 0600 mode
                    raise ApiError(409, "conflict", f"The mesh provider on this box cannot be used: {exc.__class__.__name__}. "
                                   "Run the box installer again, then retry.", reason="mesh_provider_unusable") from None
                state_repo.put(after, by=p.as_dict(), now=gw.clock())
                apply(cfg, svc)
                gw.audit.append("mesh.settings.changed", p.as_dict(), None, {"before": before.values(), "after": after})
                if svc is not None:
                    push_policy()
        return mesh_settings_json()

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
        headers["host"] = host  # the name the person used, not the gateway's own: the exposure tier depends on it
        # Only the edge calls this (loopback), so its X-OneMind-Path is the path; absent means unknown.
        status, who, _route = proxy.decide(headers, matched[0], classify.from_edge(headers))
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
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "open an app session", "reason": "permission_denied"})
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
