# SPDX-License-Identifier: Apache-2.0
"""The hard floor (gateway permissions design §3.4): what no mode and no rule can approve on its own.

Each item answers "a person decides this one, at the time". They existed before in scattered places
(registry.PHYSICAL, _never_by_policy, the AIG-04 taint guard, the licence check, the §12.22 network
paths); those checks stay where they are as asserts, and this module names them in one list so
`decide()` can say which item applied.

1. physical actions (#723, F-4)
2. destructive and actuate effective risk (T3, T4)
3. tainted or exposed requesters (AIG-04, F-11 = a). The design lets an exposed agent hold T0
   rules; that stays closed here, because the AIG-04 guard still refuses every tainted
   automatic approval. Opening it is a separate, deliberate loosening.
4. anything that grants access: data and host grants, plugin keys, agent resume, joining a
   machine, roles, certificates, update settings, the recovery kit, agent browser sites, every
   `automation.rule.*`, and a plan that opens network paths between apps (§12.22)
5. secrets: an app's sealed settings
6. radio transmit: only on the owner's tap (D-024)
7. SMB shares (D-017): AI never requests one
8. a licence that is not green (#173): the owner types the app id
9. an agent never approves (enforced in actions.py: approvals refuse every non-owner)
10. an unknown effective risk: refused before the floor (decide step 5)
11. the floor's own settings off: every mode behaves as Always ask (decide step 7)
12. a clock that cannot be trusted: the same (decide step 7)
"""

from __future__ import annotations

GRANTS_ACCESS = frozenset({
    "data.grant", "host.grant", "plugin.key.enroll", "agent.resume", "node.join", "node.set_role",
    "tls.acme.set", "backup.kit.issue", "os.update.settings", "agentbrowser.site.allow",
    "automation.rule.create", "automation.rule.update", "automation.rule.enable",
})
SMB_TYPES = frozenset({"files.share.create"})
AI_KINDS = frozenset({"agent", "plugin"})


def radio_transmit(action_type: str) -> bool:
    return action_type.startswith("radio.") and "transmit" in action_type


def floor_items(*, action_type: str, kind: str, risk: str | None, physical: bool = False, tainted: bool = False,
                exposed: bool = False, network_paths: bool = False, sealed: bool = False,
                licence_green: bool = True) -> tuple[str, ...]:
    """Every floor item this request hits, in the §3.4 order. Empty: a mode or rule may decide it."""
    out = []
    if physical:
        out.append("physical")
    if risk in ("destructive", "actuate"):
        out.append(risk)
    if exposed:
        out.append("exposed")
    elif tainted:
        out.append("tainted")
    if action_type in GRANTS_ACCESS or network_paths:
        out.append("grants_access")
    if sealed:
        out.append("secrets")
    if radio_transmit(action_type):
        out.append("radio_transmit")
    if action_type in SMB_TYPES and kind in AI_KINDS:
        out.append("smb_share")
    if not licence_green:
        out.append("licence")
    return tuple(out)
