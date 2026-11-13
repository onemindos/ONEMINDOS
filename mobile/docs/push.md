<!-- SPDX-License-Identifier: Apache-2.0 -->
# Push for the OneMind phone app (CORE-MOBILE-4, CORE-MOBILE-5)

**Serves:** D-005 (no vendor reads alert content), contract §12.14, `docs/leap/core/NOTIFICATIONS.md` §3.2 (NOTIFY-3, NOTIFY-4), `docs/leap/core/MOBILE.md` §3.3, founder decision F-4 (when to build the iOS relay).

> **In one paragraph:** the box never sends alert text through Apple or Google. It sends a **ping** that carries only an id. The phone wakes up, asks the box for the text over HTTPS with its own session, and shows it. On Android the ping travels through **UnifiedPush**: the ntfy app on the phone, connected to the box's own ntfy server, so no third party is involved at all. On iPhone Apple's push service (APNs) is the only way to wake an app, and only the app's developer key can use it, so a small **OneMind relay** holds that key and forwards `{device token, id}`. Apple learns that a ping arrived, never what it was about.

## 1. What is built here and what is not

| Piece | State | Where |
|---|---|---|
| Android: UnifiedPush native module (Kotlin, Expo local module): distributor choice, registration with the box's VAPID key, Web Push keys, endpoint rotation, content-free notification when the app is closed | **written, not yet compiled on a device or in CI** | `mobile/modules/onemind-unifiedpush/` |
| Android and iPhone: register the endpoint or raw APNs token with the box, remember it per hub, turn off, re-register a rotated endpoint | built, unit-tested | `mobile/src/lib/push.ts` |
| Ping handling while the app runs: refresh from the box, show the text fetched over HTTPS | built | `mobile/src/pushPings.ts` |
| iPhone: Notification Service Extension that replaces the generic text before it is shown | **not built** (needs the Apple developer account and an App Group, F-4) | §6 below |
| The relay itself | **not built here**: own service, own branch (`feat/push-relay`, `relay/**`) | interface in §4 |
| The box side (`POST /v1/push/registrations`, sending pings) | not built (notifications module, NOTIFY-3/-4) | contract §12.14 |

## 2. Registration: phone → box (contract §12.14)

```http
POST /v1/push/registrations
Authorization: Bearer <the person's session>
{"platform": "unifiedpush", "endpoint": "https://ntfy.<box>/upAbC…", "keys": {"p256dh": "…", "auth": "…"}, "label": "Pixel 9"}

POST /v1/push/registrations
{"platform": "apns", "token": "<64 hex>", "label": "iPhone", "environment": "production", "bundle_id": "os.onemind.mobile"}
→ 201 {"id": "…", …}
```

- `keys` are the Web Push (RFC 8291) keys the UnifiedPush connector generates; the box encrypts each ping with them.
- **Proposed additions (not yet in §12.14):** `environment` (`sandbox` for debug builds, `production` for TestFlight and store builds: APNs refuses a token on the wrong host) and `bundle_id` (the APNs topic). Both are optional; a relay that serves one app in one environment can ignore them. They belong in the next contract amendment with NOTIFY-4.
- The phone deletes its registration (`DELETE /v1/push/registrations/{id}`) when push is turned off or the hub is forgotten, and replaces it when the distributor hands out a new endpoint.
- Where the hub has a device registry (`/v1/devices/*`, docs/umbrel2/clients.md §4.4), push is offered only once the owner approved this phone, so a revoked device also stops getting pings.

## 3. Android: box → the phone's ntfy endpoint

```http
POST https://ntfy.<box>/upAbC…            (the endpoint from the registration)
Content-Encoding: aes128gcm               (RFC 8291, with the registration's keys)
Authorization: vapid t=<JWT>, k=<GET /v1/push/vapid-public-key>   (RFC 8292)
TTL: 3600
Urgency: high                             (approvals) | normal
<encrypted> {"notification_id": "ntf_01J…", "box_id": "<instance id>"}
```

The ntfy app (distributor) wakes `OneMindPushService`. If the app's JavaScript is running it fetches `GET /v1/notifications/{id}` and shows the real title and body; if not, the service shows "OneMind — Something new on your box" and opens the Inbox on tap. Anything in the ping that is not an id is ignored, never displayed.

**Setup for the person:** install ntfy (F-Droid or Google Play), add the box's ntfy server (the `apps/ntfy` seed app) as the default server, then turn on push in OneMind → Settings. No Google account, Play Services or Firebase is involved; the app's manifest blocks the FCM permission.

## 4. iPhone: the relay interface (for `feat/push-relay`)

### 4.1 Box → relay
```http
POST https://<relay>/v1/ping
Content-Type: application/json
{"device_token": "<64 hex>", "opaque_id": "ntf_01J…", "environment": "production"}
```

| Answer | Meaning | Box does |
|---|---|---|
| `202` (empty body) | handed to APNs | nothing |
| `410 {"error": "token_gone"}` | APNs said the token is no longer valid (app removed, token rotated) | delete that push registration |
| `422 {"error": "invalid_request"}` | malformed token or id | log the registration id, keep going |
| `429` with `Retry-After` | rate limited (per token and per source) | back off |
| `503` | APNs unreachable | retry with backoff, at most for the ping's TTL |

- `opaque_id` is the notification id the phone fetches (`^[A-Za-z0-9_-]{1,64}$`). `environment` is optional (default `production`).
- **Accepts nothing else.** No title, body, user, box name or URL. A body with any other field is refused with `422`, so a box bug cannot leak content to Apple.
- **Logs:** rate-limit counters only. No tokens, ids or source addresses are stored.
- **Open for the relay owner:** how a relay authenticates boxes (not in §12.14). Without it anyone who knows a device token can make that phone show a generic "something new"; content still cannot leak. Options: a per-box key issued when the box first registers, or an Ed25519 signature with the box's instance key.

### 4.2 Relay → APNs
```http
POST https://api.push.apple.com/3/device/<device_token>      (api.sandbox.push.apple.com for "sandbox")
authorization: bearer <ES256 JWT from the team's .p8 key>
apns-topic: os.onemind.mobile
apns-push-type: alert
apns-priority: 10
apns-expiration: <now + 1 h>
{"aps": {"alert": {"title": "OneMind", "body": "Something new on your box."}, "sound": "default", "mutable-content": 1},
 "opaque_id": "ntf_01J…"}
```
The generic text is what an iPhone shows if nothing replaces it. The key, the team id and the bundle id are the founder's Apple developer account (F-4); a household can run its own relay with its own account and its own build of the app.

## 5. On the phone

| State | Android | iPhone |
|---|---|---|
| App open | module event → refresh; the Inbox and a local notification show the fetched text | APNs delivers to the app; the generic banner is suppressed; refresh as on Android |
| App in the background, JavaScript alive | module event → fetch `GET /v1/notifications/{id}` → local notification with the text | iOS shows the generic alert (until §6) |
| App closed | service shows the generic notification; tap opens the Inbox | iOS shows the generic alert (until §6); tap opens the Inbox |

A notification never approves anything. One about a pending request opens the Approvals tab, where approval needs the owner and, when required, a passkey (NOTIFY-7).

## 6. Next: the iOS Notification Service Extension (needs F-4)
A Notification Service Extension runs for each push with `mutable-content: 1` and may change the text before iOS shows it (about 30 s budget). It reads the box URL and a short-lived access token from a keychain item shared with the app through an App Group, calls `GET /v1/notifications/{opaque_id}`, and sets the title and body. On any failure it leaves the generic text. Building it needs the Apple developer account (App Group and push entitlements), an extension target added through a config plugin (`@bacons/apple-targets`, MIT, build time only) and a device to test on.
