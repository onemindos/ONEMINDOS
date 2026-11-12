<!-- SPDX-License-Identifier: Apache-2.0 -->
# Backups and restore

**Status:** design for build agents (2026-11-12). API in [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) §12.5.
**Backlog:** core-alignment items 3 (BAK-P1, BAK-P2, BAK-B2), 4 (BAK-B1), 5 (BAK-P3, BAK-P4, BAK-B4), 6 (ONB-B2, with ONB-P3); also BAK-P5 and BAK-B3 as later steps.
**Builds on:** brief 30 B7 (D-B7.1…D-B7.7); research 06 recommendations W5-R1…R14; context/02 §15 (RPO/RTO and the drill); the updater's pre-update snapshot (`feat/onemindd-updater`, `internal/update/engine.go`); hardening backlog H-10 (audit checkpoints) and H-11 (LUKS2 recovery key).

> **In plain words.** Every hour, each machine copies what changed in your apps' data and in the system's own records into an encrypted backup, on a USB disk, another OneMind machine, or a cloud bucket. Three different keys can open it; one of them is printed in your emergency kit and never stored on the box. Every week the box proves a backup works by actually restoring each app into a sealed sandbox and checking that it starts. Only then does the backup turn green. Restoring is always an action you approve, and a restore can itself be undone.

## 1. Requirements

| ID | Requirement | Source |
|---|---|---|
| B-R1 | Engine is restic, pinned per arch (v0.19.1) | W5-R1, D-B7.2 |
| B-R2 | Back up: app volumes, the gateway database, the audit log, the k3s datastore (online, integrity-checked), the box PKI and secrets, core NATS streams, OS settings on `/data` | D-B7.3, context/02 §15 |
| B-R3 | Hourly by default, grandfather-father-son retention, 2× free-space check | D-B7.5, W5-R10 |
| B-R4 | Targets: USB disk, another OneMind node (append-only), S3-compatible | BAK-P2, W5-R10 |
| B-R5 | Three keys per repository: device, owner recovery, optional escrow; the owner key alone restores; setup cannot finish without the emergency kit | D-B7.2, W5-R4, ONB-B2 |
| B-R6 | App hooks from the manifest `backup:` block | D-B7.4, W5-R5 |
| B-R7 | Pre-update snapshot for OS updates and app updates | D-B7.5, APP-B1 |
| B-R8 | Daily repository check; weekly scratch restore with fresh probes; "last verified restore" per app and per box; never green without a verified restore | D-B7.6, W5-R7, W5-R8, BAK-B1 |
| B-R9 | Restore one file, one app, or the whole box (also during onboarding); all approval-gated; agents may only start a backup and read status | BAK-P3, BAK-P4, W5-R13 |
| B-R10 | Exit: the backup is a standard restic repository plus plain files, restorable without OneMind | W5-R14 |
| B-R11 | App data is never deleted by removing an app; storage class keeps volumes (`Retain`) | D-B7.1, W5-R9, APP-P2 |

## 2. What is backed up

A **unit** is something that is backed up and restored as one piece. Each unit becomes one restic snapshot per run, tagged so it can be found without OneMind.

| Unit | Contents | Runs on | How it is made consistent |
|---|---|---|---|
| `system` | gateway database; audit log (`audit.jsonl` + checkpoints); `/data/onemind/custodian/` (box CA, NATS signing key, job key); app revisions and private bundles (`/data/onemind/deploy/`); app secrets store (already encrypted, §6.4); OS settings under `/data/onemind/` (`update.conf` overrides, node name, identity) | hub | Gateway DB: SQLite online backup (`sqlite3 … ".backup"`) or `pg_dump` when on PostgreSQL. Audit log: copy, then verify the chain of the copy and record its head hash as a tag |
| `k3s` | `state.db` via SQLite online backup; `PRAGMA integrity_check` must return `ok` or the unit **fails**; server `token`, encryption config, node password; the exact k3s version as a tag | hub | D-B7.3; never a raw file copy outside restic (lab result [C-LAB-k3s-footprint-restore-011]) |
| `nats` | JetStream core streams (`ONEMIND_AUDIT`, `ONEMIND_EVENTS`) via the JetStream snapshot API | hub | Stream snapshot; app streams later (bus-as-code, gap list) |
| `app:<id>` | every PVC of the app (host directories of `onemind-local` volumes), the app's revision id, hook output (e.g. a database dump) | the node holding the volumes | Manifest `backup:` hooks (§2.2); otherwise crash-consistent copy (§2.3) |
| `node:<id>` | that node's `/data/onemind/identity/` and settings | each worker / leaf | Small files; lets a node be rebuilt with the same identity |

**Not backed up:** container images (reinstalled by digest), `/data/rauc`, caches, the restic cache, logs, anything excluded by an app manifest. Images are the main size saver; the trade-off is that a restore needs the registry or a local image cache. That is shown on the restore screen.

### 2.1 Storage the backups rely on (D-B7.1)

The gateway's platform layer (DEPLOYMENTS.md §2.2) installs the StorageClass `onemind-local`: local-path provisioner, `reclaimPolicy: Retain`, path `/data/onemind/storage`, and it is the default. k3s's own `local-path` class loses its default flag. A second class, `onemind-scratch` (`Delete`), is only for verification and temporary restores. The backup agent finds a PVC's directory and node from its PersistentVolume.

### 2.2 The manifest `backup:` block (W5-R5; schema in CONTRACT-12-DRAFT §12.13)

```yaml
spec:
  backup:
    mode: hot                  # hot (default) | cold (stop the app while copying)
    pre:  {exec: {container: db, command: ["sh", "-c", "pg_dump -Fc -f /var/lib/postgresql/data/onemind-dump.pgc app"]}}
    post: {exec: {container: db, command: ["rm", "-f", "/var/lib/postgresql/data/onemind-dump.pgc"]}}
    sqlite: ["/data/app.db"]   # paths inside a volume to copy with the SQLite online backup
    exclude: ["cache/", "*.tmp"]
    restore:
      post: {exec: {container: db, command: ["sh", "-c", "pg_restore …"]}}
    verify:                    # extra fresh check after a scratch restore (§5)
      http: {port: 3001, path: /api/status, expect: 200}
```

Hooks run **inside the app's pod** through the Kubernetes API, started by the gateway, because workers have no Kubernetes credentials (FABRIC.md §5.4). This is the pattern Home Assistant's Supervisor uses when it freezes apps before a backup (`supervisor/backups/manager.py`, Apache-2.0, `home-assistant/supervisor` `040f14c`; pattern only).

### 2.3 Apps without a `backup:` block

They are copied **hot** (crash-consistent: like pulling the power plug). That is usually fine for apps that keep their data in SQLite with a write-ahead log, and sometimes not. The weekly verified restore (§5) **is what decides**: if the copy does not come back healthy, the app's badge turns red and a repair suggests `mode: cold` for that app (owner approval). Defaulting to cold would stop every app every hour; defaulting to hot without a test would be a guess.

## 3. Schedules and retention

Every schedule is a **system automation** (AUTOMATION.md §3.4): it creates an action that the built-in system policy approves, visible and tightenable by the owner.

| Job | Default | Notes |
|---|---|---|
| Backup run (all units) to the primary target | hourly, at a random minute fixed per box | `system` and `k3s` first, then apps node by node |
| Copy to the off-site target | daily, inside the maintenance window | restic `copy`, or a direct run when the off-site target is the only one |
| Retention (`forget`) | after each run | hourly 24, daily 7, weekly 4, monthly 12 (`--keep-hourly 24 --keep-daily 7 --keep-weekly 4 --keep-monthly 12`); `reason=pre-update` snapshots kept 14 days on their own rule |
| `prune` | weekly, in the window | never on an append-only target from the source box (§4) |
| Repository check | daily: `restic check --read-data-subset=<n>/7` rotating, so all data is read every week; S3 targets weekly `n/28` to limit egress cost | on a failure: retry once, then run a memory test before reporting damage (D-B7.6) |
| Verified restore | weekly per app; system unit weekly | §5 |

**Space check (D-B7.5):** before a run, the agent estimates new data (restic `--dry-run` is too slow on small boxes, so the estimate is the change in volume sizes since the last run plus 10 %). If the target's free space is less than 2× that, the run is refused and an alert says how much space is needed.

**A run** is one id grouping all unit snapshots taken together: the **restore point** the owner picks from. A run's state is `succeeded` only when every unit succeeded. Otherwise it is `partial` with the failed units listed. A partial run is still a restore point for the units that made it.

## 4. Targets

| Kind | restic backend | Set up | Delete protection |
|---|---|---|---|
| `usb` | local path on a disk found by filesystem UUID, mounted at `/run/onemind/backup/<uuid>` | plug in, choose "Use for backups"; formatting is a separate action showing the disk model and size | A disk can be unplugged and stored away (the strongest protection) |
| `node` | `rest:` to a OneMind node running `rest-server --append-only --private-repos` over the fabric's TLS | choose a node; the target node gets a per-box user | **append-only:** the source box can add snapshots but cannot delete or overwrite them (BAK-B3; [rest-server docs](https://github.com/restic/rest-server#append-only-mode)) |
| `s3` | `s3:` any S3-compatible endpoint | endpoint, bucket, access key (stored in the secret store) | Recommend a bucket with object lock or versioning; the UI says when neither is detected (UNVERIFIED which providers expose this through the API; the check is best-effort) |
| `buddy` (later) | `rest:` to a friend's OneMind box over remote access | invitation code | append-only, as `node` |

Defaults: the first target set up is the **primary** (hourly). A second target on another device or off-site is strongly suggested (3-2-1, W5-R10), and the box badge says "1 copy only" until there are two.

**Pruning append-only targets:** the source box never holds delete rights. `backup.prune` for a `node` target is an owner-approved action that runs **on the target node** as a job. The owner unlocks it with the recovery key (typed or scanned from the kit) for that one job. The key is held in memory only. This is the one path that deletes data from such a target, and it needs a person.

## 5. Keys and the emergency kit

### 5.1 Three keys (D-B7.2, W5-R4)

restic lets one repository have several keys (`restic key add`); each opens the same data.

| Key | Where it lives | Used for |
|---|---|---|
| **device** | `/data/onemind/secrets/backup-device.key` (0600 root; TPM-sealed when `tpm2` is present, phase 3). On LUKS2 `/data` (H-11) it is also encrypted at rest | all scheduled work |
| **owner recovery** | **only** in the emergency kit; the box keeps the restic key id, not the key | restore onto new hardware; unlocking prunes on append-only targets |
| **escrow** (optional) | a second printed copy for a trusted person, or the owner's password manager | the owner loses the kit |

Each key is 256 random bits, shown as 13 groups of 4 base32 characters plus a check group, and as a QR code. They are never derived from a password (W5-R4). The **same three keys** are added to every target repository, so any one key opens any target.

**Rotation** (`backup.key.rotate {which}`, owner, passkey): add the new key to every target, verify it opens each, then remove the old key. A new kit is issued (one-time output).

### 5.2 The emergency kit

A printable page (and PDF) generated in the browser from a one-time response. It holds:
- box name, instance id, the box CA fingerprint;
- the owner recovery key (text + QR);
- the LUKS2 data-partition recovery key, when H-11 is built (same "shown once" rule);
- each target's location (path, node, endpoint and bucket); S3 credentials only if the owner ticks "include", with a warning;
- restore steps in plain words, **including the plain restic commands** to restore without OneMind (W5-R14).

**Cannot be skipped (ONB-B2):** setup does not finish until the owner types back two key groups the box picks at random. That proves the kit was saved, not just shown.

## 6. Pre-update and pre-restore snapshots

### 6.1 OS updates
The updater (`internal/update/engine.go`) snapshots `/data` with its own restic settings in `update.conf`. Change: when the backup agent is configured, the updater instead calls it on the local API (`POST :7480/api/v1/backup/run {reason: "pre-update", wait: true}`, loopback only). That takes a full run with `reason=pre-update`. The `restic_*` keys in `update.conf` stay as an override for boxes without the agent. The existing "security installs anyway with `snapshot: none` + warning" rule is kept.

### 6.2 App updates and restores
`app.update` (DEPLOYMENTS.md §5) and `backup.restore` both take an `app:<id>` snapshot with `reason=pre-update` / `reason=pre-restore` first, so **every restore can be undone** by restoring that snapshot.

### 6.3 Removal
`app.remove` keeps the volumes (Retain). `app.data.delete` takes a final `reason=pre-delete` snapshot, kept 30 days, then deletes the PersistentVolumes and directories (APP-P2).

### 6.4 Secrets
App secrets in the gateway's secret store are encrypted with a key derived from the device key. They travel inside the `system` unit and are useless without that key or the owner key: the kit's owner key opens the restic repository, which contains the device key inside the `system` unit's custodian directory.

## 7. Restore

### 7.1 Browse and restore one file
`GET /v1/backups/snapshots/{id}/tree?path=` lists; `GET …/file?path=` downloads. Reading is owner-only, audited, and never offered to agents. Restic's `dump` streams the file. Restoring a file **into** a running app is `backup.restore` with `scope: path`.

### 7.2 Restore one app (`backup.restore {scope: app, app_id, snapshot_id}`)
1. **Plan** (shown on the approval card): snapshot time and age, app version then vs now, volumes and sizes, "the current data will be saved first as a pre-restore snapshot", expected downtime.
2. Take the `pre-restore` snapshot.
3. Scale the app to zero (the gateway).
4. Job on the volume's node: move each volume directory aside to `<dir>.onemind-old-<ts>`, then `restic restore` into the empty directory.
5. If the snapshot's app revision differs from the current one, re-apply the snapshot's revision (data and code from the same moment). The plan says so.
6. Run `restore.post` hooks; scale up; wait for **fresh** health (§8).
7. Pass → delete the moved-aside directories after 24 h. Fail → put the old directories back, re-apply the previous revision, result `failed` with the reason. If even that fails → `outcome_unknown` and a repair.

### 7.3 Restore the whole box onto new hardware (BAK-P4, ONB-P3)
Offered in onboarding as "Restore from a backup" and in `onemind init --restore` (headless twin, ONB-B1).

1. Choose a target: plug in the USB disk, enter the S3 details, or point at a OneMind node.
2. Enter or scan the **owner recovery key**.
3. The box lists the boxes found in the repository (`restic snapshots --tag onemind,unit=system`, grouped by instance id), with the last run time of each, and the restore points.
4. Choose the **mode** (W5-R6):
   - **portable** (default): restore `system` (identity, PKI, gateway DB, revisions, secrets, audit), start a fresh k3s, re-apply every app's recorded revision (images by digest), then restore each `app:` unit. It works across CPU architectures whenever the image digests are multi-arch indexes; the plan lists apps that are not.
   - **exact**: also restore `k3s` (same architecture and k3s version required; checked against the snapshot's tags). Use it when there are Kubernetes objects OneMind does not know about.
5. **Fencing:** the restored box gets `generation + 1` and writes a small `fence` snapshot (`unit=fence, generation=N`) to every target. Before every run, a backup agent checks the newest fence; if it is newer than its own generation, the box **stops backing up** and raises a critical alert: "This box was replaced by a restore on <date>". This stops two machines writing as the same box.
6. Fresh health gate (§8) over the whole box; old node certificates are deny-listed; the owner is told to re-join workers (their identities can be restored from `node:` units).

**Why portable is the default:** OneMind records every app's desired state as revisions in its own database. So the k3s datastore is a second safety net, not the source of truth. That makes cross-architecture and cross-version restores possible, which a raw datastore copy is not (StartOS also restores across CPU architectures: research 02-competitors `startos.md`, [C-TD-startos-035]).

## 8. Verified restores and the badge (BAK-B1, the beat)

**Rule (D-B7.6):** a backup counts as verified only when a restore of it has passed checks that use **fresh** signals: new pods, new readiness, a new file read. It never counts by trusting restored status fields. The lab saw a restored API report healthy pods that did not exist yet ([C-W5-010], W5-R8).

**Weekly per app** (system automation, in the window, one app at a time to keep load low):
1. Pick the newest `app:<id>` snapshot that is ≥ 1 h old.
2. On the app's node (or any node with room), restore into `/data/onemind/scratch/verify-<id>-<ts>/` (job).
3. The gateway creates namespace `verify-<id>-<short>` with PSA `restricted`, a default-deny NetworkPolicy (no ingress, no egress except DNS for in-namespace names), static PVs pointing at the scratch directories (pinned to that node), and the app's revision rendered into that namespace with replicas 1, no agent principal and no secrets beyond what the app needs to start.
4. Wait for readiness of pods **created after step 3**, then the manifest's `backup.verify` check (default: HTTP 200 on `web.port` from inside the namespace), 3 passes in a row over 60 s, deadline 10 min.
5. Record the verdict, delete the namespace and the scratch directories.

**Weekly system:** restore `system` and `k3s` into scratch; `PRAGMA integrity_check` on both databases; verify the audit chain of the restored copy up to the tagged head hash (and against the latest signed checkpoint, H-10); check that `state.db` is within its size budget and that kine compaction is not lagging (REC-DEC-49). A full system drill (fresh VM, both modes) runs nightly in CI per shipped k3s version (D-B7.7) and monthly on hardware as an opt-in owner drill.

**The badge** (per app, per box, on Home, the app page, the Backups screen, the phone):

| Badge | When |
|---|---|
| **Verified** (green) | last verified restore passed ≤ 8 days ago **and** the last run succeeded ≤ 2 h ago (hourly schedule) |
| **Backed up, not verified** (amber) | runs succeed, but no passing verification in 8 days |
| **Stale** (amber) | no successful run within 2× the schedule |
| **Failing** (red) | the last verification failed, or the last 3 runs failed, or the repository check reports damage |
| **None** (grey) | the app has no volumes or backups are not set up |

The box badge is the worst of its apps plus `system`. Each badge says its age ("verified 3 days ago"). No competitor read for this page proves its restores; umbrelOS, Home Assistant and StartOS show "last backup" only (core-alignment §4.6).

## 9. Who may do what (W5-R13)

| Action type | Owner | Agent | Automation | Policy may auto-approve |
|---|---|---|---|---|
| `backup.run` | yes | **request** | request | yes (default system policy) |
| `backup.verify` | yes | request | request | yes |
| read status, runs, badges | yes | yes (`backup_status` MCP tool) | — | — |
| browse / download files | yes | no | no | — |
| `backup.restore` | yes | no (403) | no | **never** |
| `backup.target.add` / `.remove`, `backup.key.rotate`, `backup.prune`, `backup.kit.issue` | yes, with passkey | no | no | **never** |

"Restoring an attacker's snapshot hands them the box" ([C-W5-013]), which is why restore and target changes are never automatable.

## 10. Data model (gateway database)

```
backup_targets(id, kind[usb|node|s3|buddy], name, location_json, secret_ref, primary bool,
               repo_id, key_ids_json, created_at, last_ok_at, state[ok|unreachable|full|damaged])
backup_runs(id, reason[scheduled|manual|pre-update|pre-restore|pre-delete], action_id, target_id,
            started_at, finished_at, state[running|succeeded|partial|failed], units_json, bytes_added)
backup_snapshots(id, run_id, target_id, restic_id, unit, node_id, app_id, app_revision,
                 k3s_version, size_bytes, taken_at, tags_json)
backup_verifications(id, unit, snapshot_id, kind[app|system|check], started_at, finished_at,
                     verdict[passed|failed|error], details_json)
backup_state(box generation, fence_seen_generation, settings_json)   -- one row
```

**restic tags on every snapshot** (so the repository explains itself without OneMind): `onemind`, `box=<instance_id>`, `gen=<n>`, `unit=<unit>`, `node=<node_id>`, `run=<run_id>`, `reason=<reason>`, and per unit `app=<id>`, `rev=<revision>`, `k3s=<version>`, `audit_head=<hash>`.

## 11. Security

- The repository is encrypted by restic (AES-256 in counter mode with Poly1305-AES, per restic's design docs). Keys never pass through the gateway process except the device key at run time, and the owner key only during the jobs that need it.
- Targets are reached over TLS (S3, fabric), or are physically local (USB).
- Append-only `node` targets mean a compromised box cannot erase its own history on another node.
- File browsing is owner-only and audited, because backups contain everything.
- The verification sandbox has no egress, so a restored app cannot phone home or act on the outside world during the test.
- Every backup action, verification verdict and key change is in the audit log.

## 12. Test plan and acceptance criteria

| # | Test | Pass when |
|---|---|---|
| BT-1 | Hourly run on a hub with 3 seed apps (VM) | `system`, `k3s`, 3 `app:` snapshots exist with all tags; run `succeeded`; `restic snapshots` without OneMind lists them |
| BT-2 | Corrupt `state.db` copy (fault injection: integrity check returns errors) | `k3s` unit fails; run `partial`; alert raised; no `k3s` snapshot written |
| BT-3 | Owner key alone | On a fresh VM with only the kit's key, `restic -r <target> snapshots` works and the documented plain-restic steps bring back an app's files |
| BT-4 | Kit cannot be skipped | Onboarding refuses to finish until two random key groups are typed back |
| BT-5 | Restore one app, then undo | Data matches the snapshot; then restoring the `pre-restore` snapshot brings back the newer data |
| BT-6 | Failed restore rolls back | A snapshot whose app fails its probe → result `failed`, old directories back, app healthy on old data |
| BT-7 | Whole-box portable restore (port `k3s-footprint-restore/` T1–T6) | Fresh VM: all apps running with identical data; audit chain verifies; owner signs in |
| BT-8 | Exact restore with a k3s version mismatch | Refused before any change, with the versions named |
| BT-9 | Fence | After BT-7, the original VM's next run stops with the "replaced" alert and writes nothing |
| BT-10 | Verified restore with fresh signals | Verification of a good app passes; for an app whose restored data is broken, it fails even though restored objects carry `Ready` status (fresh-signal check) |
| BT-11 | Badge logic (unit, fake clock) | All five badge states at their boundaries (8 days, 2 h, 3 failures) |
| BT-12 | Append-only target | From the source box, `restic forget` against the `node` target is refused by rest-server; `backup.prune` as an approved job on the target succeeds |
| BT-13 | Agent rights | Agent `backup.run` → action; agent `backup.restore` → 403; a policy naming `backup.restore` is refused at creation |
| BT-14 | Space check | Target with too little room → run refused with the needed size in the alert |
| BT-15 | Pre-update | `onemind update apply` with the agent configured produces a `reason=pre-update` run before `rauc install` |

## 13. Build steps

| Step | What | Size | Depends on |
|---|---|---|---|
| K1 | `onemind-local` (Retain) and `onemind-scratch` classes in the platform layer; remove app keeps data | S | DEPLOYMENTS D1 |
| K2 | Backup agent in `onemindd` (Go): restic runner pinned per arch, units `system`/`k3s`/`app`/`node`, tags, local API `POST /api/v1/backup/run`; jobs `backup.run`, `backup.restore`, `backup.verify-restore`, `backup.check` | L | FABRIC F4 (jobs) |
| K3 | Gateway coordinator: targets, schedules as system automations, runs, hooks via exec, retention, space check, status API, Backups screen | M | K2, AUTOMATION A1 |
| K4 | Keys and kit: three keys, kit page, type-back check, rotation | S | K3, SEC-P1 |
| K5 | Targets: USB detection and format action; `node` with rest-server append-only; S3 | M | K3, FABRIC F2 |
| K6 | Restore: file browse, app restore with undo, whole-box restore in onboarding (portable, then exact), fencing | M | K3, ONB-P1 |
| K7 | Verified restores and badges (app + system), repository check with retry and memory test | M | K6 |
| K8 | Manifest `backup:` hooks in the schema, app-gate and seed apps; CI backup/restore of seed apps (D-B7.4) | M | K3, pipeline merged |
| K9 | Updater integration (§6.1) and CI restore drill per k3s version (D-B7.7) | S | K2, updater merged |
