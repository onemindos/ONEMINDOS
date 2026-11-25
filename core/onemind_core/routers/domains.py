# SPDX-License-Identifier: Apache-2.0
"""NET-DOM-01 (#238): bring your own domain. Owner only, off by default (domains.py).

GET    /v1/domains                              the domains, their proof record and requested names
POST   /v1/domains                              register a domain: returns the TXT record to add
DELETE /v1/domains/{domain}                     forget a domain and its names
POST   /v1/domains/{domain}/check               ask DNS for the proof record
POST   /v1/domains/{domain}/hosts               request <app>.<domain>
POST   /v1/domains/hosts/{hostname}/approve     the owner approves one name (typed in full)
DELETE /v1/domains/hosts/{hostname}             withdraw a name
Approving records a decision only: no certificate is issued and nothing is served yet.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..domains import AcmeAccount, DnsResolver, DomainError, DomainService, DomainSettings
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..netconf import NetSettings
from .net import web_apps

# Owner only: the "*" scope is the owner role's, so an adult token or an agent is refused at the route.
register_route_scope("GET,HEAD,POST,DELETE", r"/v1/domains(/.*)?", ("*",))

ORDER = 275


class DomainBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str = Field(min_length=3, max_length=253)


class HostBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=63)


class ApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str = Field(min_length=3, max_length=253)


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(DomainSettings)
    net = gw.settings.section(NetSettings)
    tls_dir = net.tls_dir or gw.settings.audit_path.parent / "tls"
    svc = DomainService(gw.db, AcmeAccount(tls_dir), DnsResolver(cfg.resolver, cfg.timeout_s), gw.clock,
                        lambda: web_apps(gw), cfg.enabled)
    app.state.domains = svc

    def owner(p: Principal = Depends(gw.principal)) -> Principal:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "domains", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "your own domain is the owner's to manage")
        return p

    def run(fn, *args):
        try:
            return fn(*args)
        except DomainError as exc:
            raise ApiError(exc.status, exc.code, exc.message, reason=exc.reason) from None

    def audit(p: Principal, event: str, data: dict) -> None:
        gw.audit.append(event, p.as_dict(), None, data)

    @app.get("/v1/domains", operation_id="domains.list", tags=["domains"], responses=error_responses(401, 403, 404, 409, 422, 503))
    def list_domains(response: Response, _: Principal = Depends(owner)):
        response.headers["Cache-Control"] = "no-store"
        return svc.summary()

    @app.post("/v1/domains", operation_id="domains.add", tags=["domains"], status_code=201,
              responses=error_responses(401, 403, 404, 409, 422, 503))
    def add(body: DomainBody, p: Principal = Depends(owner)):
        out = run(svc.add, body.domain, p.id)
        audit(p, "domains.added", {"domain": out["domain"]})
        return out

    @app.delete("/v1/domains/{domain}", operation_id="domains.remove", tags=["domains"], status_code=204,
                responses=error_responses(401, 403, 404, 409, 422, 503))
    def remove(domain: str, p: Principal = Depends(owner)):
        run(svc.remove, domain)
        audit(p, "domains.removed", {"domain": domain.lower()})
        return Response(status_code=204)

    @app.post("/v1/domains/{domain}/check", operation_id="domains.check", tags=["domains"],
              responses=error_responses(401, 403, 404, 409, 422, 503))
    def check(domain: str, p: Principal = Depends(owner)):
        out = run(svc.check, domain)
        audit(p, "domains.checked", {"domain": out["domain"]["domain"], "verified": out["proof_found"]})
        return out

    @app.post("/v1/domains/{domain}/hosts", operation_id="domains.host_request", tags=["domains"], status_code=201,
              responses=error_responses(401, 403, 404, 409, 422, 503))
    def request_host(domain: str, body: HostBody, p: Principal = Depends(owner)):
        out = run(svc.request_host, domain, body.app_id, p.id)
        audit(p, "domains.host_requested", {"hostname": out["hostname"], "app_id": body.app_id})
        return out

    @app.post("/v1/domains/hosts/{hostname}/approve", operation_id="domains.host_approve", tags=["domains"],
              responses=error_responses(401, 403, 404, 409, 422, 503))
    def approve(hostname: str, body: ApproveBody, p: Principal = Depends(owner)):
        out = run(svc.approve_host, hostname.lower(), body.confirm, p.id)
        audit(p, "domains.host_approved", {"hostname": out["hostname"], "app_id": out["app_id"]})
        return out

    @app.delete("/v1/domains/hosts/{hostname}", operation_id="domains.host_remove", tags=["domains"], status_code=204,
                responses=error_responses(401, 403, 404, 409, 422, 503))
    def remove_host(hostname: str, p: Principal = Depends(owner)):
        run(svc.revoke_host, hostname)
        audit(p, "domains.host_removed", {"hostname": hostname.lower()})
        return Response(status_code=204)
