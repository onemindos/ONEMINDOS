<!-- SPDX-License-Identifier: Apache-2.0 -->
# Backups switched on (gateway side)

**Serves:** CORE-BACKUP-6 (restore, approval-gated, with undo), CORE-BACKUP-7 (verified badge), CORE-BACKUP-8 and DEV-API-11 (API), CORE-BACKUP-5 (manifest hooks), BACKUP-WIRE-1, DB-SHARED-1. **Contract:** `sdk/contracts/poc-v0.md` §12.12 (routes), §12.5 (action types), §12.11 (signed jobs), §12.18 (`spec.backup`). **Design:** `docs/architecture/BACKUPS.md`. **Agent:** `internal/backup/` (`onemindd backup`).

> **In plain words.** Two programs share the work. The *agent* (`onemindd backup`) is the only one that touches files: it runs restic, which copies what changed into an encrypted backup. The *gateway* (this package) decides: which disk or bucket to use, when to run, and what each app needs first. Before each hourly run it asks every app to make a clean copy of its own data (for example a database dump) **inside the app's own container**, and it dumps each app's PostgreSQL database. Then it sends the agent a *job* signed with its private key; the agent does nothing it was not asked to by that key. Restoring an app is always something you approve. The box first saves today's data (so the restore can be undone), stops the app, puts the old data back, starts the app and watches it come up. If it does not come up, today's data goes back automatically.

## How the pieces talk

```
owner / agent ──REST──▶ gateway ── kubectl exec (hooks, pg_dump, pg_restore) ──▶ app pods, shared PostgreSQL
                          │
                          └─ signed onemind.job/v1 ─▶ 127.0.0.1:7480 onemindd (backup.Service) ── restic ──▶ USB / box / S3
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
| `GET /v1/backups/content` | read | apps whose manifest marks re-downloadable content (`spec.backup.content`: ZIMs, maps, models) with the content tier on or off and its size now, measured by the agent |
| `POST /v1/backups/content` | owner | `{app_id, enabled, seen_size_bytes?}` → `202` `backup.content.set`; on needs the size the owner saw (BAK-03) |
| `GET /v1/backups/verifications` | read | `{unit, snapshot_id, mode, result: pass\|fail\|error, probes}` |
| `POST /v1/restores` | owner | `{snapshot_id, scope: {app_id} \| {app_id, path}}` → `202` `backup.restore` plus `restore.plan` |
| `GET /v1/restores`, `/restores/{id}` | read | state, plan, steps, `pre_restore_snapshot_id`, `health_gate` |
| `GET /v1/backups/kit` | owner | `{state: missing\|issued\|confirmed, positions}` |
| `POST /v1/backups/kit` | owner | issues the emergency kit; `201` with `one_time: {owner_key, groups, check, text, qr_payload}`, shown once |
| `POST /v1/backups/kit/confirm` | owner | `{answers: {"<pos>": "<group>"}}`: two key groups typed back |
| `GET /v1/databases` | owner, adult | apps' databases on the shared PostgreSQL (no passwords) |

Every request accepts `reason`, `expires_at` (≤ 7 days, default 24 h), the `Idempotency-Key` header and the owner shortcut `"approve": true` (§12.1). Errors: §3 codes, plus `503 unavailable` with `reason: backups_disabled | target_unreachable` (§12.2).

## The content tier (BAK-03)

> **In plain words.** Some apps hold big files they can fetch again by themselves: Kiwix's offline Wikipedia (ZIM files), offline map archives, Ollama's models. Copying them every hour would fill the backup disk, so by default they are left out and only the app's own settings and lists are saved. If you would rather have a restore bring the whole offline library back (say you have no internet where the box lives), switch the content tier on for that app. Before you can, the box shows how big it is, and the request must carry the size you were shown.

The manifest marks the files with `spec.backup.content` patterns. Until the owner approves `backup.content.set` for the app, they are added to the app's excludes; each app snapshot is tagged `content=included|excluded`, and a restore plan says which (with a warning when the content is not in the snapshot: the app downloads it again). A restore from a snapshot without the content leaves the content out of the restored volume; carrying the current files over into the restored volume is a follow-up.

## Built-in units (`units.py`, #616)

> **In plain words.** The built-in apps (Photos, Approvals, Files and the rest) keep their data in the gateway's own database and in folders the gateway's settings name. Each one lists those tables and folders in its descriptor (`spec.backup.units`). The whole database is already copied in the agent's `system` unit, which is right for putting the same box back. On a new box the gateway may already have written its own first rows, so the export writes each built-in's rows as checked JSON lines (and copies its folders), and the restore puts them back in one transaction, or refuses and writes nothing.

`GET /v1/backups/status` lists the set as `builtin_units` (folders as set or not, never host paths). Each unit names the agent unit that carries it (`snapshot_unit`: `system` for the gateway database) and `in_snapshot`, true only when that agent unit has a successful snapshot. Without `ONEMIND_BACKUPS_EXPORT_DIR` every built-in shows `snapshot_unit: null, in_snapshot: false`: its rows are only in the whole-database copy and its folders are in no snapshot. On the image, onemind-firstboot sets it to `/data/onemind/gateway/backup-export` and adds that folder and the files root to the agent's `system` paths (`ONEMIND_BACKUPS_AGENT_DIRS=ONEMIND_FILES_ROOT`). Before each box run the gateway writes the tables-only export there as `builtin-units.tar` (a failure fails every `builtin:<id>` unit of the run; the agent still runs). A built-in is `in_snapshot` once the newest run whose `system` unit succeeded wrote the export first and that run recorded every folder it has set as carried, at the folder it points at now (the export hook's `carried`, a fingerprint per setting, never a host path): a folder added to the backup or moved after the snapshot is not in it. A folder is `carried` when its setting is in `ONEMIND_BACKUPS_AGENT_DIRS` and, when `ONEMIND_BACKUPS_AGENT_PATHS` is set (first boot writes agent.json's `system` paths there), it is one of those folders or inside one, so a relocated library reads as outside the backup. The agent runs as root without the right to change user, so the gateway writes the export itself rather than through an agent command hook; a box run reports a built-in whose declared table is missing as a failed `builtin:<id>` unit. On the box: `python -m onemind_core.backups.units list | export DIR | export --tar - | restore DIR|FILE [--replace]`. The restore refuses undeclared tables or folders, a changed file, another schema version, tables that hold rows (unless `--replace`) and folders with files in them.

## The emergency kit cannot be skipped

The owner key is 256 random bits, printed as 13 groups of four letters plus a check group. The restic password is the 13 groups with dashes, exactly as printed, so plain restic opens the backup without OneMind (the kit text lists the commands). The box keeps only a fingerprint and two salted group hashes. `status.setup.blocking` holds `emergency_kit` until the owner types those two groups back; onboarding (and `ui/src/backups/EmergencyKit`) does not offer "finish" before that.

## The shared PostgreSQL (`../databases.py`)

`spec.database: {engine: postgres, secret: <name>}` gives an app database and role `app_<id>` on one PostgreSQL per hub (`deploy/platform/postgres/`: `postgres:17.11-trixie` pinned by digest, `onemind-local` Retain storage, claims kept when the StatefulSet goes). It starts the first time an app needs it. The password goes to PostgreSQL on psql's stdin and into the app's Secret, nowhere else. Dumps (`pg_dump -Fc`) go to `onemind-dumps/` on the PostgreSQL volume and are part of that app's own snapshot, so restoring the app also brings its database back (`DROP DATABASE … WITH (FORCE)`, `CREATE DATABASE`, `pg_restore`).

## v0 choices to review (contract owner)

| Topic | Built | Why, and what replaces it |
|---|---|---|
| Agent address | `127.0.0.1:7480` under `/api/v1/backup/` (§12.12) | one backup service, inside onemindd (`backup.Service()`); no second daemon. onemindd gets four capabilities through a systemd drop-in (`deploy/systemd/onemindd-backup.conf`) |
| `spec.database` | in the schema, not in the contract | proposed §12.18 text: "`spec.database: {engine: postgres, secret}` — database and role `app_<id>` on the hub's shared PostgreSQL; Secret keys PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, DATABASE_URL" |
| Destination credentials | `credentials` in the request, held in memory until approval | `sealed` (§12.1) needs `GET /v1/secrets/public-key` from the secrets stream |
| Scheduled runs | not actions; audited `backup.schedule.fired` with `approved_by: policy:backup-schedule@1` | the automation stream's standing approvals (§12.17) make them policy-approved actions |
| `backup.verify` | file-level scratch restore by the agent, plus PostgreSQL dumps restored as part of the app | the sealed-namespace app start with fresh probes (BACKUPS.md §8 step 3-4, K7) is a follow-up |
| Whole-box restore | refused on a running box | onboarding restore (`POST /v1/onboarding/restore/candidates`) is a follow-up |
| Restore of one path | the path must be inside the app's current volumes | after a reinstall restore the whole app instead |
| Key rotation | re-issuing the kit adds a new owner key | removing the old key (`backup.key.rotate`) is a follow-up |
