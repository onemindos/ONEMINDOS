# SPDX-License-Identifier: Apache-2.0
"""Verification levels, with state (D-028; design 3.11): the owner-editable table, the trusted key
models, and the level an approval or an owner change needs. levels.py holds the pure rules.

Writes go through the approval queue (BUILDER-BRIEFING item 6): changing a row files
`verification.requirement.set`, trusting a model files `authenticator.allowlist.add`, and an owner
approves each with a key at the level the table asks for (L2 by default). Removing a trusted model
only tightens, so it is a direct owner call.

Before the household has its first proven key (open question N-1 = b, founder 2026-11-25: "go with your
recommendations on gateway and nats"), an L2 requirement is met by an L1 key **plus** the code the box's
own screen shows (presence.py), and every answer says `grace: true`. Remotely it still needs L2.
Physical actions, turning the motion lockout off and any L3 opt-in are never eased.

The grace is one-way: once any owner has held a proven key, a household flag (`proven_key_seen`) is set
and the grace never comes back, not by deleting keys, removing a trusted model or demoting an owner.
Without a proven key after that, L2 actions need a recovery path (design 3.13; until it lands, an owner
at the box can enrol a new key or revoke a lost one) instead of falling back to L1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..errors import ApiError
from . import levels as lv
from .models import HouseholdFlagRow, PasskeyRow, TrustedModelRow, VerificationLevelRow, iso

if TYPE_CHECKING:
    from ..actions import Action
    from .service import IdentityService

SET_TYPE = "verification.requirement.set"
PROVEN_SEEN = "proven_key_seen"
ADD_MODEL_TYPE = "authenticator.allowlist.add"


class RequirementParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=80, description="A row id from GET /v1/verification-requirements, "
                                                              "or type:<action type>")
    level: str = Field(pattern=r"^L[0-3]$")


class TrustedModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aaguid: str = Field(min_length=32, max_length=36)
    name: str = Field(min_length=1, max_length=100)
    roots: list[Annotated[str, Field(max_length=8192)]] = Field(min_length=1, max_length=4,
                                                                description="PEM attestation root certificates")
    user_verification: list[Annotated[str, Field(max_length=40)]] = Field(min_length=1, max_length=16,
                                         description="FIDO MDS user verification methods, e.g. fingerprint_internal")


class Verification:
    def __init__(self, svc: IdentityService):
        self.svc = svc
        self.repo = svc.repo
        path = svc.cfg.allowlist_file or lv.SHIPPED_ALLOWLIST
        self.shipped = {m.aaguid: m for m in lv.load_file(path)}

    # ---- trusted models ----------------------------------------------------------------------------
    def models(self) -> dict[str, lv.Model]:
        out = dict(self.shipped)
        for r in self.repo.all(select(TrustedModelRow)):
            out.setdefault(r.aaguid, lv.Model(r.aaguid, r.name, tuple(x.encode() for x in r.roots),
                                              tuple(r.user_verification), "owner"))
        return out

    def roots_for(self, aaguid: str) -> list[bytes]:
        m = self.models().get(aaguid)
        return list(m.roots) if m else []

    def cred_level(self, cred: PasskeyRow, models: dict | None = None) -> int:
        """The level a stored credential meets now: its enrolment level, dropped to L1 when its model
        has since left the allow-list. Rows from before verification levels count as L1."""
        have = lv.rank(cred.level) if cred.level in lv.LEVELS else 1
        if have >= 2 and (cred.aaguid or "") not in (models if models is not None else self.models()):
            return 1
        return have

    def household_level(self) -> int:
        """The strongest level any active owner's key meets (0 when no owner has a passkey)."""
        owners = self.svc.active_owner_ids()
        models = self.models()
        rows = self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id.in_(owners))) if owners else []
        return max((self.cred_level(r, models) for r in rows), default=0)

    # ---- the one-way latch (the grace never returns) ---------------------------------------------------
    def latched(self) -> bool:
        return self.repo.get(HouseholdFlagRow, PROVEN_SEEN) is not None

    def note_proven(self, why: str) -> bool:
        """Set the latch when an owner holds a proven key now (after an enrolment or a trusted model is
        added). Returns whether the household is past the grace. Idempotent."""
        if self.latched():
            return True
        if self.household_level() < 2:
            return False
        try:
            self.repo.add(HouseholdFlagRow(key=PROVEN_SEEN, set_at=self.svc.now(), detail=why[:200]))
        except Exception:  # noqa: BLE001 - a concurrent first writer already set it
            if not self.latched():
                raise
            return True
        self.svc.emit("auth", "grace.ended", {"why": why[:200]})
        return True

    def recovery_needed(self) -> bool:
        """A proven key existed and none is left: L2 actions wait for a recovery path (design 3.13)."""
        return self.latched() and self.household_level() < 2

    # ---- the table ---------------------------------------------------------------------------------
    def overrides(self) -> dict[str, str]:
        return {r.key: r.level for r in self.repo.all(select(VerificationLevelRow))}

    def row_level(self, key: str, overrides: dict | None = None) -> int:
        o = self.overrides() if overrides is None else overrides
        return lv.rank(o.get(key) or lv.bounds(key)[0])

    def in_grace(self) -> bool:
        """No owner has ever held a proven key (and the grace is on). Checks, and sets, the latch."""
        return self.svc.cfg.l2_grace and not self.note_proven("household_level")

    def grace(self, need: int, strict: bool) -> bool:
        return need == 2 and not strict and self.in_grace()

    def effective(self, need: int, strict: bool) -> tuple[int, bool]:
        """(level actually asked for, whether the no-proven-key grace eased it). Eased means an L1 key
        **plus** the code on the box's own screen (N-1 = b): callers must ask for both."""
        if self.grace(need, strict):
            return 1, True
        return need, False

    def for_row(self, key: str) -> tuple[int, bool]:
        """(need, strict) for an owner route's row."""
        return self.row_level(key), lv.ROWS[key].strict

    def for_action(self, action: dict) -> tuple[int, bool, str]:
        """(need, strict, deciding row) to approve this action."""
        from ..automation import registry  # late, as in actions.py

        t = str(action.get("type"))
        risk = action.get("risk")
        if risk is None and registry.known(t):
            risk = registry.risk_of(t, action.get("params") or {})
        o = self.overrides()
        rows = [lv.RISK_TIER.get(str(risk), "tier.T3")]  # an unknown risk is judged as destructive
        if self.svc.gw.actions.is_physical(t):
            rows.append("tier.P")
        if t in lv.TYPE_ROWS:
            rows.append(lv.TYPE_ROWS[t])
        best = max(rows, key=lambda k: self.row_level(k, o))
        need = self.row_level(best, o)
        type_key = lv.TYPE_KEY_PREFIX + t
        if type_key in o and lv.rank(o[type_key]) > need:
            best, need = type_key, lv.rank(o[type_key])
        strict = need >= 3 or any(lv.ROWS[k].strict for k in rows)
        return need, strict, best

    def table(self) -> dict:
        o = self.overrides()
        rows = []
        for key, r in lv.ROWS.items():
            rows.append({"key": key, "label": r.label, "default": r.default, "current": o.get(key, r.default),
                         "minimum": r.minimum, "maximum": r.maximum, "strict": r.strict})
        types = [{"key": k, "current": v, "minimum": "L1", "maximum": "L3"} for k, v in sorted(o.items())
                 if k.startswith(lv.TYPE_KEY_PREFIX)]
        have = self.household_level()
        latched = self.note_proven("household_level")
        return {"rows": rows, "types": types, "household_level": lv.name(have) if have else None,
                "grace": self.svc.cfg.l2_grace and not latched, "recovery_needed": latched and have < 2,
                "box_confirm": self.svc.presence.available}

    # ---- writes, through the approval queue -------------------------------------------------------
    def _owner_request(self, p, what: str) -> None:
        if not p.is_owner:
            raise self.svc.deny(p, what)

    def check_set(self, params: dict, p) -> None:
        self._owner_request(p, "change the verification table")
        refused = lv.check_edit(params["key"], params["level"])
        if refused:
            raise ApiError(422, "conflict", refused[1], reason=refused[0])
        if params["level"] == "L3" and self.household_level() < 3:
            raise ApiError(409, "conflict", "no key on this box reaches L3 yet, so nobody could approve it",
                           reason="level_unreachable")

    def recheck_set(self, a: Action) -> str | None:
        """Judged again when the approved edit runs: the floor, and that L3 is still reachable (a key may
        have been removed since it was filed)."""
        refused = lv.check_edit(a.params["key"], a.params["level"])
        if refused:
            return refused[1]
        if a.params["level"] == "L3" and self.household_level() < 3:
            return "no key on this box reaches L3 any more, so nobody could approve it"
        return None

    def run_set(self, a: Action, finish) -> None:
        from ..executors import ExecResult

        key, level = a.params["key"], a.params["level"]
        now = self.svc.now()
        with self.repo.db.session.begin() as s:
            row = s.get(VerificationLevelRow, key)
            before = row.level if row else lv.bounds(key)[0]
            if row is None:
                s.add(VerificationLevelRow(key=key, level=level, updated_at=now, updated_by=a.approved_by or "",
                                           action_id=a.id))
            else:
                row.level, row.updated_at, row.updated_by, row.action_id = level, now, a.approved_by or "", a.id
        self.svc.emit("verification", "requirement.changed", {"key": key, "from": before, "to": level,
                                                              "action_id": a.id, "approved_by": a.approved_by})
        finish(ExecResult("succeeded", f"{key} now needs {level}"))

    def check_add_model(self, params: dict, p) -> None:
        self._owner_request(p, "trust a key model")
        if lv.clean_aaguid(params["aaguid"]) is None:
            raise ApiError(422, "conflict", "aaguid must be 32 hex digits (dashes allowed), not all zero",
                           reason="invalid_aaguid")
        for pem in params["roots"]:
            if (why := lv.check_root(pem)) is not None:
                raise ApiError(422, "conflict", why, reason="invalid_root")

    def run_add_model(self, a: Action, finish) -> None:
        from ..executors import ExecResult

        prm = a.params
        aaguid = lv.clean_aaguid(prm["aaguid"]) or ""
        with self.repo.db.session.begin() as s:
            row = s.get(TrustedModelRow, aaguid)
            values = dict(name=prm["name"], roots=list(prm["roots"]), user_verification=list(prm["user_verification"]),
                          added_at=self.svc.now(), added_by=a.approved_by or "", action_id=a.id)
            if row is None:
                s.add(TrustedModelRow(aaguid=aaguid, **values))
            else:
                for k, v in values.items():
                    setattr(row, k, v)
        self.svc.emit("auth", "trusted_model.added", {"aaguid": aaguid, "name": prm["name"], "action_id": a.id,
                                                      "approved_by": a.approved_by})
        self.note_proven(f"trusted model {aaguid}")  # its keys may be proven now: the grace ends for good
        finish(ExecResult("succeeded", f"{prm['name']} is a trusted key model"))

    def list_models(self, p) -> list[dict]:
        self._owner_request(p, "read the trusted key models")
        owner_rows = {r.aaguid: r for r in self.repo.all(select(TrustedModelRow))}
        out = []
        for m in self.models().values():
            row = owner_rows.get(m.aaguid) if m.source == "owner" else None
            out.append({**m.json(), "added_at": iso(row.added_at) if row else None})
        return sorted(out, key=lambda x: (x["source"], x["name"]))

    def holds_last_proven(self, aaguid: str) -> bool:
        """Removing this owner-added model would leave no owner with a proven key."""
        if self.household_level() < 2:
            return False
        models = {k: m for k, m in self.models().items() if k != aaguid or m.source == "shipped"}
        owners = self.svc.active_owner_ids()
        rows = self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id.in_(owners))) if owners else []
        return max((self.cred_level(r, models) for r in rows), default=0) < 2

    def remove_model(self, p, aaguid: str, ctx=None) -> None:
        """Taking trust away only tightens (L0, design 3.11): keys of that model drop to L1 at once. The
        latch keeps that from re-opening the grace. Removing the model behind the household's last proven
        key needs that key (L2), or an owner at the box (a lost key), like revoking the last proven key."""
        self._owner_request(p, "remove a trusted key model")
        clean = lv.clean_aaguid(aaguid) or ""
        if self.repo.get(TrustedModelRow, clean) is None:
            if clean in self.shipped:
                raise ApiError(409, "conflict", "this model comes with the OS; an update removes it",
                               reason="shipped_model")
            raise ApiError(404, "not_found", "no such trusted key model")
        if self.holds_last_proven(clean):
            self.svc.require_step_up(ctx, p, "stop trusting the model of your last proven key",
                                     op="auth.trusted_models.remove", target=clean)
        self.repo.delete(TrustedModelRow, TrustedModelRow.aaguid == clean)
        self.svc.emit("auth", "trusted_model.removed", {"aaguid": clean}, p)

    def register(self) -> None:
        from ..actions import FeatureAction

        acts = self.svc.gw.actions
        acts.register_type(SET_TYPE, FeatureAction("sensitive", self.run_set, frozenset({"person"}),
                                                   check=self.recheck_set, params_model=RequirementParams,
                                                   check_request=self.check_set))
        acts.register_type(ADD_MODEL_TYPE, FeatureAction("sensitive", self.run_add_model, frozenset({"person"}),
                                                         params_model=TrustedModelParams,
                                                         check_request=self.check_add_model))
