# SPDX-License-Identifier: Apache-2.0
"""The approval card (#723): what the host draws before an owner approves any action.

Every action carries one (ledger.Action.to_json): hold is true for an action that cannot be undone
(risk "destructive") or that moves something physical (founder pick), so a client never reads
"card present" as "physical". A physical card also carries limits with units and a preview slot and
is hashed into the plan (actions.physical_plan). No imports from this package: ledger and actions
both use it.
"""

from __future__ import annotations

# Hold-to-approve (#723, founder pick): only for actions that cannot be undone or that move something
# physical. The approval card says hold; the HoldToApprove control (ui/) holds for this long.
HOLD_MIN_MS = 2000
APPROVAL_LIMIT_VALUE = (str, int, float, bool)


def hold_required(risk: str | None, physical: bool) -> bool:
    """Whether the approval card asks for hold-to-approve: physical, or cannot be undone."""
    return physical or risk == "destructive"


def approval_card(risk: str | None, physical: bool, limits: list[dict] | None = None,
                  preview: dict | None = None) -> dict:
    """The approval payload the host draws (apimodels.ApprovalCard): hold flag, limits, preview slot.

    limits: [{name, value, unit}] with units, shown before the owner approves (the gateway and the
    device check them again). preview: {kind, ref?, text?}, an optional slot (camera still, path).
    Raises ValueError on a malformed limit or preview.
    """
    out_limits = []
    for lim in limits or []:
        if not isinstance(lim, dict) or set(lim) - {"name", "value", "unit"}:
            raise ValueError("an approval limit is {name, value, unit}")
        name, value, unit = lim.get("name"), lim.get("value"), lim.get("unit")
        if not isinstance(name, str) or not 0 < len(name) <= 64:
            raise ValueError("an approval limit needs a name of 1 to 64 characters")
        if not isinstance(value, APPROVAL_LIMIT_VALUE) or (isinstance(value, str) and len(value) > 200):
            raise ValueError(f"approval limit {name!r}: value must be a string, number or boolean")
        if unit is not None and (not isinstance(unit, str) or len(unit) > 32):
            raise ValueError(f"approval limit {name!r}: unit must be a string of at most 32 characters")
        out_limits.append({"name": name, "value": value, "unit": unit})
    if len(out_limits) > 20:
        raise ValueError("an approval card shows at most 20 limits")
    if preview is not None:
        if not isinstance(preview, dict) or set(preview) - {"kind", "ref", "text"} or \
                not isinstance(preview.get("kind"), str) or not 0 < len(preview["kind"]) <= 32:
            raise ValueError("an approval preview is {kind, ref?, text?}")
        if any(preview.get(k) is not None and (not isinstance(preview[k], str) or len(preview[k]) > 2000)
               for k in ("ref", "text")):
            raise ValueError("approval preview ref and text are strings of at most 2000 characters")
        preview = {"kind": preview["kind"], "ref": preview.get("ref"), "text": preview.get("text")}
    hold = hold_required(risk, physical)
    return {"physical": physical, "hold": hold, "hold_ms": HOLD_MIN_MS if hold else None,
            "limits": out_limits, "preview": preview}
