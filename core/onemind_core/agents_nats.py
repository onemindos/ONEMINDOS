# SPDX-License-Identifier: Apache-2.0
"""#627: which AI agents may use the hub's NATS bus, and as whom (natsconf.py, account AGENTS).

In plain words: an agent that wants to talk on the bus (the Synadia Agent Protocol: answer prompts,
send status and a heartbeat) needs its own NATS *user*. The owner registers the agent's public key
(an nkey "U..."; the agent keeps the seed and it never reaches the gateway). The gateway then writes
one AGENTS user for it into the accounts file, and the hub's NATS reloads, exactly as it does when a
node joins. The owner removes the key, or cancels the agent, and the user is gone: the agent is
refused on its next connect.

What a registered agent gets is talk, not power: its own agents.* subjects, its own inbox, and
onemind.request.agent.<token>.<type> to ask for something, which a person approves. It gets no tools
(MCP grants are separate and start empty), no event, asset, node or audit subject and no JetStream.
Only `agent:<token>` principals with a one-token name qualify (natsconf.AGENT_TOKEN_RE).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from .audit import AuditLog
from .auth import Principal
from .errors import ApiError
from .ledger import Base, iso
from .natsconf import AGENT_TOKEN_RE, AGENTS_ACCOUNT, AgentUser, is_user_public_nkey
from .store import Database

__all__ = ["AgentNatsKeyRow", "AgentNatsKeys", "agent_token", "agent_users"]


class AgentNatsKeyRow(Base):
    """Feature "agents" (agent_principals.SCHEMA): a new table, so create_all adds it at this shape."""
    __tablename__ = "agents_nats_keys"
    principal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    nkey: Mapped[str] = mapped_column(String(56))
    added_by: Mapped[str] = mapped_column(String(100))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def agent_token(principal_id: str) -> str:
    """`agent:hermes` -> `hermes`. Anything else (a static id, a dotted name) has no NATS user."""
    if not isinstance(principal_id, str) or not principal_id.startswith("agent:"):
        raise ValueError("only an agent:<name> principal gets a NATS user")
    return _token(principal_id)


def _token(principal_id: str) -> str:
    token = principal_id[len("agent:"):]
    if not AGENT_TOKEN_RE.match(token):
        raise ValueError("a NATS agent name is one token of a-z, 0-9, '_' and '-' (no dots)")
    return token


def agent_users(db: Database) -> list[AgentUser]:
    """Every registered agent key, for natsconf.write_accounts (FabricService.write_accounts)."""
    with db.session() as s:
        rows = list(s.scalars(select(AgentNatsKeyRow).order_by(AgentNatsKeyRow.principal_id)))
    return [AgentUser(_token(r.principal_id), r.nkey) for r in rows]


class AgentNatsKeys:
    """The owner's register and remove operations. `apply` rewrites the accounts file (or is None
    when this box has no hub NATS); it raises OSError when the file cannot be written."""

    def __init__(self, db: Database, audit: AuditLog, clock, apply=None):
        self.db, self.audit, self.clock, self.apply = db, audit, clock, apply

    def _deny(self, p: Principal, what: str) -> ApiError:
        self.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")

    @staticmethod
    def _pid(name: str) -> tuple[str, str]:
        try:
            return name, agent_token(name)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None

    def _row(self, pid: str) -> AgentNatsKeyRow | None:
        with self.db.session() as s:
            return s.get(AgentNatsKeyRow, pid)

    def view(self, pid: str) -> dict:
        row = self._row(pid)
        token = _token(pid)
        user = AgentUser(token, row.nkey) if row else None
        return {
            "id": pid,
            "account": AGENTS_ACCOUNT,
            "nkey": row.nkey if row else None,
            "added_at": iso(row.added_at) if row else None,
            "inbox_prefix": f"_INBOX_{token}",
            "subjects": user.subjects() if user else [],
            "request_subject": user.request_subject() if user else None,
            "tools": [],  # talk is not power: tools come only from MCP grants, which start empty
        }

    def _rewrite(self) -> None:
        if self.apply is None:
            return
        try:
            self.apply()
        except OSError:
            raise ApiError(503, "unavailable", "the NATS accounts file could not be written; try again",
                           reason="nats_accounts_unwritable") from None

    def get(self, p: Principal, name: str) -> dict:
        if not p.is_owner:
            raise self._deny(p, "read an agent NATS key")
        pid, _ = self._pid(name)
        return self.view(pid)

    def set(self, p: Principal, name: str, nkey: str) -> dict:
        if not p.is_owner:
            raise self._deny(p, "set an agent NATS key")
        pid, _ = self._pid(name)
        if not is_user_public_nkey(nkey):
            raise ApiError(422, "conflict", "nkey: a NATS user public key (U followed by 55 base32 characters)")
        now = self.clock()
        with self.db.session.begin() as s:
            s.merge(AgentNatsKeyRow(principal_id=pid, nkey=nkey, added_by=p.id, added_at=now))
        self._rewrite()
        self.audit.append("agent.nats_key_set", p.as_dict(), None, {"agent": pid, "nkey": nkey})
        return self.view(pid)

    def remove(self, p: Principal | None, name: str, *, why: str = "removed") -> dict:
        """Drop the key and rewrite the file. `p` None is the gateway itself (an agent cancel)."""
        if p is not None and not p.is_owner:
            raise self._deny(p, "remove an agent NATS key")
        pid, _ = self._pid(name)
        with self.db.session.begin() as s:
            gone = s.execute(delete(AgentNatsKeyRow).where(AgentNatsKeyRow.principal_id == pid)).rowcount or 0
        if gone:
            self._rewrite()
            self.audit.append("agent.nats_key_removed", p.as_dict() if p else None, None, {"agent": pid, "why": why})
        return self.view(pid)
