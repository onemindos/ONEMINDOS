# SPDX-License-Identifier: Apache-2.0
"""The agent browser service (#694): allowlist, sessions, visit decisions, audit.

- An agent's allowlist grows only through action `agentbrowser.site.allow`: the agent (or the
  owner) files it with a plan hash over {agent, entry}; it lands in awaiting_approval and only an
  owner's approval adds the row (actions.py: AI requests, a person approves; never a standing
  approval, the type is not in the automation registry). The owner removes an entry directly.
- A session is one fresh browser pod (pods.py). Sessions live in this process's memory on purpose:
  nothing of a browser outlives its session, and a gateway restart deletes every leftover pod.
- A visit to a host off the allowlist answers approval_required and files the site request; a
  sign-in page, a payment page, a form submit or a download on an approved site answers
  approval_required and files `agentbrowser.step`, a one-time approval bound by plan hash to that
  agent, session, kind and exact URL (query included: the card shows it, `full_sha256` pins it).
- Every visit is audited (`agentbrowser.visit`: agent, URL without query, decision); a refused
  CONNECT at the proxy is audited once per host and session.
- Limits: pages per session (the budget), session lifetime, sessions per agent. The agent kill
  switch (agent_stop.py) ends every session at once and the proxy refuses while it is on.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from ..actions import FeatureAction
from ..auth import Principal
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Action, Base, iso, utc
from ..store import FeatureSchema
from . import policy
from .pods import BrowserPods, PodError, namespace_doc, policy_docs, session_docs
from .settings import AgentBrowserSettings

SCHEMA = FeatureSchema("agentbrowser")
SITE_ACTION = "agentbrowser.site.allow"
STEP_ACTION = "agentbrowser.step"
SITE_TTL = timedelta(days=1)
STEP_TTL = timedelta(hours=1)


class AllowedSiteRow(Base):
    __tablename__ = "agentbrowser_sites"
    __table_args__ = (UniqueConstraint("agent", "entry", name="uq_agentbrowser_site"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent: Mapped[str] = mapped_column(String(200), index=True)
    entry: Mapped[str] = mapped_column(String(260))
    plan_sha256: Mapped[str] = mapped_column(String(80))
    action_id: Mapped[str] = mapped_column(String(80))
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass
class Session:
    id: str
    owner: dict  # the principal that started it: {"id", "kind", "role"}
    created_at: datetime
    expires_at: datetime
    max_pages: int
    control_token: str = field(repr=False)
    proxy_token: str = field(repr=False)
    pages: int = 0
    state: str = "starting"  # starting | running | ended
    ended_reason: str | None = None
    refused_hosts: set[str] = field(default_factory=set)
    used_steps: set[str] = field(default_factory=set)
    replies: dict[str, tuple[tuple, dict, int]] = field(default_factory=dict, repr=False)  # Idempotency-Key -> reply

    def view(self) -> dict:
        return {"id": self.id, "agent": self.owner["id"], "state": self.state, "pages": self.pages,
                "max_pages": self.max_pages, "pages_left": max(0, self.max_pages - self.pages),
                "created_at": iso(self.created_at), "expires_at": iso(self.expires_at),
                "ended_reason": self.ended_reason}


def _key(*parts: str) -> str:
    return "agentbrowser:" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]


class AgentBrowser:
    def __init__(self, gw: Any, cfg: AgentBrowserSettings, pods: BrowserPods, *,
                 hub: Any = lambda: [], proxy: Any = None, kill_switch: Any = lambda: False):
        self.gw, self.cfg, self.pods, self.hub, self.proxy = gw, cfg, pods, hub, proxy
        self.kill_switch = kill_switch
        self.sessions: dict[str, Session] = {}
        self._starts: dict[tuple[str, str], str] = {}  # (principal id, Idempotency-Key) -> session id
        self._lock = threading.Lock()
        # How the gateway reaches a running pod's control port: fn(ip, port, token, body) -> dict.
        self.control = _control_call

    # ---- registration ------------------------------------------------------------------------
    def register(self) -> None:
        acts = self.gw.actions
        acts.register_type(SITE_ACTION, FeatureAction("sensitive", self._run_site, frozenset({"person", "agent"}),
                                                      check=self._check_site))
        acts.register_type(STEP_ACTION, FeatureAction("sensitive", self._run_step, frozenset({"person", "agent"}),
                                                      check=self._check_step))
        self.gw.events.subscribe("agents.stopped", lambda _env: self.end_all("agents_stopped"))

    # ---- who may ----------------------------------------------------------------------------
    def _deny(self, p: Principal, what: str) -> ApiError:
        self.gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", "only the owner or an AI agent uses the agent browser")

    def caller(self, p: Principal, what: str) -> None:
        if not (p.is_owner or (p.kind == "agent" and p.can_request_actions)):
            raise self._deny(p, what)

    def owner_only(self, p: Principal, what: str) -> None:
        if not p.is_owner:
            self.gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only the owner removes an approved site")

    def _off(self) -> ApiError:
        return ApiError(409, "policy_refused", "the agent browser is switched off on this box (ONEMIND_AGENTBROWSER_ENABLED)",
                        reason="agent_browser_off")

    # ---- the allowlist ----------------------------------------------------------------------
    def entries(self, agent: str) -> frozenset[str]:
        with self.gw.db.session() as s:
            return frozenset(s.scalars(select(AllowedSiteRow.entry).where(AllowedSiteRow.agent == agent)))

    def sites(self, p: Principal) -> list[dict]:
        self.caller(p, "list agent browser sites")
        q = select(AllowedSiteRow).order_by(AllowedSiteRow.created_at)
        if not p.is_owner:
            q = q.where(AllowedSiteRow.agent == p.id)
        with self.gw.db.session() as s:
            return [{"id": r.id, "agent": r.agent, "entry": r.entry, "plan_sha256": r.plan_sha256,
                     "action_id": r.action_id, "approved_by": r.approved_by, "created_at": iso(utc(r.created_at))}
                    for r in s.scalars(q)]

    def request_site(self, p: Principal, entry: str, agent: str | None, reason: str | None,
                     idem: str | None = None) -> tuple[dict, bool]:
        self.caller(p, "request an agent browser site")
        if p.is_owner:
            if not agent:
                raise ApiError(422, "conflict", "agent: name the agent this site is for")
        elif agent not in (None, p.id):
            raise self._deny(p, "request a site for another agent")
        agent = agent or p.id
        try:
            entry = policy.normalize_entry(entry)
        except policy.UrlRefused as exc:
            raise ApiError(422, "conflict", f"entry: {exc}") from None
        return self._file_site(p, agent, entry, reason, idem)

    def _file_site(self, p: Principal, agent: str, entry: str, reason: str | None,
                   idem: str | None = None) -> tuple[dict, bool]:
        _, sha = policy.site_plan(agent, entry)
        now = self.gw.clock()
        return self.gw.actions.request_feature(
            p, SITE_ACTION, {"agent": agent, "entry": entry, "plan_sha256": sha},
            idempotency_key=_key("idem", p.id, idem) if idem else _key("site", p.id, agent, entry, now.date().isoformat()),
            expires_at=now + SITE_TTL, reason=reason, pending_cap=True)

    def remove_site(self, p: Principal, site_id: str) -> dict:
        self.owner_only(p, "remove an agent browser site")
        with self.gw.db.session.begin() as s:
            row = s.get(AllowedSiteRow, site_id)
            if row is None:
                raise ApiError(404, "not_found", f"There is no approved site {site_id}.")
            agent, entry = row.agent, row.entry
            s.delete(row)
        self.gw.audit.append("agentbrowser.site.removed", p.as_dict(), None, {"agent": agent, "entry": entry})
        return {"removed": True, "id": site_id}

    def _check_site(self, a: Action) -> str | None:
        _, sha = policy.site_plan(a.params.get("agent", ""), a.params.get("entry", ""))
        return None if hmac.compare_digest(sha, a.params.get("plan_sha256", "")) else "the site plan changed; ask again"

    def _run_site(self, a: Action, finish) -> None:
        if (problem := self._check_site(a)) is not None:
            return finish(ExecResult("failed", problem))
        agent, entry = a.params["agent"], a.params["entry"]
        with self.gw.db.session.begin() as s:
            exists = s.scalar(select(AllowedSiteRow).where(AllowedSiteRow.agent == agent, AllowedSiteRow.entry == entry))
            if exists is None:
                s.add(AllowedSiteRow(id="abs_" + uuid.uuid4().hex[:20], agent=agent, entry=entry,
                                     plan_sha256=a.params["plan_sha256"], action_id=a.id,
                                     approved_by=a.approved_by, created_at=self.gw.clock()))
        finish(ExecResult("succeeded", f"{entry} is on {agent}'s agent browser allowlist"))

    # ---- one-time steps (sign-in, payment, submit, download) ---------------------------------
    def _check_step(self, a: Action) -> str | None:
        prm = a.params
        _, sha = policy.step_plan(prm.get("agent", ""), prm.get("session_id", ""), prm.get("kind", ""),
                                  prm.get("reason", ""), prm.get("url", ""), prm.get("query", ""),
                                  prm.get("full_sha256", ""))
        return None if hmac.compare_digest(sha, prm.get("plan_sha256", "")) else "the step plan changed; ask again"

    def _run_step(self, a: Action, finish) -> None:
        problem = self._check_step(a)
        finish(ExecResult("failed", problem) if problem else ExecResult("succeeded", "one step approved, once"))

    # ---- sessions ---------------------------------------------------------------------------
    def _sweep(self) -> None:
        now = self.gw.clock()
        for s in list(self.sessions.values()):
            if s.state != "ended" and now >= s.expires_at:
                self._end(s, "lifetime_over", None)

    def _get(self, p: Principal, sid: str) -> Session:
        s = self.sessions.get(sid)
        if s is None or not (p.is_owner or s.owner["id"] == p.id):  # another agent's: no existence oracle
            raise ApiError(404, "not_found", f"There is no agent browser session {sid}.")
        return s

    def list(self, p: Principal) -> list[dict]:
        self.caller(p, "list agent browser sessions")
        self._sweep()
        return [s.view() for s in self.sessions.values() if p.is_owner or s.owner["id"] == p.id]

    def start(self, p: Principal, max_pages: int | None, idem: str | None = None) -> dict:
        self.caller(p, "start an agent browser session")
        if not self.cfg.enabled:
            raise self._off()
        if idem and (prior := self.sessions.get(self._starts.get((p.id, idem), ""))) is not None:
            return prior.view()  # a retried start: the same session, never a second pod
        if self.kill_switch():
            raise ApiError(409, "policy_refused", "the agent kill switch is on", reason="agents_stopped")
        self._sweep()
        now = self.gw.clock()
        with self._lock:
            live = [s for s in self.sessions.values() if s.state != "ended" and s.owner["id"] == p.id]
            if len(live) >= self.cfg.max_sessions_per_agent:
                raise ApiError(409, "conflict", f"at most {self.cfg.max_sessions_per_agent} open sessions per agent; end one first",
                               reason="too_many_sessions")
            s = Session(id="abs_" + uuid.uuid4().hex[:24], owner=p.as_dict(), created_at=now,
                        expires_at=now + timedelta(seconds=self.cfg.session_ttl_s),
                        max_pages=min(max_pages or self.cfg.max_pages, self.cfg.max_pages_cap),
                        control_token=secrets.token_urlsafe(32), proxy_token=secrets.token_urlsafe(32))
            self.sessions[s.id] = s
            if idem:
                self._starts[(p.id, idem)] = s.id
        hub = list(self.hub())
        proxy_host = self.cfg.proxy_host or (hub[0].split("/")[0] if hub else "")
        proxy_port = (self.proxy.port if self.proxy is not None else None) or self.cfg.proxy_port
        try:
            if not proxy_host:
                raise PodError("no hub address is known for the egress proxy; the pod would have no way out")
            base = [namespace_doc(self.cfg.namespace),
                    *policy_docs(self.cfg.namespace, hub, self.cfg.control_port, proxy_port)]
            docs = session_docs(self.cfg.namespace, s.id, image=self.cfg.image or "", control_token=s.control_token,
                                proxy_url=f"http://{s.id}:{s.proxy_token}@{proxy_host}:{proxy_port}",
                                control_port=self.cfg.control_port, lifetime_s=self.cfg.session_ttl_s,
                                max_pages=s.max_pages)
            self.pods.start(docs, base)
        except PodError as exc:
            with self._lock:
                self.sessions.pop(s.id, None)
            raise ApiError(503, "unavailable", f"the browser pod did not start: {exc}"[:500], reason="browser_unavailable",
                           retry_after_s=30) from None
        self.gw.audit.append("agentbrowser.session.started", p.as_dict(), None,
                             {"session_id": s.id, "max_pages": s.max_pages, "expires_at": iso(s.expires_at)})
        return s.view()

    def _end(self, s: Session, reason: str, by: dict | None) -> None:
        with self._lock:
            if s.state == "ended":
                return
            s.state, s.ended_reason = "ended", reason
        if self.proxy is not None:
            self.proxy.close_session(s.id)
        try:
            self.pods.stop(s.id)
        except PodError:  # activeDeadlineSeconds still ends the pod; the proxy already refuses it
            pass
        self.gw.audit.append("agentbrowser.session.ended", by, None,
                             {"session_id": s.id, "agent": s.owner["id"], "reason": reason, "pages": s.pages})

    def end(self, p: Principal, sid: str) -> dict:
        self.caller(p, "end an agent browser session")
        s = self._get(p, sid)
        self._end(s, "ended_by_owner" if p.is_owner and s.owner["id"] != p.id else "ended", p.as_dict())
        return s.view()

    def end_all(self, reason: str) -> None:
        for s in list(self.sessions.values()):
            self._end(s, reason, None)

    # ---- visits -----------------------------------------------------------------------------
    def _audit_visit(self, s: Session, url: str, kind: str, decision: str, reason: str | None,
                     action_id: str | None = None) -> None:
        self.gw.audit.append("agentbrowser.visit", s.owner, action_id,
                             {"session_id": s.id, "agent": s.owner["id"], "url": url, "kind": kind,
                              "decision": decision, **({"reason": reason} if reason else {})})

    def visit(self, p: Principal, sid: str, url: str, kind: str, approval_id: str | None,
              idem: str | None = None) -> tuple[dict, int]:
        self.caller(p, "visit a page in the agent browser")
        s = self._get(p, sid)
        if idem and idem in s.replies:  # a retried visit: the same answer, no second page load or count
            body, out, status = s.replies[idem]
            if body != (url, kind, approval_id):
                raise ApiError(409, "conflict", "Idempotency-Key was already used for a different visit")
            return out, status
        out, status = self._visit(p, s, url, kind, approval_id)
        if idem and len(s.replies) < 100:
            s.replies[idem] = ((url, kind, approval_id), out, status)
        return out, status

    def _visit(self, p: Principal, s: Session, url: str, kind: str, approval_id: str | None) -> tuple[dict, int]:
        self._sweep()
        if s.state == "ended":
            raise ApiError(409, "expired", f"this session has ended ({s.ended_reason})", reason=s.ended_reason)
        try:
            t = policy.parse(url)
        except policy.UrlRefused as exc:
            raise ApiError(422, "conflict", f"url: {exc}") from None
        agent = s.owner["id"]
        principal = p  # the caller files the request (an owner looking at an agent's session files it as the owner)
        if not policy.allowed(t.host, self.entries(agent)):
            action, _ = self._file_site(principal, agent, t.host, f"the agent browser was asked to open {t.url}")
            self._audit_visit(s, t.url, kind, "approval_required", "site_not_approved", action["id"])
            return self._approval(s, "site_not_approved", action), 202
        reason = policy.classify(t, kind)
        if reason is not None and not self._step_granted(s, agent, kind, reason, t, approval_id):
            plan, sha = policy.step_plan(agent, s.id, kind, reason, t.url, t.query, t.full_sha256)
            action, _ = self.gw.actions.request_feature(
                principal, STEP_ACTION, {**plan, "plan_sha256": sha},
                idempotency_key=_key("step", s.id, sha, str(len(s.used_steps))), expires_at=self.gw.clock() + STEP_TTL,
                reason=f"{reason.replace('_', '-')} step in the agent browser", pending_cap=True)
            self._audit_visit(s, t.url, kind, "approval_required", reason, action["id"])
            return self._approval(s, reason, action), 202
        with self._lock:
            if s.pages >= s.max_pages:
                over = True
            else:
                over, s.pages = False, s.pages + 1
        if over:
            self._audit_visit(s, t.url, kind, "refused", "page_budget_exhausted")
            raise ApiError(409, "conflict", f"this session's page budget ({s.max_pages}) is used up; start a new session",
                           reason="page_budget_exhausted")
        self._audit_visit(s, t.url, kind, "allowed", None, approval_id if reason else None)
        return {"decision": "allowed", "url": t.url, "session": s.view(), "page": self._open(s, t, kind)}, 200

    def _approval(self, s: Session, reason: str, action: dict) -> dict:
        return {"decision": "approval_required", "reason": reason, "session": s.view(), "action": action}

    def _step_granted(self, s: Session, agent: str, kind: str, reason: str, t: policy.Target,
                      approval_id: str | None) -> bool:
        if not approval_id or approval_id in s.used_steps:
            return False
        a = self.gw.repo.get(approval_id)
        _, sha = policy.step_plan(agent, s.id, kind, reason, t.url, t.query, t.full_sha256)
        if a is None or a.type != STEP_ACTION or a.state != "succeeded" or a.params.get("plan_sha256") != sha:
            return False
        with self._lock:
            if approval_id in s.used_steps:
                return False
            s.used_steps.add(approval_id)  # once: a second visit needs a second approval
        return True

    def _open(self, s: Session, t: policy.Target, kind: str) -> dict:
        try:
            ip = self.pods.address(s.id)
        except PodError:
            ip = None
        if ip is None:
            raise ApiError(503, "unavailable", "the session's browser is still starting; try again shortly",
                           reason="browser_starting", retry_after_s=5)
        s.state = "running"
        try:
            page = self.control(ip, self.cfg.control_port, s.control_token, {"url": t.full, "kind": kind})
        except (OSError, ValueError) as exc:
            raise ApiError(503, "unavailable", f"the session's browser did not answer: {exc.__class__.__name__}",
                           reason="browser_unavailable", retry_after_s=5) from None
        final = page.get("final_url")
        try:
            final = policy.parse(final).url if isinstance(final, str) else None
        except policy.UrlRefused:
            final = None
        return {"status": page.get("status"), "final_url": final, "title": str(page.get("title") or "")[:300],
                "text": str(page.get("text") or "")[:20000]}

    # ---- the proxy's question ---------------------------------------------------------------
    def authorize_connect(self, sid: str, token: str, host: str, port: int) -> str | None:
        s = self.sessions.get(sid)
        if s is None or not hmac.compare_digest(s.proxy_token, token or ""):
            return "unknown_session"
        reason: str | None = None
        if s.state == "ended" or self.gw.clock() >= s.expires_at:
            reason = "session_ended"
        elif self.kill_switch():
            reason = "agents_stopped"
        elif port != 443:
            reason = "port_not_allowed"
        else:
            try:
                ok = policy.allowed(policy.normalize_host(host), self.entries(s.owner["id"]))
            except policy.UrlRefused:
                ok = False
            reason = None if ok else "site_not_approved"
        if reason and host not in s.refused_hosts and len(s.refused_hosts) < 200:
            s.refused_hosts.add(host)
            self.gw.audit.append("agentbrowser.egress_refused", s.owner, None,
                                 {"session_id": s.id, "agent": s.owner["id"], "host": host[:253], "reason": reason})
        return reason


def _control_call(ip: str, port: int, token: str, body: dict) -> dict:
    """POST /goto on the pod's control port; the pod answers {status, final_url, title, text}."""
    host = f"[{ip}]" if ":" in ip else ip
    req = urllib.request.Request(f"http://{host}:{port}/goto", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:  # noqa: S310 (a pod address on the cluster network)
            out = json.loads(r.read(2_000_000))
    except urllib.error.HTTPError as exc:
        raise OSError(f"browser pod answered {exc.code}") from None
    if not isinstance(out, dict):
        raise ValueError("browser pod answered something that is not an object")
    return out
