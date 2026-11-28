# SPDX-License-Identifier: Apache-2.0
"""Permission modes (gateway permissions design §3.5, §3.5.1; F-7, F-8, D-027, D-028).

Every principal has a mode: how its requests are handled once they pass the stop checks and the
hard floor (decide.py steps 1 to 6). In order, from tightest to loosest:

    locked    refused at once; its pending requests are cancelled
    ask       Always ask: every request waits for a person (the default for every new agent, app and
              person, F-7 = a)
    remember  waits, and the approval card offers "Approve and remember" (design PR 12)
    auto      a request a live rule covers goes through; everything else waits
    headless  a request a live rule covers goes through; everything else is refused at once
    bypass    T0/T1 inside a sandbox the gateway can prove (design PR 23; refused until then)

Who may change a mode (§3.5.1):
- **Tightening** (toward locked) by anyone with a say over that principal: the owner, or the person
  who owns that agent's token. No step-up (D-028: every tightening is L0).
- **Loosening** is an approver's power (the owner today). It needs an action-bound L2 approval,
  and requests are refused before the owner has enrolled a passkey (F-8, D-028).
- **Nobody loosens their own requests.** The owner's own requests run directly, as today: they
  are exempt from modes (the engine never looks up a mode for an owner, so neither a Locked nor a
  Headless household default touches them), and no mode row may be set for an owner (422
  owner_exempt). Without that an owner could lock themselves and, with no other approver in 1.0,
  nobody could undo it short of editing the database.
- An agent never changes a mode, its own included; it may read its own.

The household default (principal "*") applies to identities present when it is set. New identities
start on Always ask. An individual setting takes precedence over the household default. On upgrade,
every principal a live standing approval names is moved to auto once, audited as
`permission.mode.migrated`, so rules made before modes existed keep firing (fix 14).

Agent and plugin settings and household membership apply only to the registered identity that
held the display name when the owner set them.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import DateTime, String, delete, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..audit import AuditLog
from ..auth import Principal
from ..errors import ApiError
from ..ledger import Base, iso, utc
from ..principals import bound_kind, display_key
from ..store import Database
from .denies import SCHEMA

ORDER = ("locked", "ask", "remember", "auto", "headless", "bypass")
DEFAULT_MODE = "ask"  # F-7 = a
HOUSEHOLD = "*"
MIGRATED = "__migrated__"  # marker row: the one-time upgrade move to auto has run
INHERITANCE = "__inheritance__"  # marker row: a household default has a fixed set of members
PRINCIPAL_RE = re.compile(r"^(agent|plugin|automation|person):[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


class ModeRow(Base):
    __tablename__ = "permissions_modes"
    principal: Mapped[str] = mapped_column(String(100), primary_key=True)
    identity_uid: Mapped[str | None] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(16))
    set_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ModeMemberRow(Base):
    __tablename__ = "permissions_mode_members"
    principal: Mapped[str] = mapped_column(String(100), primary_key=True)
    identity_uid: Mapped[str | None] = mapped_column(String(100))


@SCHEMA.step(2, "bind modes and household membership to permanent identities")
def _bind_modes(conn: Connection) -> None:
    for table in ("permissions_modes", "permissions_mode_members"):
        if "identity_uid" not in {c["name"] for c in inspect(conn).get_columns(table)}:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN identity_uid VARCHAR(100)"))


def _matches(name: str, uid: str | None, row: ModeRow | ModeMemberRow | None, mode: str) -> bool:
    if row is None:
        return False
    if row.identity_uid is not None:
        return row.identity_uid == uid
    # Legacy names can keep a restriction until the owner rebinds it. A legacy approval mode
    # cannot be assigned to whichever credential now holds that display name.
    return mode == "locked" or not bound_kind(name)


def loosens(old: str, new: str) -> bool:
    return ORDER.index(new) > ORDER.index(old)


class ModeStore:
    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime]):
        self.db, self.audit, self.clock = db, audit, clock
        self._writes = threading.RLock()  # one gateway process owns the ledger, as for agent input declarations
        self.household_members: Callable[[], dict[str, str]] = dict
        self.identity_of: Callable[[str], str | None] = lambda name: None if bound_kind(name) else name
        self.bind_identity: Callable[[str], str | None] = lambda name: self.identity_of(name)
        self.owned_by: Callable[[str], set[str]] = lambda _uid: set()  # person id -> agents they own
        self.cancel_pending: Callable[[str, Principal], int] = lambda _name, _by: 0  # Locked cancels these
        self.owner_passkey: Callable[[], bool] = lambda: True  # F-8, set by the router
        # §3.5.1: is this display key an owner ("person:<id>" whose role is owner)? Owners are exempt.
        self.is_owner: Callable[[str], bool] = lambda _name: False

    # ---- reads -----------------------------------------------------------------------------------
    def _row(self, principal: str) -> ModeRow | None:
        with self.db.session() as s:
            return s.get(ModeRow, principal)

    def default(self) -> str:
        r = self._row(HOUSEHOLD)
        return r.mode if r is not None and r.mode in ORDER else DEFAULT_MODE

    def effective(self, name: str, kind: str | None = None) -> str:
        uid = self.identity_of(name)
        with self.db.session() as s:
            return self._effective(s, name, uid, s.get(ModeRow, name))

    @staticmethod
    def _effective(s, name: str, uid: str | None, r: ModeRow | None) -> str:
        if r is not None and _matches(name, uid, r, r.mode) and r.mode in ORDER:
            return r.mode
        default = s.get(ModeRow, HOUSEHOLD)
        if default is not None and _matches(name, uid, s.get(ModeMemberRow, name), default.mode):
            return default.mode
        return DEFAULT_MODE

    def view(self, name: str) -> dict:
        return self._view(name, self.identity_of(name))

    def _view(self, name: str, uid: str | None) -> dict:
        with self.db.session() as s:
            r = s.get(ModeRow, name)
            if r is not None and not _matches(name, uid, r, r.mode):
                r = None
            mode = self._effective(s, name, uid, r)
        return {"principal": name, "mode": mode, "own": r is not None,
                "set_by": r.set_by if r else None, "set_at": iso(utc(r.set_at)) if r else None,
                "reason": r.reason if r else None, "household_default": self.default(),
                "owner_passkey": bool(self.owner_passkey())}

    def list(self) -> list[dict]:
        with self.db.session() as s:
            names = [n for n in s.scalars(select(ModeRow.principal)) if n not in (HOUSEHOLD, MIGRATED, INHERITANCE)]
        return [row for n in sorted(names) if (row := self.view(n))["own"]]

    # ---- who has a say ---------------------------------------------------------------------------
    @staticmethod
    def _key(p: Principal) -> str:
        return display_key(p.as_dict())

    def has_say(self, p: Principal, name: str, user_id: str | None) -> bool:
        if p.is_owner:
            return True
        return p.kind == "person" and user_id is not None and name in self.owned_by(user_id)

    def may_read(self, p: Principal, name: str, user_id: str | None) -> bool:
        return self.has_say(p, name, user_id) or self._key(p) == name

    # ---- writes ----------------------------------------------------------------------------------
    def _write(self, name: str, mode: str, by: dict | None, reason: str | None, *,
               uid: str | None = None, members: dict[str, str] | None = None) -> None:
        values = {"mode": mode, "identity_uid": uid, "set_by": by,
                  "set_at": self.clock(), "reason": (reason or None) and reason[:200]}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(ModeRow).values(principal=name, **values)
                      .on_conflict_do_update(index_elements=[ModeRow.principal], set_=values))
            if members is not None:
                s.execute(delete(ModeMemberRow))
                s.add_all(ModeMemberRow(principal=member, identity_uid=member_uid) for member, member_uid in members.items())
                s.execute(self.db.insert()(ModeRow).values(principal=INHERITANCE, **values)
                          .on_conflict_do_nothing(index_elements=[ModeRow.principal]))

    def migrate_inheritance(self) -> None:
        with self._writes:
            row = self._row(HOUSEHOLD)
            if row is not None and self._row(INHERITANCE) is None:
                # A legacy default without a membership snapshot can keep a restriction.
                # Permissive defaults require a fresh choice for agents and plugins.
                self._write(HOUSEHOLD, row.mode, row.set_by, row.reason,
                            members={name: uid for name, uid in self.household_members().items()
                                     if row.mode == "locked" or not bound_kind(name)})

    def _check_target(self, p: Principal, name: str, mode: str, user_id: str | None) -> None:
        if mode not in ORDER:
            raise ApiError(422, "conflict", f"mode is one of {', '.join(ORDER)}")
        if mode == "bypass":
            raise ApiError(422, "conflict", "bypass in a sandbox arrives with gateway permissions PR 23", reason="bypass_not_built")
        if name != HOUSEHOLD and not PRINCIPAL_RE.fullmatch(name):
            raise ApiError(422, "conflict", "principal must be <kind>:<id> for an agent, plugin, automation or person")
        if p.kind != "person":
            self._denied(p, "change a permission mode")  # an agent never changes a mode, its own included
        if name == HOUSEHOLD and not p.is_owner:
            self._denied(p, "change the household default")
        if name != HOUSEHOLD and not self.has_say(p, name, user_id):
            self._denied(p, f"change the mode of {name}")
        if name != HOUSEHOLD and name.startswith("person:") and self.is_owner(name):
            raise ApiError(422, "conflict", "the owner's own requests run directly and have no mode (design 3.5.1): "
                                            "a mode here could lock the owner out for good", reason="owner_exempt")

    def _direction(self, p: Principal, name: str, mode: str, old: str) -> str:
        if mode == old:
            return "same"
        if not loosens(old, mode):
            return "tighten"
        if not p.is_owner:  # approvers other than the owner come in 1.1 (F-5 = c)
            self._denied(p, f"loosen the mode of {name}")
        if name == self._key(p):
            self._denied(p, "loosen your own requests (a different approver sets a person's mode)")
        if not self.owner_passkey():
            raise ApiError(409, "conflict", "add a passkey first: nothing is loosened before the owner has one (F-8)",
                           reason="no_owner_passkey")
        return "loosen"

    def check_change(self, p: Principal, name: str, mode: str, user_id: str | None) -> str:
        """'tighten' | 'loosen' | 'same' for this change, or raise."""
        self._check_target(p, name, mode, user_id)
        old = self.default() if name == HOUSEHOLD else self.effective(name)
        return self._direction(p, name, mode, old)

    def change(self, p: Principal, name: str, mode: str, reason: str | None, user_id: str | None,
               request_loosening: Callable[[dict], dict]) -> dict:
        with self._writes:
            self._check_target(p, name, mode, user_id)
            uid = self.bind_identity(name)
            before = self._snapshot(name, uid)
            direction = self._direction(p, name, mode, before["mode"])
            if uid is None and direction != "same":
                raise ApiError(409, "conflict", "there is no live identity for this principal", reason="unknown_principal")
            if direction == "loosen":
                return request_loosening({"principal": name, "mode": mode, "reason": reason, "before": before,
                                          "members": self.household_members() if name == HOUSEHOLD else None})
            return self._set(p, name, mode, reason, direction, before["mode"], None, uid)

    def _snapshot(self, name: str, uid: str | None) -> dict:
        view = self.household_view() if name == HOUSEHOLD else self._view(name, uid)
        return {"identity_uid": uid, **{key: view[key] for key in ("mode", "own", "set_at")}}

    def apply_requested(self, p: Principal, params: dict) -> dict:
        name, mode = params["principal"], params["mode"]
        with self._writes:
            self._check_target(p, name, mode, None)
            uid = self.identity_of(name)
            before = self._snapshot(name, uid)
            if uid is None or before != params["before"]:
                raise ApiError(409, "stale_precondition", "the permission mode changed; request the change again")
            direction = self._direction(p, name, mode, before["mode"])
            return self._set(p, name, mode, params["reason"], direction, before["mode"], "L2", uid, params["members"])

    def _set(self, p: Principal, name: str, mode: str, reason: str | None, direction: str,
             old: str, approval: str | None, uid: str | None, members: dict[str, str] | None = None) -> dict:
        if direction == "same":
            return self.view(name) if name != HOUSEHOLD else self.household_view()
        if name == HOUSEHOLD and members is None and not loosens(DEFAULT_MODE, mode):
            members = self.household_members()
        self._write(name, mode, p.as_dict(), reason, uid=uid, members=members)
        cancelled = self.cancel_pending(name, p) if mode == "locked" and name != HOUSEHOLD else 0
        self.audit.append("permission.mode.changed", p.as_dict(), None,
                          {"principal": name, "identity_uid": uid, "from": old, "to": mode, "direction": direction,
                           "approval": approval or "none (tightening)", **({"reason": reason} if reason else {}),
                           **({"requests_cancelled": cancelled} if cancelled else {})})
        return self.view(name) if name != HOUSEHOLD else self.household_view()

    def household_view(self) -> dict:
        r = self._row(HOUSEHOLD)
        return {"principal": HOUSEHOLD, "mode": self.default(), "own": r is not None,
                "set_by": r.set_by if r else None, "set_at": iso(utc(r.set_at)) if r else None,
                "reason": r.reason if r else None, "household_default": self.default(),
                "owner_passkey": bool(self.owner_passkey())}

    def migrate(self, live_rule_principals: Callable[[], dict[str, str]],
                wildcard_rules: Callable[[], list[str]] = lambda: []) -> list[str]:
        """Once per box: every principal a live rule names moves to auto (fix 14), so an upgrade never
        silently turns a working rule off. A principal that already has a mode keeps it.

        A legacy wildcard entry (person:*, automation:*) names nobody, so nobody moves for it: such a
        rule stops firing for adults, who start on Always ask. Those rules are listed in the audit line
        (`wildcard_rules_not_moved`) so the owner can see them and set each person's mode."""
        if self._row(MIGRATED) is not None:
            return []
        moved = []
        for name, uid in sorted(live_rule_principals().items()):
            if PRINCIPAL_RE.fullmatch(name) and self._row(name) is None:
                self._write(name, "auto", None, "upgrade: it had a live standing approval", uid=uid)
                moved.append(name)
        try:
            wild = sorted(wildcard_rules())
        except Exception:  # listing them is a courtesy; the move itself must still run once
            wild = []
        self._write(MIGRATED, "auto", None, "marker")
        if moved or wild:
            self.audit.append("permission.mode.migrated", None, None,
                              {"to": "auto", "principals": moved,
                               **({"wildcard_rules_not_moved": wild} if wild else {})})
        return moved

    def _denied(self, p: Principal, what: str) -> None:
        self.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")
