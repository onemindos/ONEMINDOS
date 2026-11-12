<!-- SPDX-License-Identifier: Apache-2.0 -->
# Slop audit, pass 2: code

**Date:** 2026-11-12 · **Audited:** `origin/main` at `ad81f84` (after #61, #73, #74) · **Item:** Wave G #4 (`QUALITY-SLOP-2` in [STATUS.md](../leap/STATUS.md)) · **Pass 1:** [slop-audit-code.md](slop-audit-code.md) (found at `1c278f5`, fixed in #67)
**Lens:** dead or unwired modules, duplicated logic, swallowed errors, checks that skip instead of fail, TODOs without an owner. Docs and drift are in [slop-audit-2-docs.md](slop-audit-2-docs.md) and [slop-audit-2-drift.md](slop-audit-2-drift.md).

> **Explain it like I am the founder**
> Pass 1's big problems are gone: the backup agent, `onemind storage` and `onemind mesh` are now wired, and two new guard tests (`cmd/wiring_test.go`, `core/tests/test_wiring.py`) fail when a new package or module has no caller. What is left is smaller and one level down: a few **functions** that are finished but never called, **errors thrown away** inside the backup agent (one can make a failed backup job re-run every tick), **end-to-end checks that skip forever** because they wait for routes that will never exist under that name, and **one unit test that needs the internet**. There are no `TODO`/`FIXME` markers left in shipped code at all (so none without an owner).

## How this was checked

| Check | Result on `ad81f84` |
|---|---|
| `go vet ./...` | clean |
| `go test -count=1 ./...` | 14 packages ok |
| `cd core && uv run pytest -q -rs` | **544 passed, 6 skipped, 1 failed** (CS2-05; the failure is environmental: no DNS in this container) |
| `TODO\|FIXME\|HACK` over `core cmd internal deploy os sdk mobile/src desktop scripts dashboard/src ui/src site/src` | **0 hits** (no TODO without an owner exists) |
| Python definitions with no other use inside `onemind_core/` (script, see CS2-04) | 6 hits, all in the three known unmounted modules |
| `except …: pass/continue` in `core/onemind_core` | 8 sites, all reviewed: each is a parse-or-skip on untrusted input with a safe fallback; none hides a failure of our own state |
| Go `_ = …` on errors in `internal/` and `cmd/` (non-test) | 30 sites, reviewed: 6 matter (CS2-02, CS2-03) |
| Skips: `pytest.skip`, `skipif`, `t.Skip`, `test.skip`, `SKIP` | see CS2-06, CS2-07 |
| `continue-on-error`, `if: false`, `|| true` in `.github/workflows` | none |

## Findings, most severe first

Owner rule: `orchestrator` = file in `dashboard/ ui/ docs/ apps/ site/`; `Hermes` = file in `core/ cmd/ internal/ deploy/ os/ sdk/ mobile/ desktop/` or in an open PR (#55 #56 #57 #47 #66 #72 #75-#78). `tests/` and `.github/` follow the code they test.

| Id | Sev | Owner | Kind | One line |
|---|---|---|---|---|
| [CS2-01](#cs2-01) | medium | Hermes | swallowed error, can loop | A failed state write in the backup scheduler makes a failed job re-run on every tick |
| [CS2-02](#cs2-02) | medium | Hermes | swallowed error | The backup agent ignores failures to record a run, the fence, and source sizes |
| [CS2-03](#cs2-03) | medium | Hermes | check that skips forever | e2e specs wait for routes that never exist under that name (`/v1/backups/status`, `/v1/tls`, `app-proxy`) |
| [CS2-04](#cs2-04) | medium | Hermes | unwired code | Gateway `ca.py`, `mesh.py`, `proxy.py` still unmounted; 6 public names have no caller at all |
| [CS2-05](#cs2-05) | medium | Hermes | test needs the internet | `test_owner_listing_hides_other_peoples_destinations` resolves `ntfy.sh` for real |
| [CS2-06](#cs2-06) | medium | Hermes | unwired symbols | `leaf.Supervisor.Run` and `mesh.Reporter` have no caller; the wiring test cannot see symbols |
| [CS2-07](#cs2-07) | low | Hermes | check that skips | SDK live tests and `kustomize` tests skip silently when a tool is missing |
| [CS2-08](#cs2-08) | low | Hermes | swallowed error | `onemind mcp doctor` and `audit` ignore JSON decode errors and print empty results |
| [CS2-09](#cs2-09) | low | Hermes | check that passes vacuously | `verify.sh` §3 audit-on-NATS check prints SKIP and exits 0 when no lines are seen |
| [CS2-10](#cs2-10) | low | Hermes | duplicated logic | The §10.3 install rule still exists in 5 copies (gateway, `ui`, `dashboard`, `mobile`, `site`) |
| [CS2-11](#cs2-11) | low | orchestrator | stale placeholder | Dashboard `COMING` table marks 4 settings sections "coming" whose routes exist in `/openapi.json` |

### CS2-01
**A failed job is not recorded as done when the state file cannot be written.** · medium · CORE-BACKUP-2
- **Where:** `internal/backup/schedule.go:90` (`_ = a.Store.Update(func(s *State) { s.LastJobs[j] = slots[j] })`), and `:71` (the first-run baseline).
- **Evidence:** the comment on `Tick` (`schedule.go:80-82`) promises "a failed job … is not retried before its next slot, so a broken target cannot turn into a tight loop". That promise depends on the write at `:90`. If the store cannot write (disk full, read-only `/data`), the error is dropped, `LastJobs[j]` stays old, and `dueJobs` returns the same job on the next tick.
- **Why it matters:** a full disk is exactly when backups fail; the agent then retries a restic run every tick instead of backing off.
- **Fix:** log the store error and keep an in-memory `lastJobs` map that wins over the file for the process lifetime. Test with a store whose `Update` always errors and assert `runJob` is called once per slot.

### CS2-02
**Run records, the fence and source sizes are written with the error thrown away.** · medium · CORE-BACKUP-2, CORE-BACKUP-6
- **Where:** `internal/backup/agent.go:164` (the "running" record), `:193` (`FencedBy`), `:222` (`SourceBytes`); `internal/backup/rewind.go:244`.
- **Evidence:** all four are `_ = a.Store.Update(…)`. Pass 1's CS-15 residual ("`runLocked` records no failed run for other early returns") is the same family.
- **Why it matters:** the run list is what a person reads to see "did my backup run?". A dropped write means the box can report no failure and no success. The `FencedBy` marker is how the UI says "this box was replaced by a restore"; the refusal still happens, but the reason is lost.
- **Fix:** one helper `a.record(func(*State))` that logs the error with the run id and sets `Status.Degraded`; use it at the four sites.

### CS2-03
**Golden-path specs skip on routes the code will never serve under that name.** · medium · E2E-GOLDEN, CORE-BACKUP-8
- **Where:** `tests/e2e/specs/04-landing-streams.spec.ts:88-89` (`/v1/tls`), `:33` (`features` includes `app-proxy`), `:117-118` (`/v1/backups/status`).
- **Evidence:** `sdk/openapi/onemind-v1.json` has no `/v1/tls`, no backup route and no `app-proxy` feature. The backup agent serves `GET /api/v1/backup/status` on the **node agent** (`internal/backup/api.go:70`, loopback, port 7480), not on the gateway, so the spec's skip reason "not merged yet" is true forever until a gateway route is added. The other skip reasons in the same file (`/v1/me`, `/v1/events`, `/v1/alerts`) are **stale**: those routes exist now (OpenAPI), so those specs run.
- **Why it matters:** a spec that cannot fail is not a test. Today it hides that the gateway has no backup routes (contract §12.12 promises them).
- **Fix:** replace each "not merged yet" skip with an explicit `test.fixme` that names the epic and fails the run once the route appears in the OpenAPI (so the spec must then be written), or assert the 404 today. Re-check the stale reasons.

### CS2-04
**Gateway modules built but not mounted; six public names have no caller.** · medium · CORE-NET-8, hardening H-34
- **Where:** `core/tests/test_wiring.py:17-21` lists `ca`, `mesh`, `proxy` as "not mounted yet". A scripted search for definitions used nowhere else in `onemind_core/` finds `proxy.py:89 token_session_resolver`, `proxy.py:105 KubectlServiceResolver`, `proxy.py:367 AppProxyMiddleware`, `mesh.py:518 write_secret_file`, `ca.py:61 BoxCA`, `sections.py:130 registered_sections`.
- **Evidence:** unchanged since pass 1 (CS-04); the threat model edition 2 (§4.7) and H-34 record that these are built but not wired. `registered_sections` (`sections.py:130`) is not in `NOT_MOUNTED_YET` and no test or module uses it: a plain dead function.
- **Why it matters:** about 1,300 lines are exercised only by their own tests. Anyone reading `THREAT-MODEL.md` must remember which parts are real.
- **Fix:** mounting stays with CORE-NET-8. Today: delete `registered_sections` or add its caller, and extend `test_wiring.py` with a symbol-level check for names listed above.

### CS2-05
**A unit test fails without internet.** · medium · CORE-NOTIFY-6
- **Where:** `core/tests/test_notify.py:73` (`add_channel` asserts 201) called from `:599` (`test_owner_listing_hides_other_peoples_destinations`).
- **Evidence:** in a container with no DNS the run failed: `{"error":"conflict","message":"config: cannot resolve host (gaierror)"}`. The channel config uses `https://ntfy.sh/owner-topic`; the SSRF guard resolves the host with `socket.getaddrinfo` (`core/onemind_core/notify/channels.py:76-83`, `_addresses`) and raises `DeliveryError` when it cannot. The test never patches the resolver (compare `:567`, which monkeypatches for the DNS-rebinding case).
- **Why it matters:** CI has internet, so it is green there; offline or behind a proxy the suite is red for a reason unrelated to the code.
- **Fix:** monkeypatch `socket.getaddrinfo` (or `_addresses`) in this test, or use a literal public IP. Leave the guard itself strict.

### CS2-06
**Finished symbols with no caller, and the guard cannot see them.** · medium · CORE-NET-12
- **Where:** `internal/leaf/supervise.go:148` (`Supervisor.Run`), `internal/mesh/enroll.go:168` (`Reporter`); no call in `cmd/` (searched).
- **Evidence:** `cmd/wiring_test.go:16-18` already says so in a comment, and `notWiredYet` (`:14`) is empty because both packages are imported (for `onemind mesh status` and `onemindd mesh`). The test is package-level, so it cannot flag these two.
- **Why it matters:** the "wiring" test is green while the leaf supervisor and the mesh heartbeat hook do not run on a box.
- **Fix:** CORE-NET-12 wires them. Until then, list them in `notWiredYet` by symbol (`leaf.Supervisor.Run`) and make the test use `go list -f` plus `go doc`/`grep` per listed symbol so the entry is deleted when wired.

### CS2-07
**Tool-missing skips are silent in the main core job.** · low
- **Where:** `core/tests/test_sdk_conformance.py:94, 103, 114` (`go`, `sdk/ts/node_modules`), `core/tests/test_policy.py:118` (`kustomize`).
- **Evidence:** `.github/workflows/ci-core.yml:39` runs `uv run pytest -q` with no `npm ci`, so the TypeScript live test skips there; `ci-sdk.yml:55-66` installs it and runs the same file, so the coverage exists. The `kustomize` skip has no counterpart that I could confirm (UNVERIFIED whether the runner image has it).
- **Fix:** an env var `ONEMIND_REQUIRE_TOOLS=1`, set in the jobs that install the tools, turns each `skip` into a failure.

### CS2-08
**JSON decode errors ignored in the CLI.** · low
- **Where:** `cmd/onemind/cli/mcp.go:163, 173`; `cmd/onemind/cli/audit.go:83, 230`.
- **Evidence:** `_ = json.Unmarshal(body, &init)` then the code prints `init.Result.ServerInfo.Version` and the tool list. A gateway that answers 200 with a non-JSON body (a proxy error page) makes `onemind mcp doctor` report an empty version and zero tools rather than a failure.
- **Fix:** return `fail("initialize", err)` on a decode error (as the HTTP errors already do).

### CS2-09
**One `verify.sh` check passes vacuously.** · low
- **Where:** `deploy/verify/verify.sh:379-381`.
- **Evidence:** when no audit line is seen on `onemind.audit`, the script prints `SKIP …` and `sys.exit(0)`; `skip()` (`:61`) only fails under `--strict`, and neither `ci-deploy.yml:42` nor `e2e.yml` passes `--strict`. The help text `:19` and `deploy/README.md:138-139` still describe the wave-2 skips that pass 1 turned into failures (docs fix: DS2-06).
- **Fix:** CI should run with `--strict`; keep SKIP for the no-token case only.

### CS2-10
**The §10.3 install rule is written five times.** · low · pass 1 CS-10, still open
- **Where:** `core/onemind_core/scan.py:23` (`MAX_AGE`), `ui/src/lib/trust.ts:17`, `dashboard/src/lib/scan.ts:5`, `mobile/src/lib/scan.ts:7`, `site/src/lib/apps.ts:15`.
- **Evidence:** only the gateway, `ui` and `site` refuse `tier: blocked`; the `dashboard` and `mobile` copies take `Pick<CatalogApp,'scan'>` and cannot (`dashboard/src/lib/scan.ts:22`, `mobile/src/lib/scan.ts:24`), but both are used only by the mock gateway (`dashboard/src/api/mock.ts:133`, `mobile/src/api/mock.ts:133`), so no user-visible harm today.
- **Fix:** golden vectors in `sdk/testdata/` (one JSON file of `{app, now, expect}` rows) read by all five test suites.
- **Owner split:** `dashboard/`, `ui/`, `site/` = orchestrator; `mobile/`, `core/` = Hermes. The shared vector file is `sdk/` (Hermes). Not fixed here: `dashboard/` and `ui/` are being edited by another worker.

### CS2-11
**Dashboard "coming" placeholders are stale for four sections.** · low · CORE-DASH-2
- **Where:** `dashboard/src/pages/Settings.tsx:12-21` (`COMING`): `account` (`/v1/auth/passkeys, /v1/auth/sessions`), `users` (`/v1/users`), `agents` (`/v1/tokens`) and `notifications` (`/v1/notifications/channels, /v1/notifications/preferences`).
- **Evidence:** all of those paths are in `sdk/openapi/onemind-v1.json` now (#41, #44 are merged).
- **Fix:** wire the four sections to the SDK types. Not fixed here: `dashboard/` is being edited by another worker.

## Checked and clean

- No `TODO`, `FIXME`, `HACK` anywhere in shipped code; no commented-out code blocks found in `core/onemind_core` or `internal`.
- `cmd/onemindd` refuses stray arguments and dispatches `update` and `mesh`; `registry.go` starts `backup.Service()` only when its settings file exists.
- `core/tests/test_wiring.py` and `cmd/wiring_test.go` are working guards (new orphan module or package fails).
- The 8 `except …: pass/continue` sites in the gateway parse untrusted lines or hosts and fall back safely (`audit.py:66`, `auditread.py:50`, `proxy.py:139`, `config.py:40`, `executors.py:377`).
- Skips that are correct: `test_nats_integration.py:23` and `test_plumbing.py:341` need `ONEMIND_TEST_NATS_URL`, which `ci-core.yml:38` sets; `internal/backup/integration_test.go:47, 283` need restic and a REST server (heavy CI covers them).

## What I changed in this PR

Nothing in this file's scope: every high or medium code finding is owned by Hermes, or is in `dashboard/`. See the docs audit for the text fixes.
