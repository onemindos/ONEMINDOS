<!-- SPDX-License-Identifier: Apache-2.0 -->
# Android and iPhone app shells to v1 (CORE-MOBILE)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E3 (phone approvals over HTTPS) · **Deeper docs:** `mobile/README.md` (branch `feat/mobile-shell`, uncommitted); research 12 §6–§8 (REC-W11-08, -09, -11); [D-005](../../DECISIONS.md) · **Serves:** UX-5, UX-4; core-alignment MOB-P1, MOB-P2, MOB-B1…B3.

> **Explain it like I am the founder**
> A first phone shell already exists for Android and iPhone (Expo / React Native): it shows nodes, apps, approvals and activity, and lets the owner approve.
> v1 makes it safe and daily-usable: pair by scanning a QR on the box (no token typing), approve with Face ID or a fingerprint passkey, get private push alerts, and see a clearly labelled offline view.
> The phone never decides anything itself; it only signs your approval of the exact request the box shows.

## 1. Goals and non-goals

| Goals | Non-goals (v1) |
|---|---|
| QR pairing that pins the box CA (no token in the QR) | Photo backup, file sync (umbrelOS 2.1 has it; later) |
| Passkey sign-in and passkey-signed approvals with biometric step | Running apps' UIs natively (open them in an in-app browser, signed in) |
| Push: Android UnifiedPush via the box's ntfy; iOS APNs ping-then-fetch | A OneMind cloud account |
| Tabs: Home, Nodes, Apps, Approvals, Activity (audit), Alerts, Settings | Several boxes at once (v1.1) |
| Honest offline cache with age labels; stores the latest audit checkpoint | Tablet and watch layouts |
| Store releases: TestFlight and Play internal track, then public | Phone required for activation (never; MOB-B3) |

## 2. What exists today (`feat/mobile-shell`, uncommitted)

| Piece | Where |
|---|---|
| Expo SDK 58, React Native 0.88, React Navigation 7; all direct deps MIT, pinned | `mobile/package.json` |
| Screens: Connect, Home, Nodes, Apps + app page, Approvals, Activity, Settings | `mobile/src/screens/` |
| Token in iOS Keychain / Android Keystore (`expo-secure-store`, this-device-only) | `mobile/src/storage.ts`, `session.tsx` |
| Local notifications while open (approvals, results, node offline) | `mobile/src/lib/alerts.ts`, `notify.ts` |
| API client, types and fixtures **copied** from the dashboard | `mobile/src/api/` |
| Demo mode and deep links `onemind://…` | `mobile/src/nav.ts`, `api/mock.ts` |
| Tests: API client, approvals, alerts, session, Approvals screen | `*.test.ts(x)` |

**Known gaps (its README):** plain HTTP allowed with a warning; static token; no push while closed; no audit screen; no "who am I"; no QR pairing; no icon.

**Flag (F-3):** research 12 REC-W11-09 recommends Capacitor over the web dashboard; the built shell is Expo / React Native as the 2026-11-12 task asked. This spec assumes **keep Expo** and share code through a generated `sdk/ts` package, because the shell already runs and the native push pieces (UnifiedPush module, iOS service extension) are native either way. The founder decides.

## 3. Design

### 3.1 Pairing (CORE-MOBILE-2)
```
box console / dashboard Settings ─► QR: {"v":1,"url":"https://onemind.local:8443","ca":"sha256:4be1…"}
phone scans ─► fetches CA, checks fingerprint ─► pins it for this box ─► passkey register or sign in
```
On iOS the app trusts the pinned CA for its own requests (no system-wide profile needed for the app; a profile is offered only for opening app UIs in Safari). No token ever appears in a QR or a URL.

### 3.2 Approve with a passkey (CORE-MOBILE-3)
```ts
// mobile/src/lib/approvals.ts (sketch)
const opts = await api.post(`/v1/actions/${id}/approve-options`);      // challenge bound to plan hash
const assertion = await passkeys.get(opts.publicKey);                 // Face ID / fingerprint prompt
await api.post(`/v1/actions/${id}/approve`, { plan_sha256: opts.plan_sha256, webauthn: assertion });
```
The screen shows the exact `type` and `params`, the plan (objects, images, ports, volumes), who asked (person or agent), the agent's reason in a labelled block, and the expiry countdown. Deny needs no passkey (it reduces power).

### 3.3 Push (CORE-MOBILE-4, -5)
| Platform | Path | Native work |
|---|---|---|
| Android | UnifiedPush; distributor = ntfy app; server = the box's own ntfy; payload `{alert_id, box_id}`; app fetches `/v1/alerts/{id}` | Expo native module around the UnifiedPush connector (check its licence first) |
| iOS | APNs via the stateless OneMind relay (NOTIFICATIONS); `mutable-content: 1`; Notification Service Extension fetches the text from the box | Service extension target via config plugin; raw APNs token (`getDevicePushTokenAsync`), not Expo's push service |

```console
$ onemind notify devices
DEVICE            KIND         REGISTERED   LAST PING
pixel (owner)     unifiedpush  2026-11-20   09:12 ok
iphone (owner)    apns-relay   2026-12-02   09:12 ok
```

### 3.4 Offline and audit (CORE-MOBILE-6)
The last state is cached encrypted on the device and always shown with its age ("from 14 min ago, not live"). The app stores the latest signed audit checkpoint from the box (SECURITY CORE-SEC-6) and warns if a later checkpoint does not extend it.

### 3.5 Shared code (CORE-MOBILE-1)
Replace the copied `src/api/{types,client,mock,fixtures}.ts` with the generated `@onemind/sdk` (`sdk/ts`), built from `/openapi.json`. Colours come from `@onemind/ui/tokens.json`.

## 4. Security model
- CA pinned per box; plain HTTP refused after pairing (allowed only in demo mode and on loopback dev).
- Credentials: session and device keys in Keychain/Keystore, this-device-only; passkeys in the platform authenticator.
- Approvals always need a fresh passkey assertion (F-2 default); notification taps open the card, never approve.
- Push payloads content-free; the relay sees only an opaque id.
- Deep links never carry tokens or approve actions; links from the catalog open only if `https://`.

## 5. Versioning and compatibility
- App declares the contract version it needs; on an older gateway it hides screens whose routes are missing (checked via `/openapi.json`).
- Store builds: version `1.x.y`; the minimum gateway version is shown in Settings.
- Existing v0 installs with a typed token keep working until the box requires passkeys; the app then prompts to re-pair.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Unit (exists, extend) | approvals with `approve-options`, pairing QR parsing, CA mismatch refusal |
| Real Android phone | Push arrives with the app closed; approve in under 10 s; a replayed link without passkey fails (plan E3) |
| Real iPhone | Service extension shows the fetched text; Apple payload contains only ids |
| MITM | A box with a different CA at the same URL → connection refused with a clear message |
| Offline | Airplane mode: cached view labelled with age; approve disabled |
| Accessibility | Screen reader labels on every control; dynamic type to 200 % |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-MOBILE-1 | Commit the shell; switch to generated `sdk/ts`; icon and splash | S | `sdk/ts` |
| CORE-MOBILE-2 | QR pairing with CA pinning; HTTPS only | M | SEC-1 |
| CORE-MOBILE-3 | Passkey sign-in and signed approvals; plan card | M | SEC-2, SANDBOX-2 |
| CORE-MOBILE-4 | Android UnifiedPush module | M | NOTIFY-3 |
| CORE-MOBILE-5 | iOS service extension + relay registration | M | NOTIFY-4, F-4 |
| CORE-MOBILE-6 | Alerts and Activity (audit) tabs; offline cache; checkpoint store | M | NOTIFY-1, SEC-6 |
| CORE-MOBILE-7 | Store releases (TestFlight, Play internal → public) with privacy labels | S | 1–6 |

## 8. Who owns which files

| Branch | Files |
|---|---|
| `feat/mobile-shell` (exists) | `mobile/**` |
| `feat/sdk-ts` (proposed, developer-surface stream) | `sdk/ts/**` |
| `feat/push-relay` (proposed) | `relay/**` |
| Hotspots (serialized) | `mobile/app.json` (native config, plugins), contract routes it depends on |
