<!-- SPDX-License-Identifier: Apache-2.0 -->
# Slop audit: code

**Date:** 2026-11-12 · **Audited:** `main` at `1c278f5` (after #39) · **Lens:** code slop: fake or placeholder code presented as working, canned data outside tests or demo mode, modules nobody calls, duplicated logic, TODOs left in shipped code, swallowed errors, tests that prove nothing or only test mocks, fixed sleeps in tests, commented-out code, and names that differ between components. Other lenses (docs, security, UX) are separate audits.
**Serves:** the founder's "take testing to the next level" and "no slop" asks; every fix below maps to an epic in [BACKLOG.md](../leap/BACKLOG.md) or a gate in [WORKSTREAMS.md](../leap/WORKSTREAMS.md) §5.

> **Explain it like I am the founder**
> Most of the code is careful. Its tests pass, mocks are labelled, and gateway errors are handled. The main problem is **wiring**. About 6,900 lines of finished-looking code (the backup agent, disk tools, mesh and NATS-leaf clients, the gateway's app proxy and box CA) are merged but **no program ever calls them**. Their tests pass, so they look done. Two comments even say they are registered when they are not.
> Second, **some checks check a stand-in**. The OS rollback gate asks a tiny fake service "is the OneMind API up?" when the real agent could answer. The CI contract check also turns a missing feature into "skipped" instead of "failed". And the phone app's 37 tests never run in CI.
> Third, **one rule is written five times** (when an app may be installed), and the copies already disagree.
> Each finding below names the file and line, how to see the problem, and the fix.

## How this was checked

Everything here was re-run on the audited commit. Nothing was installed on the host; Node and Python dependencies went into the project folders (`npm ci`, `uv sync`).

| Check | Result |
|---|---|
| `go vet ./...` | clean |
| `go test -count=1 ./...` | 12 packages ok |
| `make -C core test` equivalent (`uv run pytest -q -rs`) | 304 passed, 2 skipped (no `ONEMIND_TEST_NATS_URL`) |
| `mobile`: `npm ci && npm test -- --ci` | 37 passed, **local only** (see CS-06) |
| `python3 -I scripts/app-taxonomy.py --check` | exit 0 (in sync today; not in CI, see CS-06) |
| Built `onemind` and `onemindd` from `cmd/` and ran the commands the code documents | see CS-02, CS-03 |
| Production importers of each `core/onemind_core/*.py` module, and of each `internal/*` package from `cmd/` | see CS-01 to CS-04 |
| Greps: `TODO/FIXME/XXX/HACK`, commented-out code, `except …: pass`, `_ =` on errors, `time.Sleep`/`sleep` in tests, test cases with no assertion | see "Checked and clean" |

## Findings, most severe first

| Id | Sev | Kind | One line | Resolution (2026-11-12, re-verified on main) |
|---|---|---|---|---|
| [CS-01](#cs-01) | high | unwired module | `internal/backup` (2,781 lines) is never started by `onemindd` or exposed by `onemind` | fixed (638b753): `backup.Service()` runs the loop and mounts `/api/v1/backup/`; `cmd/wiring_test.go` guards new packages. Deferred: heartbeat field, updater call and the `os/` restic pin (README steps 2 to 8; the `os/` part is deferred to B2) |
| [CS-02](#cs-02) | high | unwired module | `onemind storage` and `onemind mesh status` are unreachable; the comments say otherwise | fixed (638b753): `storage` and `mesh` are groups in `cmd/onemind/cli/`; `jsonout.go` deleted |
| [CS-05](#cs-05) | high | placeholder presented as working | Health gate G6 checks a `socat` stand-in, not the agent, though `onemindd /healthz` already serves `boot_id` | deferred to B2 (`os/gate` belongs to the image line, `feat/image-line`); still valid on main (`onemind-k3s-check` greps the socat stand-in) |
| [CS-06](#cs-06) | high | tests never run | No CI workflow runs `mobile/` (37 tests, typecheck, lint) or the taxonomy `--check` | already fixed on main for `mobile/` (`.github/workflows/ci-mobile.yml`); taxonomy `--check` added to `ci.yml` (103e48e) |
| [CS-03](#cs-03) | medium | unwired module, swallowed input | `onemindd mesh …` is not dispatched, and `onemindd` silently ignores unknown arguments and starts the agent | fixed (638b753): `onemindd mesh` dispatched; stray arguments exit 2. Still deferred: `leaf.Supervisor.Run` and `mesh.Reporter` have no caller (CORE-NET-12) |
| [CS-04](#cs-04) | medium | unwired module | Gateway `ca.py`, `mesh.py`, `proxy.py` (1,308 lines) have no production importer | partly fixed (103e48e): docstrings say "not mounted yet" and `core/tests/test_wiring.py` fails on new orphan modules. Mounting stays deferred (CORE-NET-8) |
| [CS-07](#cs-07) | medium | check that cannot fail | CI's `verify.sh` turns a missing `/mcp` or §11.4 catalog fields into SKIP | fixed (103e48e): the two skips are now failures; `--strict` not needed |
| [CS-08](#cs-08) | medium | stub presented as working | The `noop` executor marks apps `installed`; no client can tell nothing ran | deferred: needs an additive `/v1/instance` field, regenerated OpenAPI and SDKs, and a dashboard/mobile badge (dashboard is Agent A's `feat/dashboard-v2`) |
| [CS-09](#cs-09) | medium | inconsistent logic | The gateway ignores `metadata.tier: blocked`; `ui/` claims to mirror the gateway and blocks it | fixed (103e48e) in the gateway and the site copy; the dashboard and mobile copies are deferred with CS-10 |
| [CS-10](#cs-10) | medium | duplicated logic | The §10.3 install rule exists in 5 copies; the site's copy accepts unreadable and future scan dates | partly fixed (103e48e): the site copy now refuses unreadable, future and blocked records. Shared module and golden vectors deferred (they touch `dashboard/` and `mobile/`) |
| [CS-11](#cs-11) | medium | tests test the mock | Dashboard `MockApi` returns `requested_by.role`, which the gateway never sends; every UI test runs on the mock | deferred: `dashboard/` is Agent A's area (`feat/dashboard-v2`); the replay-test idea stands |
| [CS-15](#cs-15) | medium | swallowed error | Async `POST /api/v1/backup/run` with an unknown target returns 202, then the run disappears | fixed (638b753): unknown target is a 400 before the 202 (test added). `runLocked` still records no failed run for other early returns (low) |
| [CS-12](#cs-12) | low | naming | Gateway and clients say `decided_by`; contract §12 settled `approved_by`; the audit already uses `approved_by` | deferred: additive `approved_by` changes `/openapi.json` and all generated SDKs and three clients; see D3 |
| [CS-13](#cs-13) | low | naming | 20 CLI hints in `ui/src/settings` name verbs that are not in the CLI tree | deferred: 20 hints in `ui/` need CLI.md verb decisions first |
| [CS-14](#cs-14) | low | swallowed error | `app-gate` ignores SBOM generation failures | fixed (103e48e): `app-gate` fails the vulnerabilities check when the SBOM is not written |
| [CS-16](#cs-16) | low | swallowed error | Directory restore drops the rollback-rename error and does not say where the original went | fixed (638b753): the error names where the original is kept. The read-only-parent test is deferred |
| [CS-17](#cs-17) | low | fixed sleep in tests | Leaf and agent tests prove "nothing happened" by sleeping a fixed time | deferred (low): needs a capturing logger on the test hub and a connect-attempt counter |
| [CS-18](#cs-18) | low | dead config | pytest marker `postgres` is unused and names an env var nothing reads | fixed (103e48e): marker now names `ONEMIND_TEST_DB_URL` (still unused by tests; deleting it is a follow-up) |

The table is grouped by severity; ids follow discovery order.

---

### CS-01
**`internal/backup` is merged but nothing runs it.** · high · CORE-BACKUP-2, BACKUPS

- **Where:** `cmd/onemindd/registry.go:15` (`optionalServices = []service.Service{}`); `cmd/onemind/cli/root.go:32-36` (groups: `node`, `update`, `version` only). `internal/backup` exports no `Service()`, and nothing outside its own tests imports it (`grep -rn 'internal/backup"' cmd internal` finds nothing).
- **Evidence:** `internal/backup/README.md:53-61` lists the eight wiring steps "still needed". The OS updater still takes its own restic snapshot (`internal/update/engine.go:213-248`), not the agent's `pre-update` run. Built `onemind`: `onemind backup now` prints the usage text and exits 2.
- **Why it matters:** 2,781 production lines and about 1,600 test lines (agent, retention ladder, Rewind, verify-restore, local API) are green in CI but never ship. The tests prove only the library, not the product.
- **Fix:** add `func Service() service.Service` in `internal/backup` (enabled when `ONEMIND_BACKUP_CONF` exists; runs `Loop`). Let `agent.Config` take extra handlers, so `a.Handler(ctx)` mounts under `/api/v1/backup/` on the `:7480` mux. Then add one line, `backup.Service(),`, to `optionalServices`. To stop the next unwired module, add `cmd/onemindd/wiring_test.go`. It runs `go list -deps ./cmd/...` and fails when an `internal/*` package is not a dependency of a binary, unless the package is in an allowlist that names the epic wiring it (here CORE-BACKUP-2).

### CS-02
**`onemind storage` and `onemind mesh status` cannot be run.** · high · UMB-STOR-3, CORE-NET-P1

- **Where:** `cmd/onemind/storage.go:38` (`storageCmd`), `cmd/onemind/mesh.go:27` (`meshCmd`). Their only callers are `storage_test.go:40,67` and `mesh_test.go:39,48,58`. They are missing from `groups` in `cmd/onemind/cli/root.go:32-36`.
- **False claims in code:** `cmd/onemind/mesh.go:24` says "Registered in main.go with one line (§18)". `internal/storage/README.md:68-84` tells the CLI owner to add a `case` to "the `switch` in `run`" and append to `const usage` in `main.go`; neither has existed since #38 (`main.go` now only calls `cli.Run`).
- **Duplication kept alive for them:** `cmd/onemind/jsonout.go:9-23` re-declares `printJSON` and `dash` from `cmd/onemind/cli/helpers.go` only to serve these two files. `internal/mesh/cli.go:163` has a third `dash`.
- **Evidence:** a built `onemind storage disks` or `onemind mesh status` prints the usage text, exit 2.
- **Fix:** move both into `cmd/onemind/cli/storage.go` and `cli/mesh.go` as `storageCommands()` and `meshCommands()` (PLUMBING.md §6). Add two lines to `groups`, delete `jsonout.go`, rewrite the README "Wiring" section to the `groups` line, and move the tests to `cli/`. The wiring test from CS-01 covers these too.

### CS-03
**`onemindd mesh …` is documented but not dispatched, and `onemindd` swallows unknown arguments.** · medium · CORE-NET-12

- **Where:** `internal/mesh/cli.go:25-29` says "`cmd/onemindd/main.go` dispatches to it with one line". `subcommands` in `cmd/onemindd/registry.go:9-11` has only `update`. `cmd/onemindd/main.go:111-116` calls `flag.Parse()` and never checks `flag.NArg()`.
- **Evidence:** `onemindd mesh status -listen 127.0.0.1:0` does not fail. Flag parsing stops at `mesh`, so `-listen` is ignored and the full agent starts: `local API listening addr=[::]:7480`. A node following NETWORKING.md's `onemindd mesh enroll --bundle F` gets a second heartbeat agent (or an "address in use" exit) instead of an enrolment.
- **Also unwired:** `leaf.Supervisor.Run` (`internal/leaf/supervise.go:148`) and `mesh.Reporter` (`internal/mesh/enroll.go:168`) have no caller outside tests.
- **Fix:** add `"mesh": func(a []string) int { return mesh.RunCLI(a, os.Stdout, os.Stderr) },` to `subcommands`. After `flag.Parse()`: `if flag.NArg() > 0 { fmt.Fprintf(os.Stderr, "onemindd: unknown command %q\n", flag.Arg(0)); os.Exit(2) }`. Add a `main_test.go` case for both. Register `leaf` as a `service.Service` when CORE-NET-12 lands.

### CS-04
**The gateway's app proxy, box CA and Headscale client are not mounted.** · medium · CORE-NET-8, CORE-NET-12, H-05, H-29

- **Where:** `core/onemind_core/ca.py` (262 lines), `mesh.py` (526), `proxy.py` (520) have zero importers in `core/onemind_core/**` (only `core/tests/test_{ca,mesh,proxy}.py`). `ROUTERS` in `core/onemind_core/app.py:44-51` has no entry, and `create_app` adds no middleware.
- **Presented as working:** `proxy.py:4` and `proxy.py:366` call it "an ASGI middleware". `proxy.py:30` refers to `/v1/auth/forward`, which no router serves.
- **Mitigation already in place:** `docs/architecture/NETWORKING.md:560` labels these "not registered yet". The design doc is honest; the module docstrings are not.
- **Fix:** in CORE-NET-8, register `routers/mesh.py` and `app.add_middleware(AppProxy…)` with one line each. Until then, change both docstrings to "not mounted yet (CORE-NET-8)". Add a core test that fails when a module under `onemind_core/` has no production importer and is not on a named allowlist (the Python twin of the CS-01 test).

### CS-05
**The OS health gate's API check (G6) checks a stand-in.** · high · PLAN-E1, CORE-UPDATE-3, OS image stream

- **Where:** `os/gate/onemind-local-api.service:10-11`. `ExecStartPre` writes `ok boot_id=<this boot>` to `/run/onemind-api/health`, and `socat` replays it through `os/gate/onemind-local-api-respond:3-5`. G6 in `os/gate/onemind-k3s-check:54-55` greps that reply for `boot_id`. The image enables the stand-in, not `onemindd` (`os/rootfs/Containerfile:60-69`).
- **Why it matters:** G6 passes whenever `socat` can start, so a release that breaks the real agent is kept, not rolled back. The real check already exists: `onemindd`'s `GET /healthz` returns `{"ok":true,"boot_id":…}` (`internal/agent/agent.go:143-149`), merged in #7.
- **Fix:** ship the static `onemindd` (`make -C cmd/onemindd build`) and `deploy/systemd/onemindd.service` in the rootfs. Point G6 at `http://127.0.0.1:7480/healthz` and compare the JSON `boot_id`. Delete `onemind-local-api.service` and `-respond`. Add a QEMU battery case where `onemindd` cannot start, and expect the gate to roll back (`test/qemu/CRITERIA.md`).

### CS-06
**The phone app's tests never run in CI.** · high · PA-MOBILE, MOBILE

- **Where:** `grep -l mobile .github/workflows/*.yml` returns nothing. `mobile/` has 5 Jest suites (37 tests), a TypeScript project and lint config. The CHANGELOG entry for #21 says "37 tests pass", but that was a one-time local run.
- **Same pattern:** `docs/design/TAXONOMY.md:333` says `scripts/app-taxonomy.py --check` is "suitable for CI", and no workflow runs it.
- **Evidence:** on this commit, `npm ci && npm test -- --ci` in `mobile/` gives 37/37. It is green today only by luck: nothing guards the next change.
- **Fix:** add `.github/workflows/ci-mobile.yml` (paths `mobile/**`; `npm ci`, `npm run lint`, `npx tsc --noEmit`, `npm test -- --ci`), with actions pinned by the SHAs in `os/versions.lock.yaml` like `ci-dashboard.yml`. Add `python3 -I scripts/app-taxonomy.py --check` as a step in `ci.yml`.

### CS-07
**CI's contract check hides wave-2 regressions as SKIP.** · medium · W2-DEPLOY, W2-GW

- **Where:** `.github/workflows/ci-deploy.yml:41` runs `verify.sh` without `--strict`. `deploy/verify/verify.sh:193` turns missing `links/tier/scan` catalog fields into `skip "… (wave-2 gateway)"`, and `:279` turns a 404/405 on `POST /mcp` into a skip. Wave 2 is merged (#24).
- **Why it matters:** a PR that deletes the MCP router or the §11.4 fields keeps `ci-deploy` green.
- **Fix:** make those two branches `fail`. Keep SKIP only where compose cannot provide the feature (`:169`, the hub has no `onemindd`). Then pass `--strict` in CI.

### CS-08
**The `noop` executor reports apps as installed.** · medium · DEV-API, DASHBOARD (principle P2 "honest about state")

- **Where:** `ONEMIND_EXECUTOR` defaults to `noop` (`core/onemind_core/config.py:109`), and the compose dev hub sets it (`deploy/compose/compose.yaml:54`). On a successful dispatch, `core/onemind_core/actions.py:341` sets the app state to `installed` whatever the executor. `/v1/apps` then returns `installed: true`, and the dashboard shows the Installed badge (`dashboard/src/pages/Market.tsx:58`) and lists the app on Home (`Home.tsx:80`).
- **Why it matters:** nothing was applied. The only trace is `result.message = "noop executor: … nothing changed"` inside the action. `/v1/instance` (`core/onemind_core/routers/instance.py:24-26`) does not say which executor runs, so no client can label it.
- **Fix:** add `"executor": "noop"|"kubernetes"` to `/v1/instance` (an additive optional field, §12.2), and show a "Dry run: nothing is installed" badge in `dashboard/src/components/Layout.tsx` and on the mobile Home. Better still, record app state `simulated` under `noop`, so `installed` always means applied.

### CS-09
**The gateway does not refuse `tier: blocked`; `ui/` says it mirrors the gateway and does.** · medium · CORE-SANDBOX, W2-PIPE

- **Where:** `scan_problem` (`core/onemind_core/scan.py:69-81`) and the approve path (`core/onemind_core/actions.py:235`) check only the scan record and never `AppEntry.tier`. `ui/src/lib/trust.ts:2-3` says "The gateway is the authority; the UI mirrors its rule", then blocks `tier === 'blocked'` (`:22`). The shipped dashboard (`dashboard/src/lib/scan.ts:22`) and mobile (`mobile/src/lib/scan.ts:24`) do not check the tier at all.
- **Failure scenario:** contract §9.4 says a malware hit means "`blocked`, and a human looks", and `app-gate --tier write` never lifts a human `blocked` (`sdk/tools/app-gate:417-425`). If a reviewer sets `metadata.tier: blocked` while `scan.json` still says `pass`, the gateway approves the install. Today every blocked app also has a failing scan (5 of 9 in `apps/`), so nothing is exposed yet.
- **Fix:** in `ActionService._precondition`, refuse `app.install` when `entry.tier == "blocked"` with `409 stale_precondition` (reason `blocked`). Add the check to the dashboard and mobile copies (or to the shared module from CS-10), plus a core test.

### CS-10
**The install rule is written five times, and the copies have drifted.** · medium · SDK-4, WEBSITE

- **Copies:** `core/onemind_core/scan.py:69` (the authority); `dashboard/src/lib/scan.ts:22`; `mobile/src/lib/scan.ts:24`; `ui/src/lib/trust.ts:21`; `site/src/lib/apps.ts:138`.
- **Drift:** in the site's copy, `daysSince` (`site/src/lib/apps.ts:80-82`) is `NaN` for an unreadable `scanned_at` and negative for a future one. Neither is `> 7`, so `installable()` returns "Passing scan within the last 7 days". The gateway ignores an unreadable record (`scan.py:63`) and refuses a date more than 5 minutes ahead (`scan.py:76`). The tier check differs too (CS-09).
- **Copy-paste with nothing enforcing it:** `mobile/src/api/{types,fixtures,mock}.ts` and `mobile/src/lib/{time,scan}.ts` are copies of the dashboard files headed "Keep the two in sync" (`mobile/src/api/types.ts:2-3`). They already differ (CS-11).
- **Fix:** keep one TypeScript module for the rule and the contract types (`ui/src/lib/trust.ts` exported from `@onemind/ui`, or `sdk/ts` when SDK-4 starts), consumed by the dashboard, mobile and the site. Add golden vectors in `sdk/testdata/install-rule.json` (inputs: scan, tier, now; expected: allowed or reason), run by core pytest and by each TypeScript suite, so any copy that drifts fails.

### CS-11
**The dashboard's mock returns a field the gateway never sends, and every UI test runs on the mock.** · medium · DASHBOARD, SDK-4

- **Where:** the gateway stores `requested_by = {"id", "kind"}` (`core/onemind_core/actions.py:169`; contract example `sdk/contracts/poc-v0.md:294`). The dashboard types it as a full `Principal` with `role` (`dashboard/src/api/types.ts:148`), and `MockApi` stores the whole principal (`dashboard/src/api/mock.ts:81`). `Approvals.tsx:43` renders "(role)" only when `role` exists, which happens only in demo mode.
- **Tests on the mock:** every flow in `dashboard/src/ui.test.tsx` runs against `MockApi` (`dashboard/src/test/helpers.tsx:15`), so the drift cannot show. Mobile already corrected its copy (`PrincipalRef`, `mobile/src/api/types.ts:137-146`).
- **Fix:** have `MockApi` store `{id, kind}` and type the field as `PrincipalRef`. Add a replay test: a core pytest writes real responses (`/v1/instance`, `/v1/nodes`, `/v1/apps`, an action through each state) from `TestClient` into `sdk/testdata/responses/*.json`. The dashboard and mobile tests load those files and render them, so the mock and the gateway are compared every run.

### CS-12
**One fact, two names: `decided_by` and `approved_by`.** · low · contract §12 (C12-A)

- **Where:** the action JSON says `decided_by` (`core/onemind_core/ledger.py:65,81`), as do both clients' types. The audit record for the same decision says `approved_by` (`core/onemind_core/actions.py:246`). Contract §12's naming table settles `approved_by` (`sdk/contracts/poc-v0.md:652`).
- **Fix:** add `approved_by` to `Action.to_json` now, mark `decided_by` deprecated in the OpenAPI description, and switch the clients. Remove `decided_by` at API v1.

### CS-13
**20 CLI hints in the settings screens name commands that do not exist in the CLI spec.** · low · CLI, PA-UI

- **Where:** `ui/src/settings/SectionsCare.tsx:48,69,75,165,207,248,250,266,299,326,413`; `SectionsSystem.tsx:69,88,99,299,312`; `SectionsAccess.tsx:46,196,205,262`. Examples, with the spec's verb in brackets (`docs/leap/dev/CLI.md` §3): `onemind backups verify|now|destinations add` (`backup verify|now`), `onemind os update --in-window`, `onemind os rollback` (`update apply`), `onemind automations list` (`auto list`), `onemind nodes add --role`, `onemind join <code>`, `onemind nodes remove` (`fabric qr|join|remove`). Also `people invite`, `diagnostics bundle`, `apps outdated|update`, `auth passkey add` and `notify routes add`, which appear nowhere in the tree. Contract §12 fixes "CLI verbs: CLI.md §3 tree".
- **Fix:** keep the hints in one map (`ui/src/lib/cli.ts`). Add a vitest that parses the §3 tree in `CLI.md` and fails on any verb not in it. Verbs that are wanted but missing (`people`, `diagnostics`) go into CLI.md first.

### CS-14
**`app-gate` ignores SBOM generation failures.** · low · W2-PIPE

- **Where:** `sdk/tools/app-gate:146-151` runs `trivy … --format cyclonedx` and discards the return code (`common.run` uses `check=False`, `sdk/tools/applib/common.py:68-69`). The upload step uses `if-no-files-found: ignore` (`.github/workflows/ci-apps.yml:145`). Contract §9.4 check 4 (`sdk/contracts/poc-v0.md:167`) says the scan produces an SBOM.
- **Fix:** on a non-zero exit, call `self.check("vulnerabilities").fail(f"SBOM for {ref} ({arch}) not written: …")`. Record each SBOM path in the report.

### CS-15
**An async backup run with an unknown target is accepted, then lost.** · medium (live once CS-01 is wired) · CORE-BACKUP-2

- **Where:** `internal/backup/api.go:60-64` acquires the lock, answers `202 {"run_id", "state": "running"}`, and runs `_, _ = a.runLocked(base, rr)` in a goroutine. `runLocked` returns `no target %q` (`internal/backup/agent.go:158-160`) before it writes any run record, so the returned `run_id` never shows up in `/api/v1/backup/status`, and the error goes nowhere. No test covers an unknown `target_id`.
- **Fix:** in the handler, check `a.target(req.TargetID)` before the 202 and answer `400 {"error":"bad_request","detail":"unknown target"}`. Also make `runLocked` record a failed `Run` for any early return, and add the test.

### CS-16
**A failed directory restore can leave the original under another name without saying so.** · low · UMB-FILES-7

- **Where:** `internal/backup/rewind.go:305-309`. If `os.Rename(tmp, dest)` fails, the rollback `_ = os.Rename(old, dest)` drops its own error. If that also fails, the person's data stays at `<dest>.onemind-old-<time>`, and the returned error names neither.
- **Fix:** `if rerr := os.Rename(old, dest); rerr != nil { return fmt.Errorf("%w; the original is kept at %s (moving it back failed: %v)", err, old, rerr) }`, plus a test with a read-only parent.

### CS-17
**Tests prove "nothing happened" by sleeping a fixed time.** · low · CORE-NET-4, node agent

- **Where:** `internal/leaf/leaf_test.go:317` sleeps 1.5 s, then asserts the leaf is down and the hub has 0 leaf nodes. `internal/agent/agent_test.go:121` sleeps 300 ms, then asserts 0 heartbeats were sent.
- **Why it matters:** on a slow runner the leaf may not have tried to connect yet, so the test passes without proving the hub refused it. A fixed sleep costs time and still proves nothing.
- **Fix:** give the hub a capturing logger (`hub.srv.SetLoggerV2(...)`) and wait, with a deadline, for its leafnode authorization or TLS rejection line. Then assert `NumLeafNodes() == 0`. For the agent, wait until its NATS connect attempt has failed at least once (expose a counter next to `Sent()`) before asserting.

### CS-18
**A pytest marker that nothing uses, naming an env var that nothing reads.** · low · test hygiene

- **Where:** `core/pyproject.toml:48` declares marker `postgres` ("needs … `ONEMIND_TEST_PG_URL`"). No test uses `@pytest.mark.postgres`. The suite reads `ONEMIND_TEST_DB_URL` (`core/tests/conftest.py:101`; `core/Makefile:32`; `.github/workflows/ci-core.yml:36`).
- **Fix:** delete the marker, or rename it to `ONEMIND_TEST_DB_URL` and put it on the PostgreSQL-only tests, so `-m "not postgres"` means something.

## Checked and clean

- No `TODO`, `FIXME`, `XXX` or `HACK` in shipped code (`core`, `cmd`, `internal`, `sdk/tools`, `os`, `deploy`, `dashboard`, `mobile`, `ui`, `site`). No commented-out code blocks.
- Demo data is gated and labelled. In the dashboard it needs `VITE_MOCK=1` and shows a "Demo data" badge (`dashboard/src/components/Layout.tsx:47`). In mobile it needs `mode: 'mock'` and shows "demo (made-up data)".
- Gateway executor failures become `failed` or `outcome_unknown`, never silent (`core/onemind_core/actions.py:251-267`). `ONEMIND_EXECUTOR` is validated at startup.
- Error codes match contract §3 across the gateway, `dashboard/src/api/client.ts` and mobile. `ONEMIND_*` variable names match across Go, Python and `deploy/`. Node-id rules are identical in `internal/heartbeat` and `core/onemind_core/nodes.py`.
- Python test waits are bounded polls, not fixed sleeps. The only test cases with no visible assertion assert inside helpers (`request_install`).
- The security pipeline's publish switch is gated on keys, root, a repository variable and the dry-run flag (`security-nightly.yml:145-158`). The Mosquitto `blocked` tier is the deliberate "licence not confirmed by GitHub or the matrix" rule (`sdk/tools/applib/licence.py:148-150`).
- The site's CLI reference (`site/src/content/docs/docs/reference/cli.md`) matches the built binary.

## Seen, but outside this lens

- `CHANGELOG.md` has no entries for the merged PRs #24 to #39. Its "Unreleased" table still lists merged branches as unmerged.
- `docs/leap/STATUS.md` still shows W2-GW, W2-PIPE, W2-DEPLOY, CORE-NET-P1, CORE-BACKUP-2 and UMB-STOR-3 as `in-progress` with no PR, although their code is on `main`. The docs audit should fix both files.
