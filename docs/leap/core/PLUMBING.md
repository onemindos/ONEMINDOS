<!-- SPDX-License-Identifier: Apache-2.0 -->
# Core plumbing: how to add a feature

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/core-plumbing` · **Serves:** BACKLOG S1 "plumbing"; lets the gateway-core, security, fabric, backups, notifications, automation and updates streams ([WORKSTREAMS.md](../WORKSTREAMS.md) §2) work in parallel without editing the same lines.

> **Explain it like I am the founder**
> Before this change, the gateway was one long function: every new feature had to edit the middle of `app.py`, so two streams working at once would collide on every merge. Now each feature lives in its own file and plugs in with **one line** in a list. The same goes for the database (each feature owns its tables and its own upgrade steps), settings (each feature reads its own `ONEMIND_<FEATURE>_*` variables), events (one call records a fact in the audit log and tells everyone listening), the `onemind` command (one file per command group) and the `onemindd` daemon (one line per optional service). Nothing the box does changed: the API, its OpenAPI document and every command's output are byte-for-byte the same.

## 1. The map

| You are adding | Write | Register with one line in |
|---|---|---|
| REST routes | `core/onemind_core/routers/<feature>.py` with `register(app, gw)` | `ROUTERS` in `core/onemind_core/app.py` (before `static`) |
| Logic and state | `core/onemind_core/<feature>.py` (or a `<feature>/` package) | imported by your router |
| Database tables | models on `ledger.Base` + `FeatureSchema("<feature>")` + a `SqlRepository` subclass, in your feature module | nothing (importing the module registers it) |
| Settings | a frozen dataclass with `@config_section("<feature>")` | nothing (importing the module registers it) |
| An event | `gw.events.publish_event("<domain>", "<name>", {...})` | — |
| A listener | `gw.events.subscribe("<pattern>", handler)` in your `register` | — |
| Background work in the gateway | `gw.on_startup(fn)` / `gw.on_shutdown(fn)` in your `register` | — |
| An `onemind` command group | `cmd/onemind/cli/<group>.go` with `func <group>Commands() []Command` | `groups` in `cmd/onemind/cli/root.go` |
| An `onemindd` mode (own process) | `runX(args []string) int` | `subcommands` in `cmd/onemindd/registry.go` |
| An `onemindd` service (inside the agent) | `internal/<feature>` exporting `Service() service.Service` | `optionalServices` in `cmd/onemindd/registry.go` |

`app.py`, `config.py`, `cmd/onemindd/main.go` and `cmd/onemind/main.go` stay hotspots ([WORKSTREAMS.md](../WORKSTREAMS.md) §4): a feature PR touches only the one registry line.

## 2. Routes: `routers/<feature>.py`

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import Depends, FastAPI
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..backups import BackupService            # your logic module

def register(app: FastAPI, gw: Gateway) -> None:
    svc = BackupService(gw)                     # build once, close over it

    @app.get("/v1/backups/status", tags=["backups"], responses=error_responses(401))
    def status(_: Principal = Depends(gw.principal)):
        return svc.status()
```

Then in `app.py`: `from .routers import backups as backups_routes` and `backups_routes.register,` in `ROUTERS`.

What `gw` (`context.Gateway`) gives you: `settings`, `clock` (use it, never `datetime.now()`, so tests control time), `tokens`, `registry` (nodes), `bus` (NATS), `audit`, `events`, `catalog`, `repo` (the action ledger), `db` (shared database), `executor`, `actions` (request/approve/deny), `skip_scan`, `principal` (the bearer-token dependency: 401 and rate-limited `auth.rejected` audit), `on_startup`, `on_shutdown`. `app.state.gateway` exposes it to tests.

Rules:
- Every route except `/healthz` depends on `gw.principal`. Role checks go through `actions` or your own module, never by reading the token yourself.
- Paths go under `/v1/`. A new top-level path must be added to `API_EXACT` in `routers/static.py`, or the dashboard's SPA fallback answers it.
- Errors use `ApiError(status, code, message)` and `error_responses(...)` so `/openapi.json` stays truthful.
- Another feature's internals are off limits; ask its owner for a function on its module.

## 3. Database: tables, repository, upgrade steps (`store.py`)

```python
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .ledger import Base
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("backups")                      # version 1 = the shape below

class BackupRunRow(Base):
    __tablename__ = "backups_runs"                     # always <feature>_<thing>
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class BackupRepository(SqlRepository):
    def add(self, run_id, now):
        with self.db.session.begin() as s:             # one transaction
            s.add(BackupRunRow(id=run_id, state="running", started_at=now))
```

Build it in your router with `BackupRepository(gw.db)`. It shares the ledger's engine, so it runs on SQLite (dev) and PostgreSQL (BD-04) alike.

**Changing a table that has shipped** (a release or `main` has it): change the model **and** add the step that brings an existing database there:

```python
@SCHEMA.step(2, "add backups_runs.bytes")
def _v2(conn):
    conn.execute(text("ALTER TABLE backups_runs ADD COLUMN bytes BIGINT"))
```

How it runs (`store.migrate`, at every gateway start):
1. `create_all`: tables that do not exist yet are created at their current shape.
2. Per feature, from the `schema_versions` table: a feature seen for the first time is stamped at its head version (its tables were just created at that shape; no steps run). A known feature runs each pending step in order; a step and its version bump commit in one transaction, so a failed step leaves the old version and the gateway refuses to start until it is fixed.
3. A database newer than the code (a downgrade) refuses to start: restore the pre-upgrade backup instead.

Why not Alembic (MIT, licence-compatible): it keeps one global revision chain, so five streams that each add "the next revision" collide on every merge. Per-feature chains never collide and add no dependency. This replaces the "one migration file per epic, numbered when merged" rule for `ledger.py` in WORKSTREAMS §4.

Rules:
- Write steps in SQL both SQLite and PostgreSQL accept (`ADD COLUMN`, `CREATE INDEX`). SQLite cannot drop or retype a column in older versions: add a new column and stop reading the old one.
- A step touches only its own feature's tables. The existing `actions`, `app_states` and `agent_tokens` tables are feature `core`.
- Upserts: `self.db.insert()(Row).values(...).on_conflict_do_...(...).returning(Row.id)` and read the outcome from `RETURNING`. Under psycopg 3, `rowcount` for `INSERT ... ON CONFLICT` is -1.
- Tests run on both databases: `make -C core test` (SQLite) and with `ONEMIND_TEST_DB_URL=postgresql://...`. The `settings` fixture drops every `Base` table before each test, yours included.

## 4. Settings: `@config_section` (`sections.py`)

```python
@config_section("backups")
@dataclass(frozen=True)
class BackupSettings:
    enabled: bool = False                 # ONEMIND_BACKUPS_ENABLED=1
    repo_url: str | None = None           # ONEMIND_BACKUPS_REPO_URL
    keep_daily: int = 7                   # ONEMIND_BACKUPS_KEEP_DAILY
    targets: tuple[str, ...] = ()         # ONEMIND_BACKUPS_TARGETS=usb,s3

    def validate(self) -> None:           # optional: raise ValueError to refuse startup
        if self.keep_daily < 1:
            raise ValueError("ONEMIND_BACKUPS_KEEP_DAILY must be at least 1")
```

Read it with `gw.settings.section(BackupSettings)`. `Settings.from_env` parses every registered section at startup, so a bad value stops the gateway with a clear message instead of failing later. Types: `str`, `int`, `float`, `bool` (`1/true/yes/on`, `0/false/no/off`), `Path`, `tuple[str, ...]` and `X | None` (empty = `None`); a field without a default is required. For anything else define `from_env(cls, env)` on the class. Tests that build `Settings(...)` directly get the section's defaults; pass `replace(settings, sections={"backups": BackupSettings(...)})` to override. Secrets never go in environment defaults or in Git: take a file path (`..._FILE`) and read the file.

## 5. Events: `publish_event` (`events.py`)

```python
gw.events.publish_event(
    "backup", "run.failed", {"run_id": run_id, "target": "usb"},
    severity="error", resource={"kind": "backup_target", "id": "usb"},
    dedupe_key="backup:usb:failing", principal=p.as_dict() if p else None,
)
```

One call, in this order:
1. **Audit:** appends `backup.run.failed` to the hash-chained audit log (data: `event_id`, `severity`, `payload`, plus `resource` and `dedupe_key` when set). The audit line is also published on `onemind.audit`, as every audit line is.
2. **NATS:** publishes the `onemind.event.v1` envelope of the contract §12.3 draft on `onemind.event.backup.run.failed` (best effort; NATS down never fails the caller, the audit line is the record of truth).
3. **In-process subscribers** whose pattern matches: `gw.events.subscribe("backup.>", handler)`. `*` matches one token, a final `>` one or more. Handlers run in the publisher's thread: keep them quick and queue slow work (a push, an email). A handler that raises is logged and skipped.

Domain and name are lower-case tokens (`[a-z][a-z0-9_]*`, name up to four dotted parts). The payload is JSON, at most 16 KiB, and carries ids and small facts only, never secrets or file contents. Notifications (CORE-NOTIFY-1) and monitoring subscribe here or to `onemind.event.>` on NATS; the event type names come from the catalogue in `docs/architecture/NOTIFICATIONS.md` §3. Until contract PR C12-A settles it, `instance_id` is the hub node id.

## 6. `onemind` commands: `cmd/onemind/cli/<group>.go`

```go
// SPDX-License-Identifier: Apache-2.0
package cli

func backupCommands(a *App) []*cobra.Command {
	backup := &cobra.Command{Use: "backup", Short: "Snapshots of app data"}
	backup.AddCommand(&cobra.Command{
		Use: "now", Short: "Take a snapshot now", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client() // the Go SDK client for the selected box (context, --hub, token)
			if err != nil {
				return err
			}
			...
		},
	})
	return []*cobra.Command{backup}
}
```

Add `backupCommands,` to `groups` in `cli/root.go`; its order is the help order. The CLI is built with cobra (F-8, DEV-CLI-1) on the Go SDK (`sdk/go`): global flags (`--context`, `--hub`, `--json`, `--timeout`, ...) are on `a.G`, `a.client()` resolves the box, `printJSON`/`table`/`kv` print (gateway strings pass through `sanitize`), and a command returns an error whose exit code comes from `cli/exit.go` (the CLI.md §4.2 table; `exitWith(code, name, msg)` for an explicit one). Unknown input prints the usage and exits 2. `cmd/onemind/main.go` only calls `cli.Run`.

## 7. `onemindd`: subcommands and optional services

- **Separate mode, own process** (needs different privileges or its own systemd unit, like `onemindd update`): add `"backup": runBackup,` to `subcommands` in `cmd/onemindd/registry.go`.
- **Service inside the agent** (runs next to the heartbeat): export from `internal/<feature>`:

```go
func Service() service.Service {
	return service.Service{
		Name:    "leaf",
		Enabled: func() bool { return os.Getenv("ONEMIND_LEAF_URL") != "" },
		Run:     func(ctx context.Context, log *slog.Logger) error { /* block until ctx.Done() */ },
	}
}
```

and add `leaf.Service(),` to `optionalServices`. `internal/service` runs each enabled service in its own goroutine with the agent's context (cancelled on SIGINT/SIGTERM or when the agent stops). A service that returns an error or panics is logged and stays stopped, and the heartbeat keeps running. The agent waits for every service before exiting.

## 8. Checklist for a feature PR

- [ ] One new router line in `app.py` (and one `groups`/`registry.go` line if it has a CLI or daemon part); no other hotspot lines.
- [ ] Tables named `<feature>_*`, a `FeatureSchema`, and a step for every change to a shipped table.
- [ ] Settings via `@config_section`; no secrets in env defaults.
- [ ] Facts worth telling someone go through `publish_event`; no direct NATS publishes under `onemind.>` from feature code.
- [ ] Tests: `make -C core test`, the same with `ONEMIND_TEST_DB_URL` (PostgreSQL), `go test -race ./...`; SPDX headers on new files.
- [ ] `docs/leap/STATUS.md` row and a CHANGELOG entry.
