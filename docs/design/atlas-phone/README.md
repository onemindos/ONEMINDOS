<!-- SPDX-License-Identifier: Apache-2.0 -->
# The phone app's agreed design (Atlas, 2026-11-21)

**Founder-requested** (2026-11-26; see the [request in issue #1225](https://github.com/onemindos/ONEMINDOS/issues/1225)): the phone app must match the design Zeus picked on 2026-11-21 (Atlas base, Sovereign colours, today's logo, Console wallpapers). The desktop dashboard was moved to it; the phone app (`mobile/`) was not. This folder holds the phone part of the final design pack so builders can work from it. **This folder supersedes [`IA.md`](../IA.md) §1 for the phone navigation** (IA.md's Home, Apps, Approvals, Activity tabs plus More, still cited by `mobile/src/nav.ts`); #1225 updates `nav.ts` and IA.md gets a pointer to this folder. The root [`DESIGN.md`](../../../DESIGN.md) is the shipped summary; this file is the phone detail.

## The renders (390 × 844, the target)

| Render | Screen | Built today? | Issue |
|---|---|---|---|
| [`13a-phone-home-dark.png`](13a-phone-home-dark.png), [`13a-phone-home-light.png`](13a-phone-home-light.png) | Home | No: the app shows a plain list of health rows | #1225 |
| [`13d-phone-approvals-dark.png`](13d-phone-approvals-dark.png), [`13d-phone-approvals-light.png`](13d-phone-approvals-light.png) | Approvals with hold to approve | No | #1226 |
| [`13c-phone-app-page-light.png`](13c-phone-app-page-light.png) | An app's page while its install waits for approval | No | #1227 |
| [`13b-phone-map-dark.png`](13b-phone-map-dark.png), [`13b-phone-map-light.png`](13b-phone-map-light.png) | Map tab | No | #656 (needs the assets API, #606) |
| [`13e-phone-stop-running-dark.png`](13e-phone-stop-running-dark.png) | A running physical action with one-tap Stop | No | needs a gateway "stop running action" route first (none exists) |

**The people and places in the renders are made up** (the "Rivera home", Maya, Hermes, the greenhouse vent). Build the layout and behaviour, never the sample data: every value on screen comes from the hub through `@onemind/sdk`. A card with no real data behind it is hidden, not filled with examples.

## Rules (from the final design pack; the pack is kept outside the repo)

**Colours.** Take every colour from the design tokens (`mobile/src/ui/theme.ts`, generated from `ui/src/tokens/tokens.ts`). `fromRoles()` in `theme.ts` maps only `accent*` today: #1225 must first add `action`, `actionText` and `actionHover` to it (the values already exist in `tokens.generated.ts`). The pack's hex values are close to the tokens but the tokens win.
- **Buttons are red** (`action`, `action-text`, `action-hover`) on every primary button, in light and dark. Today the phone paints primary buttons teal (`accent`): that is the drift to fix.
- **Teal is the highlight only:** selection, focus ring, the active tab, toggles, active chips. Never a button.
- Mark red (`#FF333A`) appears only inside the logo files.
- **Status by shape and word, never colour alone:** filled circle = fresh, half ring = stale, slashed ring = offline, diamond = needs you, triangle = fault.

**Type.** System font. Greeting 26 on phone, the sentence an approval asks 22–28, title 20, big numbers 28 with tabular figures, body 15, labels 13, nothing under 12. Mono for times and IDs.

**Layout.**
- **Five tabs: Home, Map, Approvals, Apps, Me.** Approvals carries the waiting count as a red badge. Until the Map tab (#656) lands, ship four tabs (Home, Approvals, Apps, Me); do not add an empty Map tab.
- Today's Activity and More screens move under **Me** (with Settings), so nothing that exists is lost.
- Every touch target is at least 44 px; main buttons 48 px.
- Cards: surface colour, 1 px line, 18 px radius, 14 px padding. The **Contour** wallpaper sits behind the screens (light and dark sides follow the mode).
- Every live number prints its age ("8 s", "3 min").

**Approval rule for Home, Approvals and the App page (#723, D-027/D-028).** Only an approval-card object with explicit `hold: false` permits normal signed approval. For `hold: true`, a missing or null card, a legacy string, or a card without an explicit boolean, Home shows the hold note, Approvals uses the hold control, and the App page sends the owner to Approvals with **Review and decide**.

**Home (`13a`), top to bottom.** Logo + box name + the person's avatar · greeting with their name and a one-line summary ("3 things need you. …") · the **Needs you** card: the first waiting request, who asks, its expiry, the sentence it asks, a red **Review and decide** button, and the hold note (“no one-tap yes, you hold to approve on the next screen”) when the shared rule calls for it (with "1 of 3" when more wait) · app tiles for installed apps with health pips · live sensor cards with a small trend line, only when the hub has real live values · a **Machines** row with fresh / stale / offline counts.

**Approvals (`13d`).** Segments **Waiting · n / Decided / Agents**. Each request card: the requester ("Hermes asks · AI agent · can ask, cannot act"), a tag (**Moves a device** when `action.approval.physical` is true, **Cannot be undone** when `risk == destructive`, **Can be undone** when the card explicitly permits normal approval, or **Hold required** when the card is unavailable or incomplete; `risk: actuate` alone does not mean physical: `system.restart`, `system.shutdown` and `wake` are `actuate` with no hold), the sentence it asks, the live evidence, exactly what will happen and when it goes back by itself, plan choices (for example duration), then the decision buttons, then the expiry ("9 min left. If nobody answers, nothing moves.").
- The gateway sets hold for physical or destructive actions (`core/onemind_core/approvalcard.py`). The hold control uses the card's `hold_ms` with a 2,000 ms minimum and defaults to 2,000 ms when unavailable. The label says what is approved ("Hold to approve 45 min"). The fill shows progress. Releasing early cancels, and signing starts only after a completed hold.
- For a held approval, fetch bound approval options before sending the request. Use the generated SDK approve body and preserve the observed `hold_ms` even when it is the only field. When the action has a plan, require the bound `plan_sha256` to match the displayed plan and send that hash. Physical approval requires both the matching plan hash and a WebAuthn assertion (`webauthn`), including with an enrolled phone approval key. The existing bound flow attaches `webauthn` or `device_signature` when it signs. Extend orchestration and transport in `mobile/src/lib/approvals.ts` and `mobile/src/api/client.ts`, preserving the plan comparison, challenge binding, approval-key signing and gateway verification.
- Reference behaviour: `ui/src/components/HoldToApprove.tsx`, `dashboard/src/pages/Approvals.tsx` (lines 79-81), `dashboard/src/data/adapters.ts` and `dashboard/src/lib/approve.ts`.
- **Approve with passkey (Face ID)** uses the existing signed path when the shared rule permits normal approval.
- **Deny** is always one tap.
- Reduce motion: no animated fill; show a static progress label instead.

**App page (`13c`).** Back to Market · icon, name, one-line purpose, grade and category chips · version, runs on, size · when an install waits: "Waiting for your approval", a four-step track (Asked, Checked, You, Install), **Review plan** and **Cancel request**. When the shared rule permits normal approval, show the signed **Approve with passkey (Face ID)** button and the line "No hold here: an install can be undone and moves nothing." Otherwise show **Review and decide**, which opens that request in Approvals. Below the waiting state, show **Trust** (licence, known flaws, malware scan with time) · **What it can touch** (folders, network, devices).

**App icons.** An app's own icon when its licence allows it, a neutral tile otherwise (founder answer, 2026-11-21; this replaces the pack's "never a logo" rule).

**Never.** No one-tap or single-key approval of a physical or irreversible action. Stop is never harder than approve. No map value without its age. No copied pixels, icons or text from other operating systems or competitors.

## Reference

- [`phone.reference.css`](phone.reference.css): the mock-ups' phone rules (sizes, spacing), for reading only.
- Root [`DESIGN.md`](../../../DESIGN.md), [`docs/design/TOKENS.md`](../TOKENS.md), [`docs/design/PRINCIPLES.md`](../PRINCIPLES.md).
- Decisions that bind the phone: AI never actuates without human approval; D-027 and D-028 (permission modes, biometric levels).
