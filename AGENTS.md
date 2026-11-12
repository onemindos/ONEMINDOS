# Instructions for AI agents working in this repo

## The prime directive: push OneMind OS forward
**Everything you do here must move OneMind OS development forward.** Research, docs, code, reviews and answers all count only if they feed the build.
- **Tie each output to a build step:** a requirement ID (`docs/REQUIREMENTS.md`), a decision (`docs/DECISIONS.md`, Z-xx in `research-output/26-…`), a milestone or gate (`research-output/20-PLAN-180-DAYS.md`), or a workstream in the build brief (`research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md`).
- **Save it in the repo:** useful explanations go into `docs/learning/` or the relevant brief, not only into chat.
- **Build on founder decisions; don't reopen them.** If evidence contradicts one, flag it with sources and leave the decision to Zeus. Also flag any file that conflicts with a decision, so nothing gets built in the wrong direction.
- **Prefer the next shippable step over more analysis:** something that runs, a test that passes, or a kit Zeus can run on hardware.

## Locked founder decisions (read before building)
- **D-001 to D-007** in [docs/DECISIONS.md](docs/DECISIONS.md).
- **Base OS (D-007, Z-38 = b, 2026-11-11): Debian 13 is the shipping base.**
  - Ubuntu 26.04 is a light CI hedge only.
  - Jetson runs NVIDIA L4T (dev kits).
  - Industrial is RHEL-family bootc, in year 2.
- **The stack:** own read-only image, RAUC A/B with health-gated rollback, k3s, NATS, restic, plugin sockets E1–E10, and the capability gateway. **AI never actuates without human approval.**

## Continuing work (read first in a new session)
- **[docs/leap/CONTINUE.md](docs/leap/CONTINUE.md)** lists what is left of the started waves, sorted quick / medium / heavy, and the order to finish them. Merge ownership and the next wave are in [docs/leap/NEXT-WAVE.md](docs/leap/NEXT-WAVE.md).

## Which brief to follow
- **Research mission 01 (done):** [RESEARCH-MISSION.md](RESEARCH-MISSION.md). Output in `research-output/` on branch `research/ultracode-foundation`.
- **Research mission 02, the One Mind fabric** (how every machine joins one OneMind): [RESEARCH-MISSION-02-ONE-MIND-FABRIC.md](RESEARCH-MISSION-02-ONE-MIND-FABRIC.md). Output in `research-output/fabric/` on branch `research/one-mind-fabric`.
- **Build session (OneMind OS core v0):** [`research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md`](research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md), including its founder override box.

## Rules
- Do not edit `docs/` or `context/` except proven factual fixes (separate `fix(docs):` commits with evidence) or founder-requested decision and learning entries.
- No guessing: cite primary sources; label UNVERIFIED.
- Proven competitors first (Home Assistant OS, umbrelOS, Olares): copy patterns, never code from licenses that aren't Apache-compatible.
- This repo is public: never commit secrets, private IPs, personal data or local host paths. Run gitleaks before pushing.
- Push at the end of every wave so no work lives only on one machine. Never force-push without the founder's explicit permission.
- Zeus is learning OS engineering: explain the "why" in plain language and define terms.
