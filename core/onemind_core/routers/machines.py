# SPDX-License-Identifier: Apache-2.0
"""Machines (MACH-01, #281; docs/umbrel2/machines.md §4.8): what this box can run, and enabling it.

Part 1: the preflight. `GET /v1/machines/capabilities` says, per node, whether it can run virtual
machines and why not. `POST /v1/machines/enable` is the owner's switch: it is refused, with the
reasons, on a Pi, a small box, a box without KVM and a box that is itself a VM. Nothing is installed
yet: the KubeVirt extension (MACH-2) and the machine actions (MACH-3) follow, after LT-MACH-2
measures them on real KVM hardware.

Part 5 (MACH-2): enabling is real. It files the owner-approved `machines.enable` action, which applies
the pinned KubeVirt and CDI layer, waits until both are ready and only then reports `enabled`.
`POST /v1/machines/disable` files `machines.disable`, which removes them again.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..machines.capability import MIN_MEMORY_MB, describe
from ..machines.console import ConsoleBroker, ConsoleMiddleware, KubectlProxyUpstream
from ..machines.media import MachineUploadResult
from ..machines.service import MachineService
from ..machines.spec import IMAGE_CATALOGUE, CatalogueImage


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 330


class MachineCapabilities(BaseModel):
    enabled: bool
    extension: dict
    requirements: dict
    eligible_node_ids: list[str]
    nodes: list[dict]
    image_catalogue: list[CatalogueImage]


# What a scoped token needs (identity/scopes.py): the capabilities show what /v1/nodes shows, so
# that scope reads them; enabling is owner-only, and `machines:admin` is minted to no one, so
# only the owner role (every scope) holds it. Without rows both routes fell to "full scope only".
register_route_scope("GET,HEAD", r"/v1/machines/capabilities", ("nodes:read",))
register_route_scope("POST", r"/v1/machines/enable", ("machines:admin",))
register_route_scope("POST", r"/v1/machines/disable", ("machines:admin",))
# Part 3: the machines the owner has, and the console ticket (owner-only, like enabling).
register_route_scope("GET,HEAD", r"/v1/machines", ("nodes:read",))
register_route_scope("GET,HEAD", r"/v1/machines/[a-z][a-z0-9-]*", ("nodes:read",))
register_route_scope("GET,HEAD", r"/v1/machines/[a-z][a-z0-9-]*/snapshots", ("nodes:read",))
register_route_scope("POST", r"/v1/machines/[a-z][a-z0-9-]*/console", ("machines:admin",))
register_route_scope("POST", r"/v1/machines/[a-z][a-z0-9-]*/upload", ("machines:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    svc = MachineService(gw)
    svc.register()  # machine.create|start|stop|delete: requested by an owner or an agent, approved by an owner
    app.state.machines = svc
    # The console screen: a WebSocket whose credential is the ticket below (console.py). Only a real
    # runtime has a display to show; the noop executor (demos, tests) closes it with a plain reason.
    upstream = None if gw.settings.executor == "noop" else KubectlProxyUpstream(gw.settings.kubectl)
    app.state.machine_console = ConsoleBroker(
        svc.redeem, upstream, lambda event, who, data: gw.audit.append(event, who or None, None, data))
    app.add_middleware(ConsoleMiddleware, broker=app.state.machine_console)

    def capabilities() -> dict:
        nodes = [describe(n) for n in gw.registry.list()]
        ext = svc.extension_status()
        eligible = [n["node_id"] for n in nodes if n["eligible"]]
        return {
            "enabled": ext["state"] == "ready",
            "extension": ext,
            "requirements": {"min_memory_mb": MIN_MEMORY_MB, "arch": "amd64", "kvm": True},
            "eligible_node_ids": eligible,
            "nodes": nodes,
            "image_catalogue": IMAGE_CATALOGUE,
        }

    @app.get("/v1/machines/capabilities", tags=["machines"], operation_id="machines.capabilities",
             response_model=MachineCapabilities, responses=error_responses(401))
    def machines_capabilities(_: Principal = Depends(principal)):
        """Which nodes can run virtual machines, and the reasons the others cannot."""
        return capabilities()

    def file(p: Principal, which: str, response: Response) -> dict:
        """The owner's button: the same checks as the request route, then the action waits for approval."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": f"{which} machines", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"only an owner may turn machines {'on' if which == 'enable' else 'off'}")
        if which == "enable":
            caps = capabilities()
            if not caps["eligible_node_ids"]:
                reasons = [{"node_id": n["node_id"], **r} for n in caps["nodes"] for r in n["reasons"]]
                gw.audit.append("machines.enable.refused", p.as_dict(), None, {"reasons": sorted({r["code"] for r in reasons})})
                raise ApiError(409, "policy_refused", "This box cannot run virtual machines: " + (
                    " ".join(sorted({r["message"] for r in reasons})) or "no node has reported yet."),
                    reason="machines_unsupported", details=reasons or None)
        found = svc.enable_problem() if which == "enable" else svc.disable_problem()
        if found is not None:
            raise ApiError(409, "policy_refused", found[1], reason=found[0])
        window = 600  # one open request per ten minutes: a double click files it once
        now = gw.clock()
        bucket = int(now.timestamp()) // window
        action, created = gw.actions.request_feature(
            p, f"machines.{which}", {}, idempotency_key=f"machines-{which}-{bucket}",
            expires_at=now + timedelta(seconds=window), reason=f"owner asked to turn machines {'on' if which == 'enable' else 'off'}")
        response.status_code = 202 if created else 200
        return action

    @app.post("/v1/machines/enable", tags=["machines"], operation_id="machines.enable", status_code=202, responses=error_responses(401, 403, 409))
    def machines_enable(response: Response, p: Principal = Depends(principal)):
        """The owner's switch for machines. Refused with reasons unless a node can run them; otherwise it
        files `machines.enable`, which waits in Approvals and installs KubeVirt and CDI once an owner approves."""
        return file(p, "enable", response)

    @app.post("/v1/machines/disable", tags=["machines"], operation_id="machines.disable", status_code=202, responses=error_responses(401, 403, 409))
    def machines_disable(response: Response, p: Principal = Depends(principal)):
        """Turn machines off again: files `machines.disable`. Refused while any machine exists."""
        return file(p, "disable", response)

    @app.get("/v1/machines", tags=["machines"], operation_id="machines.list", responses=error_responses(401))
    def machines_list(_: Principal = Depends(principal)):
        """The machines on this box, with their state and the quota they hold."""
        return svc.repo.all()

    @app.get("/v1/machines/{name}", tags=["machines"], operation_id="machines.get", responses=error_responses(401, 404))
    def machines_get(name: str, _: Principal = Depends(principal)):
        row = svc.repo.get(name)
        if row is None:
            raise ApiError(404, "not_found", f"There is no machine named {name}.")
        return row

    @app.get("/v1/machines/{name}/snapshots", tags=["machines"], operation_id="machines.snapshots", responses=error_responses(401, 404))
    def machines_snapshots(name: str, _: Principal = Depends(principal)):
        """The snapshots of one machine, with how consistent each copy is (a running machine's copy may be best effort)."""
        if svc.repo.get(name) is None:
            raise ApiError(404, "not_found", f"There is no machine named {name}.")
        return svc.repo.snapshots(name)

    @app.post("/v1/machines/{name}/upload", tags=["machines"], operation_id="machines.upload",
              response_model=MachineUploadResult, responses=error_responses(401, 403, 404, 409, 413, 503))
    def machines_upload(name: str, p: Principal = Depends(principal)):
        """Stream the approved Files uploads to this halted machine's CDI volumes and return their checked SHA-256."""
        return svc.upload(name, p)

    @app.post("/v1/machines/{name}/console", tags=["machines"], operation_id="machines.console", responses=error_responses(401, 403, 404, 409))
    def machines_console(name: str, p: Principal = Depends(principal)):
        """A one-minute, single-use console ticket for `GET /v1/machines/{name}/console/ws` (add `view=1` for a screen with no hands). Owner only: an agent never gets a screen."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "open machine console", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may open a machine's console")
        out = svc.console_ticket(name, p.as_dict())
        gw.audit.append("machines.console.ticket", p.as_dict(), None, {"machine": name})
        return out
