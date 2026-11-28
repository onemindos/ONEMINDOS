# SPDX-License-Identifier: Apache-2.0
"""Stored taint and declared outside inputs (gateway permissions PR 6, gap 16, F-11 = a, D-027).

Two small tables on the shared ledger database, feature "agents" (agent_principals.SCHEMA: new
tables, so create_all adds them at this shape):

- `agents_taint_marks`: who read third-party text through the gateway, and until when. The TaintLedger
  writes every mark here and reloads the live ones at start, so a restart no longer forgets them
  and the one-hour TTL keeps running (taint.py).
- `agents_inputs`: what an agent can read that the gateway cannot see (web, email, files, a
  chat host with many chats on one token). Such an agent is *exposed*: tainted all the time. Every
  agent or plugin principal is exposed by default (D-028: an agent that reads outside text on its
  own is always treated as tainted): an installed app's agent, a plugin, an identity-token agent,
  an MCP client such as Claude Code or Codex, the v0 token. Only the owner may declare otherwise,
  including "none" (an agent never lowers its own taint). A person or an automation rule is not
  exposed; a caller whose kind is unknown is, so a missing kind fails closed.

`accept_injection_risk` lists action types the owner accepts the risk for, one exact write type at a
time. It is recorded, owner only and behind the passkey step-up, and shown to the owner, but it
loosens nothing yet: an exposed agent stays tainted, so no standing approval may accept its
requests, until the rules engine (permission design PRs 8 and 11, which add the L2 key) reads it.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .audit import AuditLog
from .auth import Principal
from .catalog import Catalog
from .errors import ApiError
from .ledger import Base, iso, utc
from .store import Database
from .taint import Exposure, Taint

INPUT_KINDS = ("web", "email", "files", "chat")
DEFAULT_APP_INPUTS = ("app",)
DEFAULT_PLUGIN_INPUTS = ("plugin",)
DEFAULT_AGENT_INPUTS = ("agent",)  # any other agent: it reads outside text on its own
# A joining node filing node.join through the fabric (§12.11): the owner checks its match code, and
# that one request is not an AI reader's. ActionService.file looks the taint up under this marker for
# that path only; it is never a principal's kind (crypto.TOKEN_KINDS), so a node token on any other
# path (POST /v1/actions with actions:request:*) still counts as exposed.
NODE_JOIN_REQUESTER = "node.join-requester"
# Not AI readers: people, the rules they wrote, and the node.join path above. Every other kind, known
# or not, including "node", counts as exposed.
NOT_EXPOSED_KINDS = frozenset({"person", "automation", NODE_JOIN_REQUESTER})
MAX_ACCEPT = 20
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,79}$")  # the same as agent_principals.NAME_RE
TYPE_RE = re.compile(r"^[a-z][a-z0-9_.]{0,79}$")


class TaintRow(Base):
    """Feature "agents": a new table, so create_all adds it at this shape."""

    __tablename__ = "agents_taint_marks"
    principal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    sources: Mapped[list] = mapped_column(JSON)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InputsRow(Base):
    __tablename__ = "agents_inputs"
    principal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    external_inputs: Mapped[list] = mapped_column(JSON)
    accept_injection_risk: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str] = mapped_column(String(100))


class TaintStore:
    """The ledger's durable side."""

    def __init__(self, db: Database):
        self.db = db

    def load(self) -> dict[str, Taint]:
        with self.db.session() as s:
            return {r.principal_id: Taint(tuple(r.sources), utc(r.since), utc(r.until)) for r in s.scalars(select(TaintRow))}

    def save(self, principal_id: str, t: Taint) -> None:
        values = {"sources": list(t.sources), "since": t.since, "until": t.until}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(TaintRow).values(principal_id=principal_id, **values)
                      .on_conflict_do_update(index_elements=[TaintRow.principal_id], set_=values))

    def delete(self, principal_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(TaintRow).where(TaintRow.principal_id == principal_id))


class AgentInputs:
    """Declared outside inputs per agent principal, and the exposure lookup the taint ledger uses.

    The declarations are cached in memory and read once at start, so this assumes one gateway
    process per ledger database (agent_stop.py assumes the same)."""

    def __init__(self, db: Database, audit: AuditLog, catalog: Catalog, clock: Callable[[], datetime]):
        self.db, self.audit, self.catalog, self.clock = db, audit, catalog, clock
        self._lock = threading.Lock()
        self._rows: dict[str, dict] = {}
        self._since = utc(clock())  # when a defaulted agent's exposure started to count
        with db.session() as s:
            for r in s.scalars(select(InputsRow)):
                self._rows[r.principal_id] = self._plain(r)

    @staticmethod
    def _plain(r: InputsRow) -> dict:
        return {"external_inputs": list(r.external_inputs), "accept_injection_risk": list(r.accept_injection_risk),
                "updated_at": utc(r.updated_at), "updated_by": r.updated_by}

    # ---- the lookup the taint ledger calls on every request --------------------------------------
    def _default(self, pid: str, kind: str | None) -> tuple[str, ...]:
        if kind in NOT_EXPOSED_KINDS:
            return ()
        if kind == "plugin" or pid.startswith("plugin:"):
            return DEFAULT_PLUGIN_INPUTS
        name = pid.partition(":")[2] if pid.startswith("agent:") else ""
        if name and name in self.catalog.load():
            return DEFAULT_APP_INPUTS
        return DEFAULT_AGENT_INPUTS

    def inputs(self, pid: str, kind: str | None = None) -> tuple[str, ...]:
        with self._lock:
            row = self._rows.get(pid)
        return tuple(row["external_inputs"]) if row is not None else self._default(pid, kind)

    def exposure(self, pid: str, kind: str | None = None) -> Exposure | None:
        names = self.inputs(pid, kind)
        if not names:
            return None
        with self._lock:
            row = self._rows.get(pid)
        return Exposure(names, row["updated_at"] if row else self._since)

    def forget(self, pid: str) -> bool:
        """The agent's identity ended (its app was removed): drop what the owner declared, so a new
        agent with the same id starts at the fail-closed default (D-028: identity change resets)."""
        with self._lock:
            had = self._rows.pop(pid, None)
        if had is None:
            return False
        with self.db.session.begin() as s:
            s.execute(delete(InputsRow).where(InputsRow.principal_id == pid))
        self.audit.append("agent.inputs.cleared", {"id": pid, "kind": "agent"}, None,
                          {"principal_id": pid, "was": had["external_inputs"], "reason": "identity_ended"})
        return True

    def loosens(self, pid: str, external_inputs: list[str], accept: list[str]) -> bool:
        """True when this declaration makes the agent less guarded than it is now (D-028: only that
        needs a person at the passkey; tightening stays at L0)."""
        before = self.view(pid)
        dropped = set(before["external_inputs"]) & set(INPUT_KINDS) - set(external_inputs)
        cleared = bool(before["external_inputs"]) and not external_inputs
        return bool(dropped or cleared or set(accept) - set(before["accept_injection_risk"]))

    # ---- owner API --------------------------------------------------------------------------------
    def view(self, pid: str) -> dict:
        with self._lock:
            row = self._rows.get(pid)
        names = self.inputs(pid)
        return {
            "id": pid,
            "external_inputs": list(names),
            "declared": row is not None,
            "exposed": bool(names),
            "permanently_tainted": bool(names),
            "accept_injection_risk": list(row["accept_injection_risk"]) if row else [],
            "accept_injection_risk_effective": False,
            "updated_at": iso(row["updated_at"]) if row else None,
            "updated_by": row["updated_by"] if row else None,
        }

    def set(self, p: Principal, pid: str, external_inputs: list[str], accept: list[str],
            via: str | None = None) -> dict:
        if not p.is_owner:
            self.audit.append("authz.denied", p.as_dict(), None,
                              {"attempted": "declare agent inputs", "principal_id": pid, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not declare what an agent reads")
        if not NAME_RE.fullmatch(pid):
            raise ApiError(422, "conflict", "agent id: a-z, 0-9, '.', '_', ':', '-'")
        names = sorted(set(external_inputs), key=INPUT_KINDS.index)
        if accept:
            from .automation import registry

            for t in accept:
                if not TYPE_RE.match(t) or not registry.known(t):
                    raise ApiError(422, "conflict", f"accept_injection_risk: unknown action type {t!r}")
                if registry.risk_of(t) != "write":
                    raise ApiError(422, "conflict", f"accept_injection_risk covers one write type at a time; "
                                                    f"{t} is {registry.risk_of(t)}")
            if not names:
                raise ApiError(422, "conflict", "accept_injection_risk only applies to an agent that reads outside text")
        accept = sorted(set(accept))
        before = self.view(pid)
        now = self.clock()
        values = {"external_inputs": names, "accept_injection_risk": accept, "updated_at": now, "updated_by": p.id}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(InputsRow).values(principal_id=pid, **values)
                      .on_conflict_do_update(index_elements=[InputsRow.principal_id], set_=values))
        with self._lock:
            self._rows[pid] = {"external_inputs": names, "accept_injection_risk": accept,
                               "updated_at": utc(now), "updated_by": p.id}
        after = self.view(pid)
        self.audit.append("agent.inputs.set", p.as_dict(), None,
                          {"principal_id": pid, "external_inputs": after["external_inputs"],
                           "was": before["external_inputs"], "accept_injection_risk": accept,
                           "was_accepting": before["accept_injection_risk"], "via": via})
        return after
