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
- **Loosening** is an approver's power (the owner today): a fresh passkey (L1 today; D-028 sets L2,
  design PR 11), and **never before the owner has a passkey** (F-8 = a: until then every mode
  behaves as Always ask and loosening answers 409 "add a passkey first").
- **Nobody loosens their own requests.** The owner's own requests run directly, as today: they
  are exempt from modes (the engine never looks up a mode for an owner, so neither a Locked nor a
  Headless household default touches them), and no mode row may be set for an owner (422
  owner_exempt). Without that an owner could lock themselves and, with no other approver in 1.0,
  nobody could undo it short of editing the database.
- An agent never changes a mode, its own included; it may read its own.

The household default (principal "*") is what a principal without its own row gets. On upgrade,
every principal a live standing approval names is moved to auto once, audited as
`permission.mode.migrated`, so rules made before modes existed keep firing (fix 14).

Table `permissions_modes` (feature "permissions"; new table, so create_all adds it at this shape).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..audit import AuditLog
from ..auth import Principal
from ..errors import ApiError
from ..ledger import Base, iso, utc
from ..principals import display_key
from ..store import Database

ORDER = ("locked", "ask", "remember", "auto", "headless", "bypass")
DEFAULT_MODE = "ask"  # F-7 = a
HOUSEHOLD = "*"
MIGRATED = "__migrated__"  # marker row: the one-time upgrade move to auto has run
PRINCIPAL_RE = re.compile(r"^(agent|plugin|automation|person):[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


class ModeRow(Base):
    __tablename__ = "permissions_modes"
    principal: Mapped[str] = mapped_column(String(100), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))
    set_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


def loosens(old: str, new: str) -> bool:
    return ORDER.index(new) > ORDER.index(old)


class ModeStore:
    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime]):
        self.db, self.audit, self.clock = db, audit, clock
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
        r = self._row(name)
        return r.mode if r is not None and r.mode in ORDER else self.default()

    def view(self, name: str) -> dict:
        r = self._row(name)
        return {"principal": name, "mode": self.effective(name), "own": r is not None,
                "set_by": r.set_by if r else None, "set_at": iso(utc(r.set_at)) if r else None,
                "reason": r.reason if r else None, "household_default": self.default(),
                "owner_passkey": bool(self.owner_passkey())}

    def list(self) -> list[dict]:
        with self.db.session() as s:
            names = [n for n in s.scalars(select(ModeRow.principal)) if n not in (HOUSEHOLD, MIGRATED)]
        return [self.view(n) for n in sorted(names)]

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
    def _write(self, name: str, mode: str, by: dict | None, reason: str | None) -> None:
        values = {"mode": mode, "set_by": by, "set_at": self.clock(), "reason": (reason or None) and reason[:200]}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(ModeRow).values(principal=name, **values)
                      .on_conflict_do_update(index_elements=[ModeRow.principal], set_=values))

    def check_change(self, p: Principal, name: str, mode: str, user_id: str | None) -> str:
        """'tighten' | 'loosen' | 'same' for this change, or raise. Called before any step-up."""
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
        old = self.default() if name == HOUSEHOLD else self.effective(name)
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

    def set(self, p: Principal, name: str, mode: str, reason: str | None, direction: str, approval: str | None) -> dict:
        old = self.default() if name == HOUSEHOLD else self.effective(name)
        if direction == "same":
            return self.view(name) if name != HOUSEHOLD else self.household_view()
        self._write(name, mode, p.as_dict(), reason)
        cancelled = self.cancel_pending(name, p) if mode == "locked" and name != HOUSEHOLD else 0
        self.audit.append("permission.mode.changed", p.as_dict(), None,
                          {"principal": name, "from": old, "to": mode, "direction": direction,
                           "approval": approval or "none (tightening)", **({"reason": reason} if reason else {}),
                           **({"requests_cancelled": cancelled} if cancelled else {})})
        return self.view(name) if name != HOUSEHOLD else self.household_view()

    def household_view(self) -> dict:
        r = self._row(HOUSEHOLD)
        return {"principal": HOUSEHOLD, "mode": self.default(), "own": r is not None,
                "set_by": r.set_by if r else None, "set_at": iso(utc(r.set_at)) if r else None,
                "reason": r.reason if r else None, "household_default": self.default(),
                "owner_passkey": bool(self.owner_passkey())}

    def migrate(self, live_rule_principals: Callable[[], set[str]],
                wildcard_rules: Callable[[], list[str]] = lambda: []) -> list[str]:
        """Once per box: every principal a live rule names moves to auto (fix 14), so an upgrade never
        silently turns a working rule off. A principal that already has a mode keeps it.

        A legacy wildcard entry (person:*, automation:*) names nobody, so nobody moves for it: such a
        rule stops firing for adults, who start on Always ask. Those rules are listed in the audit line
        (`wildcard_rules_not_moved`) so the owner can see them and set each person's mode."""
        if self._row(MIGRATED) is not None:
            return []
        moved = []
        for name in sorted(live_rule_principals()):
            if PRINCIPAL_RE.fullmatch(name) and self._row(name) is None:
                self._write(name, "auto", None, "upgrade: it had a live standing approval")
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
