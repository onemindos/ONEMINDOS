<!-- SPDX-License-Identifier: Apache-2.0 -->
# Network page and Add a device (`ui/src/network/`)

**Serves:** CORE-NET-13 (NETWORKING.md §12 "Network page", §5.5 and contract §12.11 join flow).
**Demo:** `#/network`, `#/network/add`, `#/network/stale`, `#/network/error` in `ui/demo`. The
dashboard pages come in a later wiring pass (dashboard-v2 stream); these components take data and
callbacks only.

| File | What |
|---|---|
| `types.ts` | Shapes of `GET /v1/mesh`, `GET /v1/fabric`, `POST /v1/fabric/join-tickets` (core `routers/net.py`) |
| `logic.ts` | QR matrix (`uqr`, MIT, error correction M), ticket countdown, one row per machine, waiting joins |
| `NetworkPage.tsx` | Reach mode and coordinator, machines with role, state, link (direct/relayed) and event-bus link, names in use, app addresses (`https://<app>.<box>.local`) |
| `AddDevice.tsx` | Choose a machine role → one-time code as a QR plus the install command → the join request appears with its match code → "Check code and approve" opens the approval card |

Rules: no IP address by default (contract §2; "Show addresses" is owner-only and not remembered);
stale data is labelled and disables Add a device; the dialog never approves by itself (approval goes
through Approvals, with passkey step-up once enabled); closing the dialog forgets the code, which
the hub shows only once. The QR stays black on white in both themes so phone cameras read it.
