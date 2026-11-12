<!-- SPDX-License-Identifier: Apache-2.0 -->
# Backups switched on (gateway side)

**Serves:** CORE-BACKUP-6 (restore, approval-gated, with undo), CORE-BACKUP-7 (verified badge), CORE-BACKUP-8 and DEV-API-11 (API), CORE-BACKUP-5 (manifest hooks), BACKUP-WIRE-1, DB-SHARED-1. **Contract:** `sdk/contracts/poc-v0.md` §12.12 (routes), §12.5 (action types), §12.11 (signed jobs), §12.18 (`spec.backup`). **Design:** `docs/architecture/BACKUPS.md`. **Agent:** `internal/backup/` (`onemindd backup`).

> **In plain words.** Two programs share the work. The *agent* (`onemindd backup`) is the only one that touches files: it runs restic, which copies what changed into an encrypted backup. The *gateway* (this package) decides: which disk or bucket to use, when to run, and what each app needs first. Before each hourly run it asks every app to make a clean copy of its own data (for example a database dump) **inside the app's own container**, and it dumps each app's PostgreSQL database. Then it sends the agent a *job* signed with its private key; the agent does nothing it was not asked to by that key. Restoring an app is always something you approve. The box first saves today's data (so the restore can be undone), stops the app, puts the old data back, starts the app and watches it come up. If it does not come up, today's data goes back automatically.

## How the pieces talk

```
owner / agent ──REST──▶ gateway ── kubectl exec (hooks, pg_dump, pg_restore) ──▶ app pods, shared PostgreSQL
                          │
                          └─ signed onemind.job/v1 ─▶ 127.0.0.1:7481 onemindd backup ── restic ──▶ USB / box / S3
```

- **Job signature.** Ed25519 over canonical JSON (`jobs.py` and `internal/backup/canonical.go` agree byte for byte; both test suites hold the same vector). The job key is `<state>/custodian/job.key` (0600, created on first start); the agent reads the public half from `job_pubkey_file`. Each job has an id the agent remembers (no replay) and expires after 10 minutes (60 s clock skew allowed).
- **Who may do what.** Reads (`status`, `runs`, `snapshots`, `verifications`, `restores`): owner, adult, agent. Browsing and downloading files from a snapshot: owner only, each read audited (`backup.browse`, `backup.download`). Requests: `backup.run` and `backup.verify` by owners and agents; `backup.restore`, `backup.destination.add|remove`, `backup.kit.issue` by owners only. Approving: owners only, always.

## API (contract §12.12)

| Method and path | Who | What |
|---|---|---|
| `GET /v1/backups/status` | read | `{health, reason, last_success_at, last_verified_restore_at, next_run_at, copies, badges: {box, system, apps}, destinations, kit, crash_consistent_apps, setup: {blocking}}` |
| `GET /v1/backups/destinations` | owner, adult | destinations, never credentials |
| `POST /v1/backups/destinations` | owner | `{kind: usb\|box\|rest\|s3, label, primary?, config, credentials?}` → `202` `backup.destination.add` |
| `DELETE /v1/backups/destinations/{id}` | owner | `202` `backup.destination.remove`; the repository itself is left untouched |
| `POST /v1/backups/runs` | owner, agent | `{scope: "box"\|{app_id}, destination_id?}` → `202` `backup.run` |
| `GET /v1/backups/runs`, `/runs/{id}` | read | runs with units, hook results, errors |
| `GET /v1/backups/snapshots?app_id&unit`, `/snapshots/{id}` | read | restore points, with `verified_at` |
| `GET /v1/backups/snapshots/{id}/tree?path=`, `/file?path=` | owner | Rewind: browse a snapshot, download one file |
| `POST /v1/backups/verify` | owner, agent | `{mode: scratch_restore\|check, latest, units?}` → `202` `backup.verify` |
| `GET /v1/backups/verifications` | read | `{unit, snapshot_id, mode, result: pass\|fail\|error, probes}` |
| `POST /v1/restores` | owner | `{snapshot_id, scope: {app_id} \| {app_id, path}}` → `202` `backup.restore` plus `restore.plan` |
| `GET /v1/restores`, `/restores/{id}` | read | state, plan, steps, `pre_restore_snapshot_id`, `health_gate` |
| `GET /v1/backups/kit` | owner | `{state: missing\|issued\|confirmed, positions}` |
| `POST /v1/backups/kit` | owner | issues the emergency kit; `201` with `one_time: {owner_key, groups, check, text, qr_payload}`, shown once |
| `POST /v1/backups/kit/confirm` | owner | `{answers: {"<pos>": "<group>"}}`: two key groups typed back |
| `GET /v1/databases` | owner, adult | apps' databases on the shared PostgreSQL (no passwords) |

Every request accepts `reason`, `expires_at` (≤ 7 days, default 24 h), the `Idempotency-Key` header and the owner shortcut `"approve": true` (§12.1). Errors: §3 codes, plus `503 unavailable` with `reason: backups_disabled | target_unreachable` (§12.2).

## The emergency kit cannot be skipped

The owner key is 256 random bits, printed as 13 groups of four letters plus a check group. The restic password is the 13 groups with dashes, exactly as printed, so plain restic opens the backup without OneMind (the kit text lists the commands). The box keeps only a fingerprint and two salted group hashes. `status.setup.blocking` holds `emergency_kit` until the owner types those two groups back; onboarding (and `ui/src/backups/EmergencyKit`) does not offer "finish" before that.

## The shared PostgreSQL (`../databases.py`)

`spec.database: {engine: postgres, secret: <name>}` gives an app database and role `app_<id>` on one PostgreSQL per hub (`deploy/platform/postgres/`: `postgres:17.11-trixie` pinned by digest, `onemind-local` Retain storage, claims kept when the StatefulSet goes). It starts the first time an app needs it. The password goes to PostgreSQL on psql's stdin and into the app's Secret, nowhere else. Dumps (`pg_dump -Fc`) go to `onemind-dumps/` on the PostgreSQL volume and are part of that app's own snapshot, so restoring the app also brings its database back (`DROP DATABASE … WITH (FORCE)`, `CREATE DATABASE`, `pg_restore`).

## v0 choices to review (contract owner)

| Topic | Built | Why, and what replaces it |
|---|---|---|
| Agent address | `127.0.0.1:7481` (§12.12 names `:7480`) | the agent is its own process with its own capabilities; the heartbeat agent keeps `:7480`. Proposed contract edit: name `:7481` for `onemindd backup` |
| `spec.database` | in the schema, not in the contract | proposed §12.18 text: "`spec.database: {engine: postgres, secret}` — database and role `app_<id>` on the hub's shared PostgreSQL; Secret keys PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, DATABASE_URL" |
| Destination credentials | `credentials` in the request, held in memory until approval | `sealed` (§12.1) needs `GET /v1/secrets/public-key` from the secrets stream |
| Scheduled runs | not actions; audited `backup.schedule.fired` with `approved_by: policy:backup-schedule@1` | the automation stream's standing approvals (§12.17) make them policy-approved actions |
| `backup.verify` | file-level scratch restore by the agent, plus PostgreSQL dumps restored as part of the app | the sealed-namespace app start with fresh probes (BACKUPS.md §8 step 3-4, K7) is a follow-up |
| Whole-box restore | refused on a running box | onboarding restore (`POST /v1/onboarding/restore/candidates`) is a follow-up |
| Restore of one path | the path must be inside the app's current volumes | after a reinstall restore the whole app instead |
| Key rotation | re-issuing the kit adds a new owner key | removing the old key (`backup.key.rotate`) is a follow-up |
