# Instructions for AI agents working in this repo

## The prime directive: push OneMind OS forward
**Everything you do here must move OneMind OS development forward.** Research, docs, code, reviews and answers all count only if they feed the build.
- **Tie each output to a build step:** a requirement ID (`docs/REQUIREMENTS.md`), a decision (`docs/DECISIONS.md`, Z-xx in `research-output/26-…`), a milestone or gate (`research-output/20-PLAN-180-DAYS.md`), or a workstream in the build brief (`research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md`).
- **Save it in the repo:** useful explanations go into `docs/learning/` or the relevant brief, not only into chat.
- **Build on founder decisions; don't reopen them.** If evidence contradicts one, flag it with sources and leave the decision to Zeus. Also flag any file that conflicts with a decision, so nothing gets built in the wrong direction.
- **Prefer the next shippable step over more analysis:** something that runs, a test that passes, or a kit Zeus can run on hardware.

## Locked founder decisions (read before building)
- **D-001 to D-031** in [docs/DECISIONS.md](docs/DECISIONS.md) (there is no D-030). Read the newer ones before touching their area:
  - D-016 and D-018: the desktop (wallpaper, windows, dock) is the one front door. D-026 amends D-018: Backstage is kept and runs on OneMind after the OS is stable.
  - D-017: Samba file sharing is built in. D-015: Kanidm runs as a host service on the hub.
  - D-019 and D-020: Secure Boot (`efi` route, signed UKIs) and disk encryption (TPM by default, passphrase opt-in).
  - D-027 and D-028: permission modes and gateway defaults (approve in advance, bypass only for low-risk digital actions, physical actions keep a person, biometric step-up). D-029: the gateway decides, NATS enforces and carries.
  - D-031: the first key ceremony runs on YubiKeys.
- **Base OS (D-007, Z-38 = b, 2026-11-11): Debian 13 is the shipping base.**
  - Ubuntu 26.04 is a light CI hedge only.
  - Jetson runs NVIDIA L4T (dev kits).
  - Industrial is RHEL-family bootc, in year 2.
- **The stack:** own read-only image, RAUC A/B with health-gated rollback, k3s, NATS, restic, plugin sockets E1–E10, and the capability gateway. **AI never actuates without human approval.**

## Continuing work (read first in a new session)
- **[docs/leap/STATUS.md](docs/leap/STATUS.md)** is the board: what is done, in review and left.
- **[docs/leap/ALPHA-CHECKLIST.md](docs/leap/ALPHA-CHECKLIST.md)** lists what a `v0.1.0-alpha` still needs.
- **[docs/leap/AGENT-QUEUE.md](docs/leap/AGENT-QUEUE.md)** is how agents pick, claim, build and hand in issues: the `owner:`, `wave:`, `area:` and `agent-ready` labels, the definition of done (real data only, tests, DCO sign-off), and the Opus review before merge.
- **[docs/leap/BUILDER-BRIEFING.md](docs/leap/BUILDER-BRIEFING.md)**: read first before any OS or gateway change; the checklist of mistakes reviewers keep sending back.
- Historical (2026-11-12, kept for the record, do not follow): `docs/leap/HANDOFF.md`, `CONTINUE.md`, `NEXT-WAVE.md`.
- **No robotics work until OneMind has a robot** (founder, 2026-11-14): issues labelled `parked` are not started.

## Branches and landing
- **Branch from `origin/release/next` and open the PR (draft first) with base `release/next`.** `release/next` lands on `main` through the GitHub merge queue.
- **Merge commits only (gate practice; repo settings also allow squash and rebase). Never rebase or force-push** (not without the founder's explicit permission); to catch up, merge `origin/release/next` into your branch.
- **Write `Refs #n`, never `Closes #n`.** Issues are closed by hand once the work is truly done.
- **Informational CI workflows** are listed in `INFORMATIONAL` in `scripts/ci-gate.py`: `api-fuzz`, `go-fuzz`, `perf-smoke`, `net-2vm`, `security-nightly`, `apps-gate-all`, `restore-drill`. The merge gate reports them and never waits on or fails for them. On a pull request each one runs only when the PR touches that workflow's own harness paths (for example `core/tests/api_fuzz_check.py`, `test/perf/**`, `test/net/**`, `test/restore-drill/**`) or its workflow file; otherwise they run on pushes to `main` (api-fuzz, go-fuzz, perf-smoke and net-2vm, on their own path filters), nightly or weekly or monthly on a schedule (api-fuzz, go-fuzz, security-nightly, apps-gate-all, restore-drill), by hand, and api-fuzz also in the merge queue. The `nightly` workflow is not informational: it runs on a schedule or by hand only and never on a PR. Replay an api-fuzz seed with `gh workflow run api-fuzz.yml -f seed=N`. The apps CI runs only on changed apps. Runner routing is set by the repo variables `LOCAL_RUNNER` and `MQ_RUNNER` (see [docs/learning/self-hosted-runner.md](docs/learning/self-hosted-runner.md)).

## Engineering: where code lives and how to build it
Run every command from the repo root. On a Mac, install the tools once:
`brew install uv go node@22 gitleaks shellcheck` (Go 1.26, Node 22, Python 3.12 comes through uv), plus Docker Desktop (or a Lima VM: `brew install lima`) for container builds. Before `make test`, follow [the Mac developer loop](docs/learning/mac-dev-loop.md#native-tests-no-docker-or-vm-needed) to create and activate an isolated Python environment and install `requirements-dev.txt`; system Python does not supply PyYAML. Image assembly and release scripts need a Linux build environment, such as the Lima guest; native unit tests need neither Docker nor a VM.

| Part | Code | Check it with (what CI runs) |
|---|---|---|
| Gateway (Python, FastAPI) | `core/` | `make -C core test`; PostgreSQL + NATS: `make -C core test-integration` (needs Docker) |
| Node daemon and `onemind` CLI (Go) | `cmd/`, `internal/` | `gofmt -l cmd internal`, `go vet ./...`, `go test -race -count=1 ./...` |
| SDKs, OpenAPI, schemas | `sdk/` | `make -C sdk check-stale` (the committed spec matches `core/`, the SDK code generates), `make -C sdk test` |
| Dashboard (React) | `dashboard/` | `cd dashboard && npm ci && npm run lint && npm run typecheck && npm test && npm run build` |
| Design system | `ui/` | the same five npm commands in `ui/` |
| Mobile app (Expo) | `mobile/` | `cd mobile && npm ci && npm run typecheck && npx jest --ci` |
| Desktop app (Tauri) | `desktop/` | `cd desktop && npm ci && npm run check:ui && (cd src-tauri && cargo test --locked)` |
| Mac client (Swift, spike) | `desktop-mac/` | see [desktop-mac/README.md](desktop-mac/README.md) (Xcode; macOS only) |
| Website (Astro) | `site/` | `cd site && npm ci && npm run check && npm run build` |
| Tips | `tips/` | `./tips/author check` ([tips/README.md](tips/README.md)) |
| Lab kits (real hardware) | `lab-kits/` | scripts Zeus runs on hardware; see each kit's README |
| Apps (Market) | `apps/` | `python3 -I sdk/tools/validate-apps`, `python3 -I -m unittest discover -s sdk/tools/tests` |
| Install and compose bundle | `deploy/` | `python3 -I deploy/check-pins.py`, `python3 -I deploy/verify/tests/test_verify.py -v` |
| Unit and acceptance suites | `test/unit/`, `test/acceptance/`, other `test/*` (net, perf, restore-drill, ...) | `python3 -I -m unittest discover -s test/unit` (run the whole suite; see the briefing) |
| End-to-end (Playwright) | `tests/e2e/` | see `.github/workflows/e2e.yml` |
| OS image, boot, RAUC | `os/`, `test/qemu/` | `make image BOARD=x86_64-efi`, then `make battery BOARD=x86_64-efi UPTO=T5` (Linux with KVM; on a Mac, CI's `image` workflow runs it) |
| Repo-wide | everything | `make lint`, `make test`, `python3 -I scripts/changes.py check`, `make hygiene` (gitleaks + hygiene greps) |

**Rules that keep the code clean** (the full definition of done is [docs/leap/AGENT-QUEUE.md §4](docs/leap/AGENT-QUEUE.md)):
- **Never export `GIT_DIR` or `GIT_WORK_TREE`.** In a linked worktree use `git -C <worktree> ...`. Git commands run with them set (`git worktree`, `git config`) can write the work tree into the shared `.git/config`, which then redirects every other worktree and sends commits to the wrong folder. `scripts/git-guard.sh` fails when they are set ([docs/learning/mac-dev-loop.md](docs/learning/mac-dev-loop.md#guard-against-committing-into-the-wrong-checkout)).
- **Use the generated client.** Dashboard and app code call the gateway through `@onemind/sdk` (`sdk/ts`), never hand-written API types. Change the API in `core/`, then run `make -C sdk gen` and commit only the spec `sdk/openapi/onemind-v1.json`; the generated SDK code is not committed (CI-16), and a fresh clone runs `make -C sdk gen-code` once before building.
- **Read [docs/leap/BUILDER-BRIEFING.md](docs/leap/BUILDER-BRIEFING.md) before an OS or gateway change** (read-only root, `/data` writes, systemd sandboxing, pre-registered QEMU checks).
- **Wire it up.** A feature is reachable from a mounted route, a dashboard screen or the `onemind` CLI in the same PR, or the PR says why not. No new mock backend.
- **Tests in the same PR,** one issue per PR, under about 600 changed lines unless the PR is labelled `large`.
- **One change fragment per PR:** `changes/<branch-with-dashes>.md` ([changes/README.md](changes/README.md)). `CHANGELOG.md` and `docs/leap/STATUS.md` are filled from the fragments, never edited in a feature PR.
- **Sign off every commit** (`git commit -s`) and open the PR with the template in `.github/pull_request_template.md`. `.github/CODEOWNERS` requests the reviewer.

## Which brief to follow
- **Build brief (OneMind OS core v0):** [`research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md`](research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md), including its founder override box.
- **Research missions (done, for background):** [RESEARCH-MISSION.md](RESEARCH-MISSION.md) (output in `research-output/` on branch `research/ultracode-foundation`) and [RESEARCH-MISSION-02-ONE-MIND-FABRIC.md](RESEARCH-MISSION-02-ONE-MIND-FABRIC.md) (how every machine joins one OneMind; output in `research-output/fabric/` on branch `research/one-mind-fabric`).

## Rules
- Do not edit `docs/` or `context/` except proven factual fixes (separate `fix(docs):` commits with evidence) or founder-requested decision and learning entries.
  - This does not clash with the status table: feature PRs never edit `docs/leap/STATUS.md` or `CHANGELOG.md`; they add a `changes/` fragment, and the `changes-collect` job writes both files.
- No guessing: cite primary sources; label UNVERIFIED.
- Proven competitors first (Home Assistant OS, umbrelOS, Olares): copy patterns, never code from licenses that aren't Apache-compatible.
- This repo is public: never commit secrets, private IPs, personal data or local host paths. Run gitleaks before pushing.
- Push at the end of every wave so no work lives only on one machine. Never force-push without the founder's explicit permission.
- Zeus is learning OS engineering: explain the "why" in plain language and define terms.
