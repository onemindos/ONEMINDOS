# SPDX-License-Identifier: Apache-2.0
"""Immutable principal ids (gateway permissions PR 7, gap 19, fix 12 part 1; D-027, D-028).

A display id such as `agent:notes` or `plugin:photos` can be used again: an app installed later
with the same id, or a person who mints a new agent token under an old name, would become the same
`agent:<id>` and inherit every standing approval that names it. So the gateway gives each agent and
plugin principal a permanent id (`prn_<ULID>`) the first time it is seen, and a standing approval
binds to that id and the person who owns it, not to the display id alone.

- **Never reused.** When an identity ends, its record is *retired* and the next principal with the
  same display id gets a new `prn_` id. A rule bound to the old one never matches again.
- **What ends an identity:** revoking one of its tokens (an owner who revokes a token is saying "this
  credential may be in the wrong hands", so its rules stop with it), cancelling the agent, disabling
  its owning person, removing the app that issued it, or retiring an app's plugin credential.
  Rotating a token does not end it (the same holder proves the old secret).
- **Persons and automations** already have ids that are never reused (`person:<user ULID>`,
  `automation:<rule ULID>`), so only agents and plugins are registered here.
- **Collision at app install:** an app whose agent principal (`agent:<app-id>`) is already held by
  a personal agent token or a static-file principal is refused (`collision`), so it never inherits
  that agent's rules or audit trail.

Table `principals_registry` (feature "principals"; new table, so create_all adds it at this shape).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .audit import AuditLog
from .ledger import Base, iso, utc
from .store import Database, FeatureSchema

SCHEMA = FeatureSchema("principals")

BOUND_KINDS = frozenset({"agent", "plugin"})


class PrincipalRow(Base):
    __tablename__ = "principals_registry"
    uid: Mapped[str] = mapped_column(String(40), primary_key=True)  # prn_<ULID>, never reused
    name: Mapped[str] = mapped_column(String(100), index=True)  # agent:notes, plugin:photos
    kind: Mapped[str] = mapped_column(String(16))
    owner_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(16))  # identity | app | plugin | file | seen
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)


def display_key(requested_by: dict) -> str:
    """`kind:id` for a requester; static-file tokens carry a bare id (`hermes`)."""
    kind, pid = str(requested_by.get("kind", "")), str(requested_by.get("id", ""))
    return pid if pid.startswith(kind + ":") else f"{kind}:{pid}"


def bound_kind(name: str) -> bool:
    return name.partition(":")[0] in BOUND_KINDS


def _json(r: PrincipalRow) -> dict:
    return {"uid": r.uid, "name": r.name, "kind": r.kind, "owner_user_id": r.owner_user_id, "source": r.source,
            "created_at": iso(utc(r.created_at)), "retired_at": iso(utc(r.retired_at)) if r.retired_at else None,
            "retired_reason": r.retired_reason}


class PrincipalRegistry:
    """Permanent ids for agent and plugin principals. One live record per display id at a time."""

    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime],
                 file_ids: Callable[[], set[str]] = set):
        self.db, self.audit, self.clock = db, audit, clock
        self.file_ids = file_ids
        self._lock = threading.RLock()  # one gateway process per ledger database (as agent_stop.py)
        # PR 9: fn(display id, reason) when an identity or its credential changes; standing approvals that
        # name it are suspended until an approver re-confirms them (design §3.6.2 item 7).
        self.listeners: list[Callable[[str, str], None]] = []

    def notify(self, name: str, reason: str) -> None:
        for fn in list(self.listeners):
            try:
                fn(name, reason)
            except Exception:  # a listener failure must not undo the change that caused it
                import logging

                logging.getLogger("onemind.principals").exception("principal listener failed")

    def live(self, name: str) -> dict | None:
        """The live record of a display id, or None (no identity holds it now)."""
        with self.db.session() as s:
            r = self._live_row(s, name)
            return _json(r) if r else None

    @staticmethod
    def _live_row(s: Session, name: str) -> PrincipalRow | None:
        return s.scalars(select(PrincipalRow).where(PrincipalRow.name == name, PrincipalRow.retired_at.is_(None))
                         .order_by(PrincipalRow.created_at.desc())).first()

    def register(self, name: str, *, source: str, owner_user_id: str | None = None,
                 persist: Callable[[Session], None] | None = None) -> dict:
        """Register the live identity and optionally persist its credential in the same transaction."""
        from .automation.store import new_id  # the same prefixed ULIDs as the rule ids
        from .errors import ApiError

        with self._lock, self.db.session.begin() as s:
            if persist is not None:
                persist(s)
            found = self._live_row(s, name)
            if found is not None:
                if source == "identity" and (found.source != source or found.owner_user_id != owner_user_id):
                    raise ApiError(409, "conflict", f"agent id {name!r} belongs to another principal",
                                   reason="agent_id_taken")
                return _json(found)
            row = PrincipalRow(uid=new_id("prn_"), name=name, kind=name.partition(":")[0],
                               owner_user_id=owner_user_id, source=source, created_at=self.clock())
            s.add(row)
        out = _json(row)
        self.audit.append("principal.registered", None, None,
                          {"principal_id": name, "uid": out["uid"], "source": source, "owner_user_id": owner_user_id})
        return out

    def retire(self, name: str, reason: str, *, persist: Callable[[Session], None] | None = None) -> str | None:
        """End the live identity of `name`, optionally revoking its credential in the same write."""
        with self._lock, self.db.session.begin() as s:
            if persist is not None:
                persist(s)
            found = self._live_row(s, name)
            if found is None:
                return None
            found.retired_at = self.clock()
            found.retired_reason = reason[:80]
        self.audit.append("principal.retired", None, None,
                          {"principal_id": name, "uid": found.uid, "reason": reason[:80]})
        self.notify(name, reason)
        return found.uid

    def history(self, name: str) -> list[dict]:
        with self.db.session() as s:
            return [_json(r) for r in s.scalars(select(PrincipalRow).where(PrincipalRow.name == name)
                                                .order_by(PrincipalRow.created_at))]

    def _holders(self, name: str) -> set[tuple[str, str | None, str]]:
        """Credential sources, owners and original ids behind a canonical display id."""
        from .identity.models import AgentOwnerRow, TokenRow
        from .ledger import AgentTokenRow

        kind, _, bare = name.partition(":")
        aliases = {name} if bare.startswith(kind + ":") else {name, bare}
        holders: set[tuple[str, str | None, str]] = set()
        if kind == "agent":
            holders.update(("file", None, raw) for raw in self.file_ids() & aliases)
        with self.db.session() as s:
            if kind == "agent":
                holders.update(("app", None, raw) for raw in s.scalars(select(AgentTokenRow.principal_id).where(
                    AgentTokenRow.principal_id.in_(aliases), AgentTokenRow.revoked_at.is_(None))))
            source = "plugin" if kind == "plugin" else "identity"
            local = set(s.execute(select(TokenRow.principal_id, TokenRow.owner_user_id).where(
                TokenRow.kind == kind, TokenRow.principal_id.in_(aliases), TokenRow.revoked_at.is_(None))))
            holders.update((source, owner, raw) for raw, owner in local)
            if kind == "agent" and local:
                reservation = s.get(AgentOwnerRow, name)
                if reservation is not None and any(owner != reservation.owner_user_id for _, owner in local):
                    # A stored credential also cannot override the permanent owner reservation.
                    holders.add(("identity", reservation.owner_user_id, name))
        return holders

    def credential_matches(self, kind: str, raw_id: str, source: str, owner_user_id: str | None = None) -> bool:
        name = display_key({"kind": kind, "id": raw_id})
        if self._holders(name) != {(source, owner_user_id, raw_id)}:
            return False
        found = self.live(name)
        return found is None or (found["source"], found["owner_user_id"]) == (source, owner_user_id)

    def resolve(self, name: str, *, adopt: bool = True) -> dict | None:
        """Resolve a unique holder, adopting older credentials that predate the registry."""
        with self._lock:
            holders = self._holders(name)
            if len(holders) != 1:
                return None
            source, owner_user_id, _ = next(iter(holders))
            found = self.live(name)
            if found is None:
                return self.register(name, source=source, owner_user_id=owner_user_id) if adopt else None
            return found if (found["source"], found["owner_user_id"]) == (source, owner_user_id) else None

    def collision(self, name: str) -> str | None:
        """Why an app may not take `name` as its agent principal, or None."""
        sources = {source for source, _, _ in self._holders(name)}
        if "file" in sources:
            return "a principal in the tokens file"
        r = self.live(name)
        if r is not None and r["source"] not in ("app",):
            return "a personal agent" if r["source"] == "identity" else f"a {r['source']} principal"
        if "identity" in sources:
            return "a personal agent"
        return None
