# Information architecture

**Serves:** backlog items 7 (UX-P1), 8 (NOT-P1), 9 (UX-B1), 10 (OSU-P1), 11 (APP-P1–P3), 15 (FAB-P1/P2), 16 (FAB-P3, APP-B3), 17 (MOB-P1, MOB-B2), 20 (NOT-B1), 22 (REM-P1), 25 (SEC-B3/B4) in `docs/strategy/core-alignment.md`; contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §3, §5, §9.3, §11.4.
**Mocks:** every screen below is a static mock in [`ui/demo`](../../ui/demo/) (fixtures only). Screenshots are in [`screens/`](screens/).

**How to read "Data":** *contract* means the field exists in `poc-v0.md` today. **PROPOSED** means the screen needs an endpoint or field that does not exist yet; the backlog item that would add it is named. Mocks use fixtures for both.

## 1. Navigation

| Group | Item | Route | Badge | Phone |
|---|---|---|---|---|
| — | Home | `/` | — | Tab |
| — | Apps (installed + Market) | `/apps`, `/apps/<id>` | updates available (PROPOSED) | Tab |
| — | Approvals | `/approvals` | requests waiting | Tab |
| — | Activity | `/activity` | — | Tab |
| — | Alerts | `/alerts` | open alerts | More (and push) |
| System | Nodes | `/nodes`, `/nodes/<id>` | — | More |
| System | Backups | `/backups` | — | More |
| System | Updates | `/updates` | — | More |
| System | Settings (People, Agents and tokens, Security, Remote access, Notifications, Appearance) | `/settings/<section>` | — | More |

- **Desktop (> 720 px):** left sidebar with groups; a top bar with the hub connection state (a freshness pill: the hub's own answer is ageing too) and the person menu.
- **Phone (≤ 720 px):** bottom tab bar with four primary items plus **More**, which opens a sheet with the rest. Badges on More sum the hidden badges.
- **Why Alerts is under More on phones:** on a phone, alerts arrive as notifications, and an alert that needs a decision opens its approval directly (NOT-B3). The tab slot is worth more for Activity. **This differs from backlog MOB-P1**, which lists six tabs (Home, Nodes, Apps, Approvals, Activity, Alerts); flagged for the founder, easy to switch.
- **Not in v0 navigation:** Files, Family limits, AI & Agents console, Control Hub (docs/DASHBOARD.md §3). The agent console is a Settings section until backlog SEC-B3 lands. A command palette (UX-P3) will search all routes.
- **The rescue console** (REC-W11-04) is a separate tiny page served by `onemindd` on the host when k3s is down: health, logs, update and rollback. It uses the same tokens but not this navigation. Pattern: StartOS `routes/diagnostic/` (MIT).

## 2. Screens

Each screen lists its purpose, content, actions (every action is a request, P1), states, and data.

### 2.1 Home · `screens/home.png`, `home-dark.png`, `home-phone.png`
- **Purpose:** "Is everything fine, and does anything need me?"
- **Content, in order:** greeting with a one-line summary; four stat tiles (nodes online of total, apps running, approvals waiting with the nearest expiry, last backup with last verified restore), each linking to its screen; **Needs you** (up to two approval cards and the top open alert); installed app tiles; **widgets from apps** (typed widgets, PLUGIN-UI.md §2); recent activity (5 entries).
- **Actions:** approve or deny in place; open an app; add an app.
- **States:** nothing needs you → "Needs you" is replaced by a single calm line ("Nothing needs you"); hub unreachable → the top bar pill turns Stale/Offline and every tile says "last known".
- **Data:** contract `GET /v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/actions`. Widgets, alerts and backup tiles PROPOSED (PLG-P1, NOT-P1, BAK-B1).

### 2.2 Apps and Market · `screens/apps.png`
- **Purpose:** see installed apps, find new ones, and know before clicking whether an app can be installed.
- **Content:** search; category chips; **Installed** cards (status, Open); **Market** cards (tier pill, licence, archs, memory, and the reason Install is disabled when it is).
- **Actions:** Request install → creates `app.install` and shows a toast linking to Approvals; Open (per-app subdomain behind the gateway login, REC-W11-03, PROPOSED in SEC-P2/UX-P2); **Deploy your own** (DEP-P1, PROPOSED).
- **States:** scan missing, failed or older than 7 days → Install disabled with the reason (contract §10.3, §11.4); blocked tier → "Blocked"; no node fits → "No node has enough free memory" (FAB-P3).
- **Data:** contract `GET /v1/apps` with `links`, `tier`, `scan` (§11.4).

### 2.3 App page, with trust card · `screens/app-home-assistant.png`, `app-immich.png`
- **Purpose:** what the app is, whether to trust it, what it does on this box, and its lifecycle.
- **Layout (StartOS service-page pattern):** header (icon, name, description, running state and node); action row; left column: **Settings** (panel supplied by the app, PLUGIN-UI.md §3), **Data and backup** (volumes, exclusions, last backup, database consistency), **Logs** (tail, download; UX-P4), **History** (installs, updates, reverts, who approved); right column: **TrustCard**.
- **TrustCard** shows a verdict first ("Can install" / "Cannot install" and why), then Market tier, licence and licence class, last scan date and result, vulnerability counts, malware scan, image signature, archs and memory, **"It will be able to"** (plain-language permissions, Olares pattern), and links (Docs, Source, Website, Support). For an app that is not installed it adds **placement**: which node it would run on, or "why not" per node (APP-B3).
- **Actions:** Open; Update to X (a request; health-gated with snapshot and automatic revert, APP-B1); Restart; Remove… (alertdialog: "data volumes are kept", APP-P2); Request install. Changing a setting is a request too.
- **Install review (PROPOSED, pattern from umbrelOS, study only):** after "Request install", a short stepped dialog with one concern per step (folders it may use, GPU, exposure) before the request is created. Steps that do not apply are skipped.
- **Data:** contract §3/§9.3/§11.4 for trust facts. Scan counts (critical/high/malware/cosign) are in `scan.json` (§11.1) but not yet in the catalog summary; **PROPOSED** to add them to §11.4. Logs, settings, history, placement: PROPOSED (APP-P3, FAB-P3).

### 2.4 Approvals · `screens/approvals.png`, `approvals-dark.png`, `approvals-phone.png`
- **Purpose:** the single place where change happens.
- **Content:** **Waiting** (ApprovalCards: who asked with Person/Agent/System pill, why, impact, expiry countdown, exact request and API equivalent); **Recent decisions** (table: request, asked by, decided by, when, result).
- **Actions:** Approve, Deny. Deep links (`/approvals?highlight=<id>`) highlight one card, as the current dashboard does.
- **States:** expired → "Expired", buttons disabled with reason; viewer not owner → disabled with "Only the owner can approve."; failed or outcome unknown → the hub's message; empty → "Nothing is waiting" with the API query.
- **Data:** contract `GET /v1/actions`, approve/deny. The `system:*` requester (updates, repairs, automations) is **PROPOSED**: today the contract has person and agent principals only.

### 2.5 Activity and audit · `screens/activity.png`, `activity-phone.png`
- **Purpose:** what happened, who did it, and proof nothing was hidden (UX-B1).
- **Content:** a **"Chain verified"** banner (entries checked, when, from the first entry to the latest); filters (Everything, People, Agents, System; later node and app); timeline entries with time, actor pill, text, sequence number, node/app, result pill.
- **States:** chain broken → the banner turns red and names the first bad entry, and an alert is raised.
- **Data:** contract §3 audit log (hash-chained JSONL). A read endpoint (`GET /v1/audit?after=` and `GET /v1/audit/verify`) is **PROPOSED**.

### 2.6 Nodes and fabric · `screens/nodes.png`, `nodes-dark.png`, `nodes-phone.png`
- **Purpose:** every machine, honestly (P2), and growing or shrinking the fabric.
- **Content:** NodeCards (role, board, arch, freshness pill with last seen, memory and disk meters, OS, cluster role and readiness, booted A/B slot or "no A/B (developer install)", CPU and GPU, app count); an **Add a node** card (single-use join QR, expiry, the CLI line); **Fabric links** table (bus link to the hub, identity, state).
- **Actions:** Add a node (FAB-P1, join through approval); Drain… / Remove… (FAB-P2, requests); Details (per-node page: apps, logs, metrics, updates).
- **Data:** contract `GET /v1/nodes` (§2, §3). Fabric links and join tokens PROPOSED (FAB-P1, fabric research).

### 2.7 Backups · `screens/backups.png`
- **Purpose:** "Can I get my data back?" (BAK-P1–P4, BAK-B1, BAK-B4.)
- **Content:** stats (last backup and how many destinations are current, **last verified restore**, what is protected, recovery keys present of three); an explainer of verification; **Destinations** (USB, another box, S3; last success; behind/current); **Snapshots** (time, id, size, restore-test result, Restore…); **Encryption keys** (box key, owner recovery key, offsite key).
- **Actions:** Back up now; Restore… (dialog: one app, a folder, or the whole box; current data is snapshotted first; creates a request).
- **Data:** all PROPOSED (backup agent, backlog items 3–5).

### 2.8 Updates · `screens/updates.png`
- **Purpose:** what runs, what is waiting, the policy, and what happened (OSU-P1, UX-P5, OSU-B1).
- **Content:** the waiting OS update (channel, what it fixes, the three-step explanation: snapshot, install to the other slot, keep only if healthy); **This box** (running version and slot, fallback slot, channel, maintenance window, canary policy for other nodes); **App updates** table; **History** including rollbacks with the failed check named (OSU-B3).
- **Actions:** Approve for the window; Postpone; release notes.
- **Data:** PROPOSED (updater stream `internal/update` in flight; a gateway read endpoint is needed).

### 2.9 Alerts and notifications · `screens/notifications.png`, `notifications-phone.png`
- **Purpose:** one inbox for the fabric; each alert says what happened, what it affects and what can be done (NOT-P1–P3, NOT-B1, NOT-B3).
- **Content:** alert cards (severity pill, source, age, acknowledged); **repairs** carry a fix action (HA resolution pattern) that becomes a request; alerts tied to a pending request show "Review request"; **Where alerts go** (in-app, Android UnifiedPush via the box's ntfy, iOS opaque ping then fetch per D-005, email, Matrix/Telegram); **Rules** (severity → channel, quiet hours, dedupe window).
- **Data:** alert record from backlog NOT-P1 (`{id, severity, source, audience, title, body, fixable, fix_action, created, acked_by, resolved}`), PROPOSED.

### 2.10 Settings · `screens/settings.png`
- **Sections:** **Security posture** (SEC-B4: HTTPS on the LAN, sign-in method, disk encryption, Secure Boot, app isolation, exposure, agents; each Good/Check with a detail line); **People** (name, role owner/adult/guest, sign-in method, last seen; Invite) (SEC-P1); **Agents and tokens** (identity, what it can do, last used, Revoke) (SEC-B3); **Remote access** (off by default, overlay network, exposure as a separate approved request) (REM-P1, REM-B1); **Appearance** (System/Light/Dark).
- **Data:** contract §3 principals (static tokens today); everything else PROPOSED.

### 2.11 Components · `screens/gallery.png`, `gallery-dark.png`
The visual test page: colour roles, every component in every state. Used for design review in both themes; replaces Storybook.

## 3. Mobile mapping

The phone app is a **shell over the same screens**, not a separate design (REC-W11-01, REC-W11-09).

| Phone tab / place | Screen | Phone-specific behaviour |
|---|---|---|
| Home | 2.1 | Stat tiles stack; widgets render natively from typed templates (no iframe on phones in v0) |
| Apps | 2.2, 2.3 | Open launches the app's subdomain in the in-app browser, signed in |
| Approvals | 2.4 | Approve requires device biometrics or a passkey; the approval is signed (MOB-B1, SEC-B2) |
| Activity | 2.5 | Same timeline; filters in a sheet |
| More → Alerts | 2.9 | Push notifications open the alert, or the approval directly (NOT-B3) |
| More → Nodes, Backups, Updates, Settings | 2.6–2.8, 2.10 | Read-mostly; risky actions are requests as everywhere |
| Pairing (first run) | — | Scan the box's QR (box URL + CA fingerprint + one-time token, REC-W11-16) |
| Offline | all | The last known state is cached and labelled with its age, never shown as live (MOB-B2, P2) |

**Shell technology conflict (flagged, not decided here):** REC-W11-09 and backlog item 17 say **Capacitor** over the web UI. The in-flight mobile worktree builds an **Expo / React Native** app with its own screens and a minimal token file. Both can use this design system: Capacitor would load the `ui/` components directly; React Native would read `dist/tokens.json` (same colours, spacing, radius) and mirror the components. The founder should pick one; the tokens are ready for either.

## 4. Screen states checklist (every screen)
| State | Rule |
|---|---|
| Loading | Skeleton of the layout, no spinner taking the whole page; after 10 s say what is slow |
| Empty | Say why it is empty and what happens next; show the command (EmptyState) |
| Error | Show the contract error code and message; link to docs when DOC-B1 lands |
| Stale | Dashed card, Stale pill, "last report N ago, not live" |
| Forbidden | Show the control disabled with the reason, never hide it silently |
| Demo | "Demo data" flag in the top bar |
