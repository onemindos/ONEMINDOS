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

from sqlalchemy import DateTime, String, select, update
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

    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime]):
        self.db, self.audit, self.clock = db, audit, clock
        self._lock = threading.Lock()  # one gateway process per ledger database (as agent_stop.py)
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
            r = s.scalars(select(PrincipalRow).where(PrincipalRow.name == name, PrincipalRow.retired_at.is_(None))
                          .order_by(PrincipalRow.created_at.desc())).first()
            return _json(r) if r else None

    def register(self, name: str, *, source: str, owner_user_id: str | None = None,
                 persist: Callable[[Session], None] | None = None) -> dict:
        """Register the live identity and optionally persist its credential in the same transaction."""
        from .automation.store import new_id  # the same prefixed ULIDs as the rule ids
        from .errors import ApiError

        with self._lock, self.db.session.begin() as s:
            if persist is not None:
                persist(s)
            found = s.scalars(select(PrincipalRow).where(PrincipalRow.name == name, PrincipalRow.retired_at.is_(None))
                              .order_by(PrincipalRow.created_at.desc())).first()
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

    def retire(self, name: str, reason: str) -> str | None:
        """End the live identity of `name`; returns the retired uid, or None when none was live."""
        with self._lock:
            found = self.live(name)
            if found is None:
                return None
            with self.db.session.begin() as s:
                s.execute(update(PrincipalRow).where(PrincipalRow.uid == found["uid"], PrincipalRow.retired_at.is_(None))
                          .values(retired_at=self.clock(), retired_reason=reason[:80]))
        self.audit.append("principal.retired", None, None,
                          {"principal_id": name, "uid": found["uid"], "reason": reason[:80]})
        self.notify(name, reason)
        return found["uid"]

    def history(self, name: str) -> list[dict]:
        with self.db.session() as s:
            return [_json(r) for r in s.scalars(select(PrincipalRow).where(PrincipalRow.name == name)
                                                .order_by(PrincipalRow.created_at))]

    def _live_token(self, name: str) -> tuple[str, str | None] | None:
        """(source, owner) of a live credential minted before this registry existed, or None."""
        from .ledger import AgentTokenRow

        with self.db.session() as s:
            if s.scalars(select(AgentTokenRow.principal_id).where(AgentTokenRow.principal_id == name,
                                                                  AgentTokenRow.revoked_at.is_(None))).first():
                return "app", None
            try:  # identity is optional wiring
                from .identity.models import TokenRow

                t = s.scalars(select(TokenRow).where(TokenRow.principal_id == name, TokenRow.kind.in_(BOUND_KINDS),
                                                     TokenRow.revoked_at.is_(None)).limit(1)).first()
            except Exception:  # no identity tables
                t = None
            if t is not None:
                return ("plugin" if t.kind == "plugin" else "identity"), t.owner_user_id
        return None

    def resolve(self, name: str, file_ids: set[str]) -> dict | None:
        """The identity a new standing approval binds to: the live one, or one that holds a credential
        now (registered here on first sight). None when nothing holds `name`: a rule for an agent that
        does not exist yet would be inherited by whoever takes the id first."""
        found = self.live(name)
        if found is not None:
            return found
        if name in file_ids or name.partition(":")[2] in file_ids:
            return self.register(name, source="file")
        held = self._live_token(name)
        if held is not None:
            return self.register(name, source=held[0], owner_user_id=held[1])
        return None

    def collision(self, name: str, file_ids: set[str]) -> str | None:
        """Why an app may not take `name` as its agent principal, or None."""
        if name in file_ids or name.partition(":")[2] in file_ids:
            return "a principal in the tokens file"
        r = self.live(name)
        if r is not None and r["source"] not in ("app",):
            return "a personal agent" if r["source"] == "identity" else f"a {r['source']} principal"
        held = self._live_token(name)
        if held is not None and held[0] != "app":
            return "a personal agent" if held[0] == "identity" else f"a {held[0]} principal"
        return None
