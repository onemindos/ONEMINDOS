# Instructions for AI agents working in this repo

## The prime directive: push OneMind OS forward
**Everything you do here must move OneMind OS development forward.** Research, docs, code, reviews and answers all count only if they feed the build.
- **Tie each output to a build step:** a requirement ID (`docs/REQUIREMENTS.md`), a decision (`docs/DECISIONS.md`, Z-xx in `research-output/26-…`), a milestone or gate (`research-output/20-PLAN-180-DAYS.md`), or a workstream in the build brief (`research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md`).
- **Save it in the repo:** useful explanations go into `docs/learning/` or the relevant brief, not only into chat.
- **Build on founder decisions; don't reopen them.** If evidence contradicts one, flag it with sources and leave the decision to Zeus. Also flag any file that conflicts with a decision, so nothing gets built in the wrong direction.
- **Prefer the next shippable step over more analysis:** something that runs, a test that passes, or a kit Zeus can run on hardware.

## Locked founder decisions (read before building)
- **D-001 to D-014** in [docs/DECISIONS.md](docs/DECISIONS.md).
- **Base OS (D-007, Z-38 = b, 2026-11-11): Debian 13 is the shipping base.**
  - Ubuntu 26.04 is a light CI hedge only.
  - Jetson runs NVIDIA L4T (dev kits).
  - Industrial is RHEL-family bootc, in year 2.
- **The stack:** own read-only image, RAUC A/B with health-gated rollback, k3s, NATS, restic, plugin sockets E1–E10, and the capability gateway. **AI never actuates without human approval.**

## Continuing work (read first in a new session)
- **[docs/leap/HANDOFF.md](docs/leap/HANDOFF.md)** is the full hand-off: everything left, split between two agents, with their prompts.
- **[docs/leap/CONTINUE.md](docs/leap/CONTINUE.md)** lists what is left of the started waves, sorted quick / medium / heavy, and the order to finish them. Merge ownership and the next wave are in [docs/leap/NEXT-WAVE.md](docs/leap/NEXT-WAVE.md).

## Picking up build work (Codex, GPT, Claude)
- **[docs/leap/AGENT-QUEUE.md](docs/leap/AGENT-QUEUE.md)** is how agents pick, claim, build and hand in issues: the `owner:`, `wave:`, `area:` and `agent-ready` labels, the definition of done (real data only, tests, DCO sign-off), and the Opus review before merge.
- **No robotics work until OneMind has a robot** (founder, 2026-11-14): issues labelled `parked` are not started.

## Engineering: where code lives and how to build it
Run every command from the repo root. On a Mac, install the tools once:
`brew install uv go node@22 gitleaks shellcheck` (Go 1.26, Node 22, Python 3.12 comes through uv), plus Docker Desktop (or a Lima VM: `brew install lima`) for container builds. Before `make test`, follow [the Mac developer loop](docs/learning/mac-dev-loop.md#native-tests-no-docker-or-vm-needed) to create and activate an isolated Python environment and install `requirements-dev.txt`; system Python does not supply PyYAML. Image assembly and release scripts need a Linux build environment, such as the Lima guest; native unit tests need neither Docker nor a VM.

| Part | Code | Check it with (what CI runs) |
|---|---|---|
| Gateway (Python, FastAPI) | `core/` | `make -C core test`; PostgreSQL + NATS: `make -C core test-integration` (needs Docker) |
| Node daemon and `onemind` CLI (Go) | `cmd/`, `internal/` | `gofmt -l cmd internal`, `go vet ./...`, `go test -race -count=1 ./...` |
| SDKs, OpenAPI, schemas | `sdk/` | `make -C sdk check-stale` (generated code is current), `make -C sdk test` |
| Dashboard (React) | `dashboard/` | `cd dashboard && npm ci && npm run lint && npm run typecheck && npm test && npm run build` |
| Design system | `ui/` | the same five npm commands in `ui/` |
| Mobile app (Expo) | `mobile/` | `cd mobile && npm ci && npm run typecheck && npx jest --ci` |
| Desktop app (Tauri) | `desktop/` | `cd desktop && npm ci && npm run check:ui && (cd src-tauri && cargo test --locked)` |
| Apps (Market) | `apps/` | `python3 -I sdk/tools/validate-apps`, `python3 -I -m unittest discover -s sdk/tools/tests` |
| Install and compose bundle | `deploy/` | `python3 -I deploy/check-pins.py`, `python3 -I deploy/verify/tests/test_verify.py -v` |
| OS image, boot, RAUC | `os/`, `test/qemu/` | `make image BOARD=x86_64-efi`, then `make battery BOARD=x86_64-efi UPTO=T5` (Linux with KVM; on a Mac, CI's `image` workflow runs it) |
| Repo-wide | everything | `make lint`, `make test`, `python3 -I scripts/changes.py check`, `make hygiene` (gitleaks + hygiene greps) |

**Rules that keep the code clean** (the full definition of done is [docs/leap/AGENT-QUEUE.md §4](docs/leap/AGENT-QUEUE.md)):
- **Never export `GIT_DIR` or `GIT_WORK_TREE`.** In a linked worktree use `git -C <worktree> ...`. Git commands run with them set (`git worktree`, `git config`) can write the work tree into the shared `.git/config`, which then redirects every other worktree and sends commits to the wrong folder. `scripts/git-guard.sh` fails when they are set ([docs/learning/mac-dev-loop.md](docs/learning/mac-dev-loop.md#guard-against-committing-into-the-wrong-checkout)).
- **Use the generated client.** Dashboard and app code call the gateway through `@onemind/sdk` (`sdk/ts`), never hand-written API types. Change the API in `core/`, then run `make -C sdk gen` and commit the result.
- **Wire it up.** A feature is reachable from a mounted route, a dashboard screen or the `onemind` CLI in the same PR, or the PR says why not. No new mock backend.
- **Tests in the same PR,** one issue per PR, under about 600 changed lines unless the PR is labelled `large`.
- **One change fragment per PR:** `changes/<branch-with-dashes>.md` ([changes/README.md](changes/README.md)). `CHANGELOG.md` and `docs/leap/STATUS.md` are filled from the fragments, never edited in a feature PR.
- **Sign off every commit** (`git commit -s`) and open the PR with the template in `.github/pull_request_template.md`. `.github/CODEOWNERS` requests the reviewer.

## Which brief to follow
- **Research mission 01 (done):** [RESEARCH-MISSION.md](RESEARCH-MISSION.md). Output in `research-output/` on branch `research/ultracode-foundation`.
- **Research mission 02, the One Mind fabric** (how every machine joins one OneMind): [RESEARCH-MISSION-02-ONE-MIND-FABRIC.md](RESEARCH-MISSION-02-ONE-MIND-FABRIC.md). Output in `research-output/fabric/` on branch `research/one-mind-fabric`.
- **Build session (OneMind OS core v0):** [`research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md`](research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md), including its founder override box.

## Rules
- Do not edit `docs/` or `context/` except proven factual fixes (separate `fix(docs):` commits with evidence) or founder-requested decision and learning entries.
  - This does not clash with the status table: feature PRs never edit `docs/leap/STATUS.md` or `CHANGELOG.md`; they add a `changes/` fragment, and the `changes-collect` job writes both files.
- No guessing: cite primary sources; label UNVERIFIED.
- Proven competitors first (Home Assistant OS, umbrelOS, Olares): copy patterns, never code from licenses that aren't Apache-compatible.
- This repo is public: never commit secrets, private IPs, personal data or local host paths. Run gitleaks before pushing.
- Push at the end of every wave so no work lives only on one machine. Never force-push without the founder's explicit permission.
- Zeus is learning OS engineering: explain the "why" in plain language and define terms.
