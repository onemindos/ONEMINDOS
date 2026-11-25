# SPDX-License-Identifier: Apache-2.0
"""The agent browser (#694; agentbrowser/ has the model).

- GET    /v1/agent-browser/sites                       the allowlist (owner: every agent's; an agent: its own)
- POST   /v1/agent-browser/sites                       file agentbrowser.site.allow; only an owner's approval adds it
- DELETE /v1/agent-browser/sites/{site_id}             owner only: take a site away, at once
- GET    /v1/agent-browser/sessions                    sessions (owner: all; an agent: its own)
- POST   /v1/agent-browser/sessions                    start a fresh browser pod for the caller
- DELETE /v1/agent-browser/sessions/{session_id}       end it (owner: any; an agent: its own)
- POST   /v1/agent-browser/sessions/{session_id}/visit open a page: 200 allowed, or 202 approval_required
                                                       with the action the owner approves

Only the owner and AI agents call these; every other person, plugin, automation or node is
refused (403, audited). The agent kill switch refuses agents at the door and ends every session.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..agentbrowser.pods import BrowserPods, PodError
from ..agentbrowser.proxy import EgressProxy
from ..agentbrowser.service import AgentBrowser
from ..agentbrowser.settings import AgentBrowserSettings
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..executors import local_flannel_addresses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody

ORDER = 157  # after agents (155): the kill switch it obeys is registered there
TAGS = ["agent-browser"]
# A retried request with the same key gets the same answer: the same action, session or visit result.
IdemHeader = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)]

register_route_scope("GET,HEAD", r"/v1/agent-browser/(sites|sessions)", ("actions:read",))
register_route_scope("POST", r"/v1/agent-browser/(sites|sessions)", ("actions:request",))
register_route_scope("POST,DELETE", r"/v1/agent-browser/sessions/[^/]+(/visit)?", ("actions:request",))
register_route_scope("DELETE", r"/v1/agent-browser/sites/[^/]+", ("*",))


class AgentBrowserSite(BaseModel):
    id: str
    agent: str = Field(description="The agent principal id this entry is for")
    entry: str = Field(description="example.org (that host) or *.example.org (its subdomains)")
    plan_sha256: str = Field(description="The plan hash the owner approved")
    action_id: str = Field(description="The agentbrowser.site.allow action that added it")
    approved_by: str | None = None
    created_at: str


class SiteBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    entry: str = Field(min_length=1, max_length=260, description="example.org or *.example.org")
    agent: str | None = Field(default=None, min_length=1, max_length=200,
                              description="Owner: the agent it is for (required). An agent: omit it, or name itself")
    note: str | None = Field(default=None, max_length=500, description="Why, shown on the approval card")


class AgentBrowserSession(BaseModel):
    id: str
    agent: str = Field(description="The principal that started it")
    state: Literal["starting", "running", "ended"]
    pages: int
    max_pages: int
    pages_left: int
    created_at: str
    expires_at: str
    ended_reason: str | None = None


class SessionBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    max_pages: int | None = Field(default=None, ge=1, le=1000, description="Page budget (capped by the box's limit)")


class VisitBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=4096, description="https URL of a page")
    kind: Literal["navigate", "submit", "download"] = "navigate"
    approval_id: str | None = Field(default=None, max_length=80,
                                    description="The approved agentbrowser.step action that allows this one step, once")


class AgentBrowserPage(BaseModel):
    status: int | None = None
    final_url: str | None = Field(default=None, description="Where the page ended up, without query")
    title: str
    text: str = Field(description="The page's visible text, at most 20000 characters")


class AgentBrowserVisit(BaseModel):
    decision: Literal["allowed"]
    url: str = Field(description="The URL opened, without query or fragment")
    session: AgentBrowserSession
    page: AgentBrowserPage


class AgentBrowserApproval(BaseModel):
    decision: Literal["approval_required"]
    reason: Literal["site_not_approved", "sign_in", "payment", "submit", "download"]
    session: AgentBrowserSession
    action: Action = Field(description="The request waiting for the owner (approve it in /v1/actions)")


class SiteRemoved(BaseModel):
    removed: bool
    id: str


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(AgentBrowserSettings)
    pods = BrowserPods(gw.settings.kubectl, cfg.namespace)
    hub_reader = local_flannel_addresses()

    def kill_switch() -> bool:
        stop = getattr(app.state, "agent_stop", None)
        return bool(stop is not None and stop.on)

    svc = AgentBrowser(gw, cfg, pods, hub=lambda: list(cfg.hub_cidrs) or hub_reader(), kill_switch=kill_switch)
    svc.proxy = EgressProxy(svc.authorize_connect)
    svc.register()
    app.state.agent_browser = svc
    principal = gw.principal

    async def startup() -> None:
        if not cfg.enabled:
            return
        try:
            pods.stop_all()  # sessions live in memory: a pod left from an earlier run belongs to no one
        except PodError:
            pass
        await svc.proxy.start(cfg.proxy_listen, cfg.proxy_port)

    async def shutdown() -> None:
        svc.end_all("gateway_stopped")
        await svc.proxy.stop()

    gw.on_startup(startup)
    gw.on_shutdown(shutdown)

    @app.get("/v1/agent-browser/sites", operation_id="agentbrowser.sites.list", tags=TAGS,
             responses={200: {"model": list[AgentBrowserSite]}, **error_responses(401, 403)})
    def list_sites(p: Principal = Depends(principal)):
        return svc.sites(p)

    @app.post("/v1/agent-browser/sites", operation_id="agentbrowser.sites.request", tags=TAGS, status_code=201,
              responses={200: {"model": Action, "description": "The same request was already filed"},
                         201: {"model": Action}, **error_responses(401, 403, 409, 422, 429)})
    def request_site(body: SiteBody, idem: IdemHeader = None, p: Principal = Depends(principal)):
        action, created = svc.request_site(p, body.entry, body.agent, body.note, idem)
        return JSONResponse(action, status_code=201 if created else 200)

    @app.delete("/v1/agent-browser/sites/{site_id}", operation_id="agentbrowser.sites.remove", tags=TAGS,
                responses={200: {"model": SiteRemoved}, **error_responses(401, 403, 404)})
    def remove_site(site_id: str, p: Principal = Depends(principal)):
        return svc.remove_site(p, site_id)

    @app.get("/v1/agent-browser/sessions", operation_id="agentbrowser.sessions.list", tags=TAGS,
             responses={200: {"model": list[AgentBrowserSession]}, **error_responses(401, 403)})
    def list_sessions(p: Principal = Depends(principal)):
        return svc.list(p)

    @app.post("/v1/agent-browser/sessions", operation_id="agentbrowser.sessions.start", tags=TAGS, status_code=201,
              responses={201: {"model": AgentBrowserSession}, **error_responses(401, 403, 409, 422, 503)})
    def start_session(body: SessionBody | None = None, idem: IdemHeader = None, p: Principal = Depends(principal)):
        return JSONResponse(svc.start(p, body.max_pages if body else None, idem), status_code=201)

    @app.delete("/v1/agent-browser/sessions/{session_id}", operation_id="agentbrowser.sessions.end", tags=TAGS,
                responses={200: {"model": AgentBrowserSession}, **error_responses(401, 403, 404)})
    def end_session(session_id: str, p: Principal = Depends(principal)):
        return svc.end(p, session_id)

    @app.post("/v1/agent-browser/sessions/{session_id}/visit", operation_id="agentbrowser.sessions.visit", tags=TAGS,
              responses={200: {"model": AgentBrowserVisit},
                         202: {"model": AgentBrowserApproval, "description": "approval_required: the owner decides first"},
                         **error_responses(401, 403, 404, 409, 422, 429, 503)})
    def visit(session_id: str, body: VisitBody, idem: IdemHeader = None, p: Principal = Depends(principal)):
        out, status = svc.visit(p, session_id, body.url, body.kind, body.approval_id, idem)
        return JSONResponse(out, status_code=status)
