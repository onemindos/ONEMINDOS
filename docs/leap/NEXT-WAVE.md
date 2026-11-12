<!-- SPDX-License-Identifier: Apache-2.0 -->
# Next wave (Wave G) and merge ownership

**Prepared:** 2026-11-12, while Waves D, E and F run. **Board:** [STATUS.md](STATUS.md) · **Record:** [CHANGELOG.md](../../CHANGELOG.md)

> **Explain it like I am the founder**
> This page says two things. First, who is responsible for merging each branch that is still in flight, so nothing built gets left behind. Second, what starts next, in order, once the current waves finish. Nothing on this page starts until the work it depends on has merged.

## 1. Merge ownership (every unmerged branch has exactly one owner)

| Branch | What | Merged by | Waits for |
|---|---|---|---|
| `feat/sec-p0` (#40) | Security P0 | Wave D integrator | CI |
| `feat/identity` (#41) | Accounts, passkeys | Wave D integrator | #40 |
| `feat/notify-monitor` (#44) | Notifications, monitoring | Wave D integrator | #41 |
| `feat/devsurface` | SDKs, CLI, MCP | Wave D integrator | #44 |
| `feat/e2e-golden-path` | Golden-path e2e | Wave D integrator | devsurface |
| `feat/test-security`, `feat/test-property-fuzz`, `feat/test-ci-matrix` (#42) | Attack suite, fuzzing, CI matrix | Their own builders | CI |
| `docs/slop-audit` | Slop audit + fixes | Wave D slop fixer | Wave D phase 1 |
| `feat/app-lifecycle` | App lifecycle P0 | Its builder | Wave D phase 1 |
| `feat/net-part2`, `feat/backups-on`, `feat/app-secrets`, `feat/mobile-v1`, `feat/photos-server`, `feat/storage-actions`, `feat/migrate-kit`, `feat/market-batch-4-5` | The 12-gap streams | Wave E landers | Wave D integration |
| `feat/deploy-port27` | Ports from #27 | Wave E lander | `feat/net-part2` |
| `feat/dashboard-v2`, `feat/market-batch-1`, `feat/automation`, `feat/files` | Wave C streams | Wave F landers | Wave D integration |
| `feat/appstore-depth` | App store depth | Its builder | `feat/app-lifecycle` |
| `feat/desktop-v1` | Desktop v1 | Its builder | #33, brand |
| `feat/dashboard-wiring` | Pages for every new API | Its builder | `feat/dashboard-v2` |
| `research/one-mind-fabric-2`, `docs/learning-what-we-built`, `feat/perf-budget`, `spike/machines` | Research, learning, perf, VM spike | Their own builders | — |
| `feat/market-batch-2-3`, `feat/plugin-sdk-v0`, `docs/site-user-guides` | Market, plugin SDK, guides | Their own builders | CI |
| `docs/board-gaps` (#43) | Board refresh | Merge watcher | CI |
| `feat/desktop-client` (#33), `feat/mobile-photos` (#34) | Desktop app, phone photos | Merge watcher | CI |
| `feat/image-line` | OneMind in every image, Pi 5, Jetson, installer, cloud, releases | **Orchestrator** when its workflow finishes | — |
| `feat/brand-single-source` | Logo and brand everywhere | **Orchestrator** when its workflow finishes | — |
| `test/register` | Test register, test-all | **Orchestrator** when its workflow finishes | — |
| `feat/ui-leap`, `feat/app-hermes`, `feat/apps-wave2` | Stale or empty (ui-leap shipped squashed as #29) | Delete after checking | — |

## 2. Wave G (starts when Waves D–F have landed)

In order; each item is build → independent review → land, with its board row and CHANGELOG entry in the same PR.

1. **Image integration.** Apply the os/ patches the other streams wrote (`docs/leap/core/*-os.patch.md`): mesh and NATS TLS, LUKS2 initrd and layout, brand boot splash/GRUB/os-release, the updater and its TUF root location. Re-run the full QEMU battery and first-boot tests on every board.
2. **Full CI run.** Trigger `test-all.yml`, `apps-gate-all.yml`, `ui-quality.yml`, `api-fuzz.yml` and `perf-smoke.yml` on `main`; turn every failure into a fix PR; update `docs/testing/TEST-REGISTER.md` statuses.
3. **Security re-review.** Refresh `docs/security/THREAT-MODEL.md` for everything merged since #18 (identity, mesh, proxy, backups, secrets, storage, migrate, plugins); a fresh hardening backlog; fix P0s.
4. **Slop pass 2.** Repeat the three audits (code, docs, drift) on the new `main`; fix.
5. **Parity check.** Re-score `docs/strategy/umbrel-parity.md` and `docs/umbrel2/README.md` against `main`; the remaining P0/P1 gaps become the next streams.
6. **Clients catch-up.** Mobile and desktop parity with every API the dashboard wiring pass added.
7. **Market.** Unblock apps the gate blocked (newer upstream images, or documented holds); batches 6+ from `apps/_intake/CANDIDATES.md`.
8. **Fabric follow-through.** Turn the mission-02 research answers into epics and the first build stream.
9. **Alpha readiness.** A release checklist for v0.1.0-alpha (images, downloads page, signed releases, upgrade path, docs), blocked on the founder items below.

## 3. Blocked on the founder

| Id | Decision | Unblocks |
|---|---|---|
| F-25 | Order the hardware (Pi 5 16 GB + NVMe, Pi 5 4 GB, Jetson Orin Nano Super, Meshtastic radios) | Every real-hardware test (TEST-REGISTER) |
| F-27 | Offline TUF root ceremony and signing secrets | Publishing OS updates and signed releases |
| F-7 | Owner override for scan-blocked apps (built, off by default) | Hermes until upstream ships a fixed image |
| F-5 | Website domain and hosting | Deploying the site |
