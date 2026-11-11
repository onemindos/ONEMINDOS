# 🛠️ BUILD MISSION: OneMind OS core, release v0 (the second ultracode session, F-9)

> **You are the build lead for OneMind OS.** This file is your complete, one-shot brief. **You cannot ask the founder anything during this run.** Every decision you need is stated here, either as a research decision you build on (§4.1) or as a build default you apply unless the founder has already overridden it in writing (§4.2). Work at maximum depth: run independent workstreams in parallel, prove every claim with a test, and keep going until §10's definition of done is met or you have documented exactly what remains. Token cost is not a constraint. Shipping something that bricks a box, leaks a secret or lets an AI move a robot without approval is.

**Commissioned by:** Zeus Delacruz, founder · **Written:** 2026-11-11 by the research run (tag BRIEF30) · **Planned Day 1:** Monday 2026-11-16 (the `20-PLAN-180-DAYS.md` calendar)
**Repo:** https://github.com/onemindos/ONEMINDOS (public). Base branch `main`. Never force-push.
**Reviewer:** Zeus, who is learning OS and platform engineering as he goes. Every handbook page you write explains the "why" in plain English and defines its terms.
**Claims:** IDs in brackets resolve in `research-output/evidence/claims/*.csv`. New facts this brief verified are `C-BRIEF30-001…007` (sources in [`evidence/sources/BRIEF30.md`](evidence/sources/BRIEF30.md)). Everything else is an existing research row.
**Serves requirements:** F-9 (primary), F-3, F-5, F-6, F-7, F-8, F-11, F-14, R-1, R-2, R-3, M-2, M-6, M-7, M-8, P-1, P-4, P-7, P-8, N-3, N-4, N-6, N-9, A-1, A-5, A-6, AI-2, AI-3, AI-4, AI-5, AI-7, AI-9, U-1, U-4, UX-1, UX-4, UX-6, H-3, D-001, D-002, D-003, D-004 (full trace in §14)

> ### Explain it like I'm the founder
> The research run decided *what* OneMind OS stands on. This file tells the next AI session *how to build it*, in an order that proves the dangerous parts first.
> Think of it as a recipe card with the safety rules printed on top. The agent builds **your own read-only Debian 13 image**, with **two copies of the OS (A/B)** managed by **RAUC**, so a bad update rolls itself back. On top runs **k3s** (small Kubernetes), and on top of that the **OneMind Core**: sign-in, the "capability gateway" that every human, app and AI request must pass through, the action ledger, backups, the Market and the dashboard.
> The agent can do almost everything inside virtual machines on your Mac and in GitHub's build machines. It **cannot** touch your Pi, Jetson, Dell or Beelink, your live cluster, your signing keys, or any vendor. For each of those it writes you a **kit**: exact commands and pass/fail rules, so you run the test in an hour and paste the result back.
> Where a choice is yours (which login system, which task tracker, whether security updates install by default…), the brief picks the option the research recommended and lists it in §11 so you can overrule it in one line.
> Success after this session looks like: a signed image boots in QEMU for x86, generic arm64 and (as a kit) Pi 5; a broken update rolls back by itself; you sign in, an AI agent asks to switch on a test light and **cannot until you approve on your phone**; a simulated robot arm is discovered, starts in "observe-only", and stops safely when its plugin is revoked; a backup restores onto a fresh VM. Everything else is labelled honestly as done, kit-ready, or not started.

---

## 0. The mission in one paragraph

Implement **OneMind OS release v0** exactly as decided in [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) revision 3: a Debian 13 read-only image built from container-defined layers, A/B updates with **OneMind's own RAUC built from v1.15.2**, a **fresh-signal health gate**, the **§4.3 disk layout** with LUKS2 data from first boot and a Secure-Boot-ready boot route, **hardened k3s** on platform nodes, **restic** backups with the online SQLite procedure, the **ten extension points E1–E10** with their enforcement, the **Core vertical slice** (identity, agent identity, capability gateway, action ledger, audit), the first Market apps and two profiles, the **dashboard MVP**, the **"connect a robot" MVP**, a **test harness** that turns every passed research lab into a CI job, and a **CI/CD pipeline** from the founder's Mac to signed artifacts. Map the work onto the six phases and eight gates of [`20-PLAN-180-DAYS.md`](20-PLAN-180-DAYS.md) and the Blueprint acceptance tests A01–A24. Produce founder kits for every hardware test you cannot run.

**North star (from the founder, unchanged):** *"I want to connect a robot" → "use OneMind OS."* One OS from a Pi greenhouse to a GPU cluster with no product switch (F-14). Ease of use first. Open core under Apache-2.0 (D-001).

---

## 1. Read first, in this order

1. **This file**, in full.
2. [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) §1 (answer table), §4 (every recommendation in detail), §7 (ADR-001 verdicts), §11 (REC-DEC-01…41), §12 (conditions). **01 wins** over any other research file where they differ; this brief restates 01 and wins only where it fills a gap 01 left open (stated in §4.2).
3. [`20-PLAN-180-DAYS.md`](20-PLAN-180-DAYS.md): phases P1–P6, gates G0–G7, the cut list (§8) and the never-cut list.
4. [`22-HARDWARE-LAB-TEST-PLAN.md`](22-HARDWARE-LAB-TEST-PLAN.md): every `LT-*` test, its pass/fail criteria and the result template (§2.5). You **reuse those IDs and criteria verbatim**.
5. [`29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`](29-PLATFORM-ECOSYSTEM-MARKETPLACE.md) §3, §6–§11, §16 (plugin types, manifest, CLI, security model, robot onboarding, tests). **Where 29 §1 differs from 01 §4.8 (nine vs ten points, combined vs per-vendor driver packs), 01 wins.**
6. [`28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md`](28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md) §6 (kernel contract), §9 (Mac setup), §10 (CI/CD diagram). **Its §7 image-builder choice (Rugix Bakery) is superseded by §4.2 BD-05 of this brief**, because 01 moved the engine to RAUC.
7. The lab kits you will port, in `research-output/evidence/lab/`: `rauc-1152/` (the reference build and battery), `rauc-k3s-gate/`, `secureboot-rauc/`, `ubuntu-2604-leg/`, `mender/`, `k3s-footprint-restore/`, `w19-sysext/`, `w8-nats-leaf-buffer/`, `minimal-image-dc20/`. Read each README's pass/fail table and `versions.md`.
8. Context for the product layer: `context/02-prior-planning.md` (§3 product surfaces, §4 authority rule and API, §5 action lifecycle, §6 manifest and signing, §7 identity, §8 NATS envelope, §10 offline sync, §15 restore drill, §16 milestones, §18 A01–A24); `context/01-proven-infrastructure-cluster.md` §5 (NATS subject grammar); [`10-ai-capability-layer.md`](10-ai-capability-layer.md) REC-W9-01…12; [`12-dashboard-clients-xr.md`](12-dashboard-clients-xr.md) REC-W11-01…20; [`13-apps-market-plugins.md`](13-apps-market-plugins.md) §3.4, §5, §8.3; [`06-backups-recovery.md`](06-backups-recovery.md) W5-R1…R14; [`09-iot-mesh-offgrid-tak.md`](09-iot-mesh-offgrid-tak.md) §2.2 and §8; [`11-hardware-line.md`](11-hardware-line.md) §5.2.
9. [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md): every Z-item. You apply its recommendation unless the founder decided otherwise (check the PR and `handbook/decisions.md` if it exists).
10. `docs/REQUIREMENTS.md` (the requirement IDs), `docs/DECISIONS.md` (D-001…D-006, binding), `docs/APPS.md`.

---

## 2. Rules

1. **Build only what 01 decided.** Never swap a decided component (Debian, RAUC, k3s, restic, Kanidm by default, Traefik + Gateway API, NATS) because something else looks easier. If you find evidence that a decision is wrong, write it down in `handbook/findings.md` with a test that shows it, keep building on the decision, and flag it in the PR. The only legal way a decision moves is a gate result read against its **pre-written** rule (20 §4).
2. **Pin everything.** Every package, image, tool and upstream repo is pinned to a version **and** a digest or commit SHA, recorded in `os/versions.lock.yaml` (machine-readable) and `handbook/versions.md` (human). Never `latest`, never a branch, never an unpinned `curl | sh`. Debian packages come from a dated `snapshot.debian.org` timestamp. Container base images are pinned by digest.
3. **No guessing in code or docs.** Before relying on a tool's behaviour or flag, open its primary documentation or source at the pinned version and record the URL plus commit in a code comment or `handbook/versions.md`. If you cannot open it, write a test that proves the behaviour, or mark the item `UNVERIFIED` in `handbook/findings.md`. New product or version facts you discover go into `research-output/evidence/claims/BUILD.csv` with the same header and rules as the research ledger (IDs `C-BUILD-###`, `recheck_by` +6 months for kernel/BSP/Kubernetes, +12 months for lifecycle and pricing).
4. **Every pass/fail criterion is written before the run.** For each new test, commit its criteria first (a separate commit, or a `PREREGISTRATION.sha256` like `rauc-1152/`), then the code that runs it. A failed test is re-run once only if its log shows a harness fault. Never edit a criterion to make a result pass.
5. **Licences (D-001).** All OneMind code is Apache-2.0 with SPDX headers; contributions use a **DCO sign-off** (`git commit -s`), no CLA (REC-W16-02). You may **study** umbrelOS (PolyForm-Noncommercial), Olares (AGPL), Glance (AGPL), Homepage (GPL) and umbrel-apps (no licence) [C-W12-002]; **never copy their code or manifests.** Copying Apache/MIT code (Olares's `beclab/apps` charts, CasaOS-AppStore, Homarr integration code, HAOS scripts) is allowed with attribution and the upstream LICENSE kept, after a per-file review noted in `NOTICE`. Every third-party component you add must already have a row in `research-output/evidence/license-matrix.csv`, or you add one (pinned LICENSE file at a SHA) before using it. L3/L4 apps (13 §4) are never preinstalled.
6. **Safety of the machine you run on.** Untrusted code (any downloaded installer, any upstream build script you have not read, any image you did not build) runs only inside a **disposable Lima or QEMU VM** with no host mounts except one work folder, no credentials and user-mode networking with `restrict=on` where the test allows. Read every `curl | bash` script before running it in a VM, and hash it. Keep your own scripts outside downloaded trees, and run Python that reads them with `python3 -I`.
7. **What you never do.** Never contact vendors, send email, open issues on upstream projects, or post anywhere outside this repo (draft any outreach in `handbook/outreach-drafts.md`). Never touch the founder's live DOKS cluster, Tailscale, Argo CD or DigitalOcean account, even read-only; live-cluster checks are founder tests (22 §9). Never write, burn or fuse anything irreversible (Pi OTP, Jetson fuses, EEPROM keys). Never generate, request or store a **production** signing key; you use throwaway development keys only (§6 B4). Never rewrite git history.
8. **Physical safety.** Linux and AI are never the safety function (W7-R6). Any capability with `effect: actuate` requires human approval at the gateway, a TTL, an idempotency key and a declared safe state. A queued physical command never replays after its TTL (A12). No code path lets an agent approve its own request.
9. **Public-repo hygiene (the repo is public; this is not optional).**
   - Never commit: secrets, keys (even throwaway ones), tokens, kubeconfigs, `state.db`, restic passwords, LUKS recovery keys, private IPs (RFC1918 and 100.64/10: mask as `<vm-private-ip>`, `<pod-ip>`), `.ts.net` names, e-mail addresses, host usernames, home paths (refer to `<lab-dir>` and `<repo>`), serial numbers, MAC addresses, or raw `kubectl`/`doctl` output.
   - Before **every** push run `make hygiene`, which you build in B0. It runs `gitleaks dir .` and `gitleaks git --log-opts="origin/main..HEAD"` with gitleaks v8.30.1 [C-BRIEF30-006], plus greps for `/Users/[a-z]`, `/home/[a-z]`, RFC1918/CGNAT addresses, `[A-Za-z0-9.-]+\.ts\.net` and e-mail-shaped strings. Every remaining hit must be a reviewed false positive listed in `handbook/hygiene.md` (same format as `research-output/evidence/hygiene-log.md`). A non-empty unreviewed result blocks the push.
   - Logs you commit are trimmed and masked by a script (pattern: `rauc-1152/scripts/trim-logs.sh`). Lab images, disks and bundles are never committed; only their sha256 in `SHA256SUMS`.
   - Masking also covers documentation examples that look like credentials, because GitHub push protection rejects them.
10. **Teach.** Every major handbook page (`handbook/*.md`) has an "Explain it like I'm the founder" box, a glossary, a "What competitors do" table **with a constraint-fit column**, and the requirement IDs it serves. Plain English; define every acronym on first use.
11. **Trace.** Every workstream deliverable names the REC-DEC/REC-W* it implements and the requirement IDs it serves. `handbook/trace.md` maps requirement ID → code path → test.
12. **Checkpoint.** Commit and push after each workstream milestone so partial work survives. Small, reviewable commits with conventional messages (`feat(os): …`, `test(gate): …`).

---

## 3. Tools, limits and what you cannot do

**You have:** a shell on an Apple-silicon Mac, the GitHub CLI with access to `onemindos/ONEMINDOS`, GitHub Actions (public repo: hosted amd64 and arm64 Linux runners `ubuntu-24.04` and `ubuntu-24.04-arm` are free and unlimited [C-W18-057]), Lima VMs (Lima v2.3.0 is current [C-BRIEF30-005]; the research lab ran Lima 2.3 on the `vz` driver with nested virtualisation [C-W18-054]), QEMU, Docker inside a Lima VM, web search and fetch.

**Limits.** Nested KVM in Lima needs an M3 or newer Mac on macOS 15+ [C-W18-054]; check with `limactl shell onemind-dev ls -l /dev/kvm` and fall back to TCG (slower; the research batteries took 41–56 min under TCG) or to CI. x86 guests on the arm64 Mac are emulated (TCG); run x86 batteries in CI on amd64 runners when time matters. On GitHub-hosted runners, check for `/dev/kvm` at job start and record whether the job used KVM or TCG; never assume.

**Method substitutions:**

| If the work needs… | Do this instead |
|---|---|
| A Raspberry Pi 5, Jetson Orin Nano Super, Dell 5540 or Beelink U55 | Build the image or kit, run everything the board-independent path allows in QEMU (x86_64 UEFI, aarch64 UEFI), and write the founder kit under `lab-kits/<LT-ID>/` with the exact commands and the 22-… pass/fail text. Mark the item `kit-ready (blocked: founder-hardware)` |
| A real power cut | QEMU `SIGKILL` at the scripted moments (as the labs did), labelled "emulated power cut"; the real pull is PP-10 in the founder kit (QEMU's kill does not drop the disk's write cache, 22 §2.4) |
| Production signing keys, an HSM, the key ceremony | Throwaway dev keys generated inside the CI job or the VM and destroyed at the end; the ceremony is a script plus a placeholder document (§6 B4.6) |
| The founder's live cluster, Hermes, the existing `omos` Core | The contracts in `context/01` and `context/02` only. Write adapters against those contracts and fixtures; mark live integration `blocked: founder-access` |
| A founder choice | §4.2 default; list it in §11's table in the PR body |
| An NVIDIA GPU | Build the CI job and the module-signing path; the GPU smoke test is a founder kit (LT-GPU-01) on a rented RTX instance |
| A real robot | The simulated arm (§6 B12) over QEMU's emulated USB serial device; the SO-101 run is a founder kit (LT-PI5-13j) |

---

## 4. Decisions you build on

### 4.1 Research decisions (frozen; from 01 rev. 3; do not reopen)

| Area | Decision | Source |
|---|---|---|
| Base | **Debian 13 "trixie"** core for x86_64, generic arm64 and Pi 5 (Raspberry Pi's kernel and apt repo on Pi). A second CI leg builds the same definition `FROM ubuntu:26.04` and runs the x86 battery, as a hedge only (never shipped until Z-01 is answered) | 01 §4.1, REC-DEC-01, -17 [C-W2-043, C-W2-044, C-LAB-ubuntu-2604-leg-011] |
| Jetson | NVIDIA **L4T Ubuntu 24.04 (JetPack 7.2+)** flavor for a Robotics beta, built only as a **dev-kit flavor, never distributed** until Z-01; every Jetson flashed with `ROOTFS_AB=1`; meta-tegra is a founder lab (LT-JET-06), not this build | 01 §4.1, REC-DEC-18 [C-REF-DC-cost-005, C-REF-DC-cost-007] |
| Image | OneMind owns the image: a container-defined rootfs on a snapshot-pinned Debian, assembled into A/B disk images; read-only root | 01 §1, §4.1 [C-W2-043] |
| Updates | **RAUC built from upstream v1.15.2** (commit `4fb7c798d6ae412344fb8f8d310d773046af3441`), never Debian's package; `bundle-formats=verity`; **3 boot tries** on the x86 GRUB route; abandoned trials on Pi 5 and the `efi` route are re-offered (bounded, never a gate-rejected release); one release contract; no auto-retry of a rejected release | 01 §4.2, REC-DEC-05, -31, -32 [C-LAB-rauc-1152-011, C-LAB-ubuntu-2604-leg-010, C-LAB-rauc-1152-012] |
| Gate | Fresh signals only; apps excluded; trial marker in RAUC **pre-install**; never `After=k3s.service`; version-match rule | 01 §4.2 item 5, REC-DEC-07, -23 [C-LAB-rauc-k3s-gate-001…010, C-LAB-secureboot-rauc-018] |
| Layout | The 01 §4.3 x86 layout (below in B2); LUKS2 data from first boot | REC-DEC-08 [C-LAB-secureboot-rauc-020] |
| x86 boot route | Target RAUC's **`efi` backend + one signed UKI per slot**; GRUB backend is the fallback; Z-18 decides at G2 | REC-DEC-20 [C-LAB-secureboot-rauc-013, C-LAB-secureboot-rauc-003] |
| Kubernetes | **k3s v1.37.2+k3s1** on platform nodes (≥ 4 GB RAM and SSD/NVMe), pinned hardened config, state bind-mounted off the read-only root, `secrets-encryption` on; capturable field nodes run the **agent only**; NATS leaf below the floor; Gateway API + Traefik; no system-upgrade-controller on image nodes | 01 §4.5, REC-DEC-09, -22, -23 [C-LAB-rauc-k3s-gate-004, C-W4-016, C-W3-065, C-REF-W4-security-008] |
| Storage and backups | local-path with a **Retain** class; **restic v0.19.1** upstream binary, three-key repository; single-box datastore = online SQLite `.backup` + token + node password + encryption config inside restic; restore drill per shipped k3s version | 01 §4.6, REC-DEC-11, -28 [C-W5-019, C-W5-009, C-LIC-036] |
| Plugins | E1–E10 with enforcement: signed-only extension policy, no directory extensions, quarantine before merge, per-vendor driver packs, `module.sig_enforce=1`, expiring revocation list; E5, E6, E8 ship as v1-beta | 01 §4.8, REC-DEC-24, -40 [C-REF-W19-security-004] |
| Security | Gateway-enforced human approval for actuation, OS updates, installs, exports; robot-runtime exception by signature; Pod Security Restricted for Market namespaces; default-deny NetworkPolicy | 01 §4.7, REC-DEC-13, -36 [C-W6-068, C-W7-033, C-DEC-015] |
| Kernel | K1 at launch (Debian stock, Raspberry Pi's, NVIDIA L4T) plus a CI-checked **kernel contract**; K2-hybrid only for the release that enforces Secure Boot with out-of-tree modules | 01 §3.5, REC-DEC-12, -25 [C-DEC-008…010] |

### 4.2 Build defaults (gaps 01 left open; founder may override, see §11)

| ID | Default | Why (evidence) | Override path |
|---|---|---|---|
| **BD-01** | Implementation lives **in this repo** next to `research-output/`, on branch `build/core-v0` cut from `main` (if the research PR is not merged yet, cut from `research/ultracode-foundation` and say so in the PR) | One public repo keeps research, decisions and code traceable; the research PR is the input | Founder names another repo |
| **BD-02** | **Languages:** Go for host and cluster plumbing (`onemindd`, the `onemind` CLI, `onemind-probe`, the Market controller, the capability broker admission webhook); **Python + FastAPI** for the Core (gateway, policy, ledger, audit, adapters), honouring the Blueprint's OS-D02 ("keep the Python Core and MCP; TS for SDK and UI", context/02 §19) and the existing Python `onemind-core` and `onemind-mcp`; **TypeScript + React** for the dashboard and widget SDK (REC-W11-01). Gate scripts stay **POSIX shell** (REC-DEC-41) | Go gives single static binaries for x86/arm64/Jetson with no interpreter on the host and native libraries for TUF and Sigstore (go-tuf v2.4.2 [C-LIC-056], sigstore-go v1.4.0 [C-BRIEF30-004]); the Python Core avoids the Blueprint's "rewrite in a new language" risk (context/02 §20) | Founder chooses one backend language |
| **BD-03** | **On-box identity provider: Kanidm v1.12.0** (MPL-2.0 [C-LIC-069]): passkeys/WebAuthn, OAuth2/OIDC provider, Unix integration with TPM-protected offline auth, two-node replication, aimed at "home labs, families, small businesses" through enterprise [C-BRIEF30-001]. The Core gateway is the **MCP authorization-server façade** in front of it (REC-W9-05), because neither Authentik nor a plain IdP gives MCP's audience binding today [C-W9-014]. Authentik stays in the founder's cloud tier; OIDC federation between them is year-1 work | 10 named Kanidm the single-box candidate; Authentik needs PostgreSQL + Redis, too heavy for a 4 GB box (measure in B6) | Founder picks Authentik on-box |
| **BD-04** | **Core datastore: PostgreSQL** (one instance per box, StatefulSet on the Retain class, version pinned at B0), per Blueprint OS-D09 (context/02 §9 table list) | The ledger needs transactional outbox and idempotency; Blueprint already specifies the tables | — |
| **BD-05** | **Image builder:** a **Containerfile-defined rootfs** (built with `docker buildx`, exported as a tar per arch) plus **OneMind's own assembler** (`os/assemble/`) using the exact tools the six passing labs used: `sgdisk`, `mkfs.*`, `ukify`/`sbsign`, `rauc bundle`, and `mmdebstrap` only for the build chroot [lab `rauc-1152/scripts/build.sh`, `secureboot-rauc/scripts/build.sh`]. **mkosi** (the W18 runner-up, measured in DC-20 [C-LAB-minimal-image-dc20-016]) is the named fallback if the assembler exceeds ~1,500 lines or when the EROFS + dm-verity root work starts. **Rugix Bakery is not used**: 28 chose it because it "pairs with the Rugix updater" [28 §7], which 01 replaced, and no lab built a RAUC image with it | Lab-proven path; one toolchain for x86, arm64 and Pi; the Containerfile keeps the umbrelOS pattern and the `FROM ubuntu:26.04` leg | Founder prefers mkosi from day one |
| **BD-06** | Root filesystem v0 = **ext4, mounted read-only** in each slot (what every RAUC lab ran). EROFS + dm-verity root is a tracked follow-up with its own pre-registered spike (raises RAUC's C3 to anchor 5, 01 §3.2) | Lab-proven; changes nothing in the layout | — |
| **BD-07** | **Pi 5 layout = the F-PI5 kit's layout** with 04 §11's labels: `onemind-autoboot` 64 MiB FAT (`autoboot.txt` + slot markers), `onemind-boot-a/b` 512 MiB FAT, `onemind-system-a/b` 8 GiB, `onemind-data` rest; NVMe or USB SSD only for platform nodes | The kit passed a desk pre-flight on the real Raspberry Pi OS tree and found a backend bug [C-LAB-rauc-1152-017]; 04's 256 MiB/6 GiB were estimates | LT-PI5-01 result |
| **BD-08** | x86: CI builds **both** route variants from one layout (`efi` + UKI and GRUB fallback) until G2; the default shipped route follows Z-18's recommendation (a) only if the combined spike B4.4 passes | 01 §4.2 item 1 makes the combined spike a precondition | Z-18 |
| **BD-09** | Update policy implemented with **"security channel auto-installs by default; feature channel manual; opt-out, postpone and a maintenance window; mission-safe reboot for robots and field kits"** as a setting with that default (Z-02 recommendation (a), SEC-05) | CRA expects automatic security updates by default [C-W6-008]; rollback makes it safe | Z-02 = (b) flips the default only |
| **BD-10** | Market controller: OneMind's own Go controller reconciling a `OneMindApp` custom resource into a Helm release through the **Helm v4.3.1** SDK [C-LIC-033]; **no Argo CD on boxes in v0** (05 §4 leaves Argo CD Core vs Flux to a RAM lab; one owner per resource) | Portable to any Kubernetes (REC-DEC-10 portability guard) | Lab result on Argo CD Core RAM |
| **BD-11** | k3s datastore = **SQLite on every box** in v0; embedded etcd only after LT-PI5-04 passes (REC-DEC-38) | 01 §4.6 | LT-PI5-04 |
| **BD-12** | Networking: Flannel, ServiceLB on single boxes, Traefik v3.7.18 with Gateway API v1.7.0 [C-LIC-033]; remote access = a Tailscale/Headscale client **app, off by default** (REC-W11-12) | 05 §6 | — |
| **BD-13** | **Task system: GitHub Issues + one GitHub Project** on `onemindos/ONEMINDOS`, one issue per deliverable ID (D-B*.x), labels `ws:B1…B13`, `gate:G0…G7`, `kit:LT-*`, `founder-decision` (the open "which task system?" item, 26 §C) | It is where the code, CI and PR already live; no new account | Founder names another tracker |
| **BD-14** | **One manifest schema** reconciling 13 §5.1 and 29 §6: `apiVersion: onemind.io/v1alpha1`, `kind:` one of `App, Widget, Shell, Adapter, Skill, Automation, Profile`; fields from both (requirements, entrances, storage, backup, permissions/grants, host, bus, capabilities with `effect` read/write/destructive/actuate, integrations with `aiPolicy`, widgets, alerts, compat, signing, offline). Published as JSON Schema in `sdk/schema/` | 13 and 29 disagree on the envelope; one schema avoids two validators | — |
| **BD-15** | Third-party **host** plugins (E3/E4 by non-OneMind publishers) are **disabled in v0**; OneMind-built host extensions only, until LT-VM-01's security variant passes **and** Z-22 is answered | 01 §4.8 conditions DC-16 on T-W19-01; 20 §4 G1 | Z-22 |
| **BD-16** | Agent runtime sandbox: kubernetes-sigs agent-sandbox + gVisor `RuntimeClass` (REC-W9-08) for agent-run code; Kata only where KVM exists | 10 | — |
| **BD-17** | Local inference in v0: none shipped by default; Ollama/llama.cpp as Market apps only (REC-W9-09); the gateway's model router supports a local and a remote provider behind one interface | Keeps the 4 GB footprint honest | — |
| **BD-18** | Handbook and build ADRs go in a new top-level `handbook/`; **`docs/` and `context/` are not edited** (research rule kept) | Separates founder-owned docs from build output | Founder |

### 4.3 Standing triggers you watch (from 20 §4.1; you only report, never act alone)

RAUC newer than v1.15.2 (rebuild and re-run the battery within 30 days, REC-DEC-31) · k3s patch releases on the v1.37 line · systemd fixes for sysext signature bypasses landing in Debian's 257 line [C-REF-W19-security-006] · any founder answer to Z-01, Z-03, Z-18, Z-22. Record each check in `handbook/watch.md` with the date.

---

## 5. Repository layout

Create exactly this tree (empty directories get a `README.md` saying what goes there and which deliverable fills it).

```
<repo>/
├── research-output/            # research (read-only for you, except evidence/claims/BUILD.csv and evidence/lab/founder-hardware/)
├── docs/  context/  research/  # founder and research inputs (never edited)
├── handbook/                   # build docs for Zeus: ADRs (adr/), versions.md, findings.md, hygiene.md, trace.md,
│                               #   keys/ (ceremony placeholders), watch.md, outreach-drafts.md, release-notes/
├── os/
│   ├── versions.lock.yaml      # every pin (version + digest/SHA + source URL)
│   ├── rootfs/                 # Containerfile + layers/ (base, systemd, k3s, rauc, gate, onemindd, extensions, kanidm-client…)
│   │   ├── debian.args  ubuntu.args          # FROM debian:trixie@sha256… / ubuntu:26.04@sha256… + snapshot timestamp
│   ├── boards/                 # one folder per board: x86_64-efi, arm64-efi, rpi5, jetson-orin, vm
│   │   └── <board>/board.yaml  layout.yaml  boot/   # partition table, boot files, kernel package, RAUC backend
│   ├── assemble/               # assemble.sh (disk image), mkbundle.sh (RAUC bundle), convert.sh (qcow2/vhdx/vmdk/vdi/ova)
│   ├── rauc/                   # build-rauc.sh (pinned tag), system.conf.in, backends/rpi-tryboot-ab.sh, handlers/
│   ├── gate/                   # onemind-health-gate, onemind-k3s-check, systemd units, defaults
│   ├── kernel/                 # kernel-contract.yaml, check-contract.sh, nvidia/ (module build + sign), k2/ (dry-run route)
│   ├── extensions/             # merge wrapper, image policy, staging/quarantine logic tests
│   ├── secureboot/             # ukify config, enrolment scripts, SBAT policy; NO keys
│   └── release/                # TUF metadata layout, manifest schema, sign/verify scripts, channel config
├── platform/
│   ├── k3s/                    # config.yaml, psa.yaml, audit-policy.yaml, registries.yaml, bind-mounts.conf, sysctl.d
│   ├── charts/                 # core charts: onemind-core, postgres, kanidm, nats, dashboard, market-controller,
│   │                           #   capability-broker, backup-agent, onemind-probe (all pinned, all with limits)
│   └── profiles/               # lite, pro, tak-node, greenhouse, robot-agent (E8 bundles)
├── cmd/                        # Go mains: onemindd, onemind, onemind-probe, market-controller, capability-broker
├── internal/                   # Go packages (update, trust, extensions, probe, rescue, nats, k8s)
├── core/                       # Python/FastAPI: gateway (REST + MCP façade), policy, ledger, approvals, audit, sync,
│                               #   adapters/ (homeassistant, tak, knowledge, hermes, robot)
├── dashboard/                  # React + TypeScript SPA (Vite), widget host, PWA
├── sdk/                        # schema/onemind.app.schema.json, widget-sdk/, templates/ (plugin init), conformance/
├── apps/                       # Market seed: one folder per app (onemind.app.yaml + chart or chart ref + LICENSE row)
├── adapters/                   # out-of-Core plugins: sim-arm, so101, mqtt-bridge (each a kind: Adapter package)
├── test/
│   ├── qemu/                   # the battery runner (port of rauc-1152 run-tests.py) and board configs
│   ├── acceptance/             # A01…A24, one folder each: criteria.md (pre-registered), run script, results/
│   ├── e2e/  unit/  fixtures/  # HA demo fixture, TAK CoT fixtures, knowledge vault fixture, sim robot
├── lab-kits/                   # founder kits, one folder per LT-ID: README (22's criteria verbatim), scripts, expected output
├── .github/workflows/          # ci.yml, image.yml, battery.yml, release.yml, hygiene.yml, nightly.yml
├── Makefile                    # make dev | image BOARD=… | battery | hygiene | kit LT=… | release-dry-run
├── LICENSE (Apache-2.0)  NOTICE  CONTRIBUTING.md (DCO)  SECURITY.md (CVD policy, SEC-06)
```

---

## 6. Workstreams

Run B1 first (everything depends on it). Then B2–B7 (the OS spine) in parallel with B9 (Core). B8, B10–B12 follow their dependencies. B13 runs throughout: every deliverable lands with its test. Each deliverable has an ID (`D-Bn.x`) used in issues, commits and the trace table.

### B1 · Workbench, monorepo and CI/CD from the Mac (28 §9–§10; F-8)

| ID | Deliverable | Done when |
|---|---|---|
| D-B1.1 | Lima `onemind-dev` VM: `limactl start --name=onemind-dev --vm-type=vz --nested-virt --cpus=8 --memory=16 --disk=100 template:debian-13` (use `--mount-none` for any VM that runs third-party code; mount only the repo for daily work); inside: Docker CE + buildx (QEMU/Rosetta binfmt), Go, Python 3 + uv, Node LTS, `mmdebstrap`, `gdisk`, `dosfstools`, `e2fsprogs`, `squashfs-tools`, `systemd-ukify`, `sbsigntool`, `efitools`, `qemu-system-x86`, `qemu-system-arm`, `ovmf`, `qemu-efi-aarch64`, `swtpm`, `tpm2-tools`, k3s for the local loop. Script: `make workbench`; records versions | `make workbench` is idempotent; `handbook/workbench.md` explains each tool; `/dev/kvm` result recorded (LT-VM-09) |
| D-B1.2 | Monorepo skeleton (§5), Apache-2.0 headers, DCO check, `Makefile` targets, `os/versions.lock.yaml` seeded from `rauc-1152/versions.md` and C-LIC-033 | `make lint` passes |
| D-B1.3 | `make hygiene` and `.github/workflows/hygiene.yml` (rule 9) as a required check on every PR | A planted fake key and a planted `/Users/x` path in a throwaway branch are both caught, then removed |
| D-B1.4 | CI (`ci.yml`): lint, unit tests, `go vet`, `ruff`, `eslint`, `osv-scanner`, `govulncheck`, licence linter against `license-matrix.csv`; multi-arch app images by `docker buildx` on **native** runners (`ubuntu-24.04`, `ubuntu-24.04-arm`) [C-W18-057]; images pushed to `ghcr.io/onemindos/*` by digest | Green on the skeleton |
| D-B1.5 | `image.yml`: rootfs per leg and arch → kernel-contract check → assembled images per board → SBOM (syft) + CVE scan (grype or Trivy v0.76.2 [C-LIC-056]) with Debian tracker states as VEX (REC-DEC-41) → artifacts with sha256 | Produces x86_64-efi, arm64-efi, rpi5 and vm artifacts on every main push |
| D-B1.6 | `battery.yml`: the QEMU battery (B13) on every image change; nightly full run including the Ubuntu leg and Mender comparison | Runs and publishes verdict tables |
| D-B1.7 | `release.yml` (dry-run only in this session): signs with throwaway keys created in the job, produces TUF metadata and RAUC bundles, verifies them on a fresh VM, then destroys the keys; GitHub OIDC build provenance (SLSA Build L3 target, SEC-10) | Dry run passes; no key material leaves the job |
| D-B1.8 | Jetson job on an amd64 runner: rootfs layers on NVIDIA's L4T base (pinned BSP tarball sha256), producing a dev-kit flash package for `ROOTFS_AB=1` (NVIDIA tools need a Linux x86 host [C-W18-021]) | Artifact builds; marked `not for distribution (Z-01)` |

**CI/CD flow (implement as drawn; 28 §10 is the source):** Mac edits → Lima local loop (k3s, QEMU boot of a dev image) → PR → native-runner CI (lint, apps, rootfs, kernel contract, assemble, SBOM, QEMU battery) → `beta` channel signed by the online CI signer → founder hardware kits → `stable` (only after the founder's G-level results) → devices update at the owner's chosen time. Releases are never built by emulation on the Mac.

### B2 · Image build pipeline per board (01 §4.1–§4.4; P-7, F-14, D-002)

**One Containerfile, many boards.** `os/rootfs/Containerfile` takes `BASE` (`debian:trixie@sha256:…` or `ubuntu:26.04@sha256:…`) and `SNAPSHOT` (a `snapshot.debian.org` timestamp, or the Ubuntu equivalent) as build args. Layers: base system (systemd, udev, dbus, `systemd-logind` never masked, locale/timezone/first-boot policy so `systemd-firstboot` never blocks, `apparmor` [C-LAB-minimal-image-dc20-016, C-LAB-minimal-image-dc20-017, C-LAB-ubuntu-2604-leg-008]) → OneMind RAUC (from B4) → k3s binary + air-gap images (sha256-checked) → gate → `onemindd` → extension merge wrapper → board extras (kernel package, firmware, boot files) selected by `BOARD`. Name the initramfs generator explicitly (initramfs-tools on Debian; dracut is Ubuntu 26.04's default) [C-LAB-ubuntu-2604-leg-001].

| Board | Kernel (K1) | Boot route | Layout (labels are the contract; sizes per 01 §4.3 / BD-07) | Output |
|---|---|---|---|---|
| **x86_64-efi** (Lite, Pro, VM) | Debian `linux-image-amd64` from the snapshot | RAUC `efi` (UKI per slot) **and** RAUC GRUB fallback (BD-08) | `onemind-esp` 1 GiB FAT32 · `onemind-boot-a/b` 512 MiB **FAT32, ESP type** · `onemind-system-a/b` 10 GiB (≥ 10 % verity headroom) · `onemind-recovery` 1 GiB (empty) · `onemind-data` rest, **LUKS2** | raw `.img.xz`, USB installer ISO (also the rescue disk), RAUC bundles |
| **arm64-efi** (generic arm64, QEMU) | Debian `linux-image-arm64` | RAUC `efi`/GRUB on UEFI | same as x86 | raw image, bundles (LT-VM-08 runs here) |
| **rpi5** (Edge) | Raspberry Pi `linux-image-rpi-2712` from a pinned `archive.raspberrypi.com` snapshot + keyring; tested `rpi-eeprom` release, never `default` [C-REF-DC-longevity-002] | RAUC custom backend `rpi-tryboot-ab.sh` (port of the F-PI5 kit) | BD-07; `config.txt` sets `force_eeprom_read=0` and turns camera/display auto-detect off; overlays only from the boot slot (E10) [C-REF3-W19-technical-016] | flashable `.img.xz` for Raspberry Pi Imager, bundles; 16K-page cell in CI (01 §4.1) |
| **jetson-orin** (Robotics, dev kits only) | NVIDIA L4T (JetPack 7.2+) | NVIDIA rootfs A/B + image-based OTA, OneMind gate in NVIDIA's validation hook, `OTA_MAX_RETRY_COUNT` > 0 [C-W3-051] | NVIDIA `ROOTFS_AB=1` (`APP`, `APP_b`) + a OneMind data partition | flash package; never published (Z-01) |
| **vm** | as x86_64-efi | as x86_64-efi | x86 layout, 32 GiB virtual disk | qcow2, vhdx, vmdk, vdi, ova (HAOS ships all five; constraint-fit high) |

**k3s on a read-only root** (lab finding [C-LAB-rauc-k3s-gate-004]): bind-mount from `onemind-data`: `/etc/rancher/node`, `/var/lib/rancher`, `/var/lib/kubelet`, `/var/lib/cni`, `/var/log/pods`, `/var/log/containers`; kubeconfig written to `/run/k3s/k3s.yaml`; nothing of k3s's under `/etc` except its read-only `config.yaml` (confext needs `/etc`, B8).

**Install paths v0 (01 §4.4):** P2 flash image (Pi), P3 USB installer ISO (x86; writes the layout, enrols the db key in setup mode when the firmware allows (SB-7), creates EFI entries per SB-2, generates the LUKS recovery key and shows it once), P4 VM images, P6 developer install (`make dev` on a plain Debian 13 VM: same layers, **no OS rollback, labelled unsupported**, dashboard bound to localhost, its own update channel; REC-DEC-30). P1 preinstalled and P7 PXE are out of scope.

| ID | Deliverable | Done when |
|---|---|---|
| D-B2.1 | Containerfile + both legs + snapshot pinning; `make rootfs LEG=debian|ubuntu ARCH=amd64|arm64` | Rebuild on another day gives the same package list (`dpkg -l` diff empty) |
| D-B2.2 | Assembler for all five boards; `layout.yaml` per board validated against 01 §4.3 by a test | Images boot in QEMU (x86_64-efi, arm64-efi, vm); rpi5 image passes a loop-mount structure test and the F-PI5 desk pre-flight |
| D-B2.3 | USB installer ISO + rescue mode (shell, `rauc status`, gate log, restore entry) | Installs onto a blank QEMU disk and the result passes the battery |
| D-B2.4 | Developer install (P6) from the same layers | `make dev` on a Debian 13 Lima VM gives Core + dashboard; A01 partial (CI builds from the published recipe only) |
| D-B2.5 | Jetson dev-kit package (B1.8) + `lab-kits/LT-JET-01`, `LT-JET-02`, `LT-JET-03` | Kits reviewed against 22 §5 |

### B3 · Kernel configuration route (28 §6; 01 §3.5; F-7)

1. **Kernel contract** `os/kernel/kernel-contract.yaml`: cgroup v2 and namespaces; overlayfs, squashfs, erofs; dm-verity, dm-crypt; TPM 2.0; WireGuard; KVM (Pro); SocketCAN, USB serial (FTDI, CH34x, CP210x, CDC-ACM); V4L2/UVC; `CONFIG_MODULE_SIG` and `CONFIG_MODULE_SIG_FORCE`-equivalent behaviour via `module.sig_enforce=1`; AppArmor; BTF only if Cilium is enabled; PREEMPT_RT for the `robot-rt` profile. `check-contract.sh` reads each flavor's `/boot/config-*` from the built rootfs and fails the build on a missing option (HAOS fragments are the model [C-W18-008]).
2. **K1 per board** (table in B2). Kernel command line on every board: `module.sig_enforce=1 panic=10` plus the board's console; the gate depends on `panic=` and a watchdog.
3. **Newest-kernel cell:** CI also boots the newest kernel each product may run (trixie-backports for x86; HWE on the Ubuntu leg) and runs battery T1–T3, because a kernel interface change broke RAUC 1.13 on ≥ 6.19 [C-LAB-ubuntu-2604-leg-010] (REC-DEC-31).
4. **NVIDIA modules (Pro):** CI job builds `nvidia-open` for the exact image kernel, signs with the dev module key, packs a driver-pack sysext (E4), and never uses DKMS on the device; kernel security fixes are never held for a module build (7-day maximum GPU lag with an alert, REC-DEC-37). GPU smoke test = founder kit LT-GPU-01.
5. **K2 dry run (LT-VM-10, agent-runnable):** build kernel.org 6.18.y with a OneMind fragment set and the module key built in, for x86_64 and arm64, once a week for 4 weeks; record hours per bump in `handbook/k2-dry-run.md`. The research Mac lab built 6.18.62 in 101 s (x86_64) and 333 s (arm64) [C-W18-066].
6. **RT profile:** Debian `linux-image-rt-*` for x86/arm64; Pi RT and NVIDIA RT are kits (LT-PI5-08, LT-JET-04).

### B4 · Update and signing chain (01 §4.2–§4.3; R-1, R-3, M-2)

**B4.1 OneMind RAUC.** `os/rauc/build-rauc.sh` = port of `rauc-1152/scripts/build-rauc.sh`: clone tag `v1.15.2`, abort unless `HEAD` is `4fb7c798d6ae412344fb8f8d310d773046af3441`, meson with the options in `rauc-1152/versions.md`, build per arch against the base's own libraries, install into the rootfs; the Debian `rauc`/`rauc-service` packages must be absent (build fails otherwise). `system.conf`: `compatible=onemind-<board>`, `bootloader=efi|grub|custom`, `bundle-formats=verity`, `check-purpose=codesign-rauc` when signer certificates carry the codeSigning EKU [C-LAB-rauc-009], keyring = the OneMind RAUC CA, data directory on `onemind-data`. Handlers: **pre-install** writes the trial marker with the version read from the bundle's `manifest.raucm` (port `rauc-1152/scripts/guest/rauc-pre-install`) [C-LAB-rauc-k3s-gate-001, C-LAB-rauc-k3s-gate-002].

**B4.2 `onemindd` update service (Go).** Downloads releases (HTTPS or USB/LAN mirror), verifies TUF metadata (go-tuf), checks compatibility, free space and a **recent verified backup** (pre-update restic snapshot), asks the policy (BD-09) and the gateway (OS updates are approval-gated, REC-DEC-13), calls `rauc install`, schedules the reboot in the window, reports the **booted** slot and version (never "succeeded" from the installer's exit status alone; ZimaOS's field failure is the reason [C-TD-casaos-zimaos-044]), keeps a per-device `bad-releases` list (no auto-retry), and re-offers an abandoned trial on Pi 5 and the `efi` route with a bounded counter of 3 (REC-DEC-32). API on a local Unix socket plus `/v1/os/*` through the gateway; CLI `onemind update status|check|install|rollback|channel|window`.

**B4.3 One release contract (REC-DEC-06).** A release = TUF `targets` metadata listing, per board family, one RAUC bundle (or the Jetson payload), the driver packs built for that kernel, the SBOM, provenance and the release notes, each by sha256 and size. Channels `dev`, `beta`, `stable` (Blueprint: dev/pilot/stable; "pilot" = `beta`). Metadata expiry: `timestamp` 7 days, `snapshot` 30 days, `targets` 180 days, with an **offline grace** setting (default 90 days) after which a box refuses *new* releases but keeps running and accepts USB bundles signed under an unexpired root. Rollback protection: TUF version numbers plus the gate's refusal of an older OneMind version unless the owner forces a downgrade from the rescue console.

**B4.4 x86 boot routes and the combined spike.** Implement the `efi` route as in `secureboot-rauc/` (one UKI per slot on `onemind-boot-a/b`, EFI entries `OneMind-A/B`, recovery UKI only at the ESP's removable-media path) and the GRUB route as in `rauc-1152/` (3 tries). **Pre-register and run the combined spike** 01 §4.2 item 1 requires: `efi` backend + real k3s gate + emulated power cut during the trial boot, with the gate re-arming `BootNext` while a trial marker exists and the slot is not marked bad (the `efi` route gives one try per `BootNext` [C-LAB-secureboot-rauc-003]). Pass → BD-08 ships `efi`; fail → GRUB. Record the verdict as `C-BUILD-…` rows and in 20's G2 inputs.

**B4.5 Secure Boot rules SB-1…SB-10.** 01 uses SB-1…SB-6 but defines only SB-2…SB-5 (§4.3); this brief codifies the full set from 01's text. Rules marked *(01)* are 01 verbatim in substance; the others are 01 §4.2–§4.3 and REC-DEC-21/-25/-36 written as rules, flagged for the DEC owner in §15.

| Rule | Requirement | Where enforced | Test |
|---|---|---|---|
| **SB-1** Route | x86 boots RAUC's `efi` backend with one **signed UKI per slot** (kernel + initrd + command line in one signed file); no GRUB, shim or systemd-boot on that route; GRUB route keeps the same layout | `boards/x86_64-efi`, assembler | Battery under OVMF Secure Boot build (port `secureboot-rauc/`) |
| **SB-2** Boot entries *(01)* | Installer creates both EFI entries, puts only the active slot in `BootOrder`, removes firmware auto-entries for the OneMind disk, and `onemindd` re-checks every boot (RAUC's `efi` backend reports any slot in `BootOrder` as good, even an empty one; OVMF re-adds its own entries) [C-LAB-secureboot-rauc-019] | installer, `onemindd` boot check | battery T-SB2 |
| **SB-3** No slot-pinned fallback *(01)* | Only a **recovery UKI** at the ESP removable-media path; never a slot kernel there | assembler | structure test |
| **SB-4** Anti-downgrade *(01)* | Gate refuses `mark-good` when the kernel's `onemind.version` (UKI command line) ≠ the root's `ONEMIND_VERSION` in `/usr/lib/os-release`; security releases bump the SBAT generation or rotate the db key [C-LAB-secureboot-rauc-018] | gate G7, release process | port of `secureboot-rauc/scripts/e1-factory-fallback.py` must now **fail to commit** |
| **SB-5** Data key policy *(01)* | LUKS2 data bound to **PCR 7 + a signed PCR 11 policy**, built with a **systemd initrd** so the stub's policy signature is used natively [C-LAB-secureboot-rauc-005, C-LAB-secureboot-rauc-017]; every OneMind key or dbx change re-seals first (pcrlock-style prediction); recovery key generated at install and shown once | initrd, `onemindd` | battery T-SB5 (unlock on A, B, rollback; locked with Secure Boot off) |
| **SB-5b** Volume identity *(01 rev. 3)* | The initrd measures the unlocked volume's key into **PCR 15** and refuses to continue if the volume is not the expected one; no fall-back to a passphrase that then boots in the measured state [C-REF3-DC-security-009, C-REF3-DC-security-010] | initrd unit | QEMU volume-substitution test (pre-registered); founder LT-X86-06 |
| **SB-6** Module trust | `module.sig_enforce=1` on every board; modules signed by the OneMind module key (K-MOD). A UEFI db key cannot sign modules for a stock kernel [C-DEC-008…010], so the release that **enforces** Secure Boot with out-of-tree modules uses K2-hybrid (B3.5) unless LT-X86-12 finds a console-free route | kernel cmdline, CI signing | LT-VM-02, founder LT-X86-12 |
| **SB-7** Factory enrolment | OneMind's db key is enrolled on **every** x86 box from the first shipment, even with enforcement off, in setup mode, by the installer or the factory script; owner-run enrolment documented for BYO boxes [C-REF3-DC-longevity-008] | installer, `handbook/keys/enrolment.md` | QEMU setup-mode test; founder LT-X86-03/-07 |
| **SB-8** No irreversible fusing | Pi OTP and Jetson fuses are never touched by any OneMind script in v0 (Z-15 rule for the window) | code review rule + CI grep for `rpi-otp`, `odmfuse` | hygiene job |
| **SB-9** Owner takeover | A documented, tested procedure to replace OneMind's PK/KEK/db with the owner's ("sovereign mode"; SEC-03, Z-19) | `handbook/keys/owner-takeover.md` | QEMU test |
| **SB-10** Keys never in the repo or on the Mac | Lab and CI keys are created inside the VM or job and destroyed; production keys exist only after the ceremony (B4.6) | hygiene job, `release.yml` | planted-key test (D-B1.3) |

**B4.6 Key hierarchy and ceremony placeholders.** Write `handbook/keys/HIERARCHY.md` and `handbook/keys/CEREMONY.md`. You implement the verification side for every key and the signing scripts; you never create a production key.

| Key | Purpose | Custody (Z-04 default (a)) | v0 in this session |
|---|---|---|---|
| **K-ROOT** | TUF root role: certifies every other role; threshold **2-of-3** | Offline, three hardware tokens, `<CUSTODIAN-1>`, `<CUSTODIAN-2>`, `<CUSTODIAN-3>` | Dev root generated per CI run |
| **K-RAUC-CA** → **K-RAUC-SIGN** | X.509 CA in the RAUC keyring → short-lived bundle signer (EKU codeSigning) | CA offline; signer online in CI, validity `<SIGNER-VALIDITY-DAYS>` | Dev CA per run |
| **K-TUF-ONLINE** | `targets`/`snapshot`/`timestamp` roles for channels and the revocation feed | Online in CI (GitHub Environment with required reviewer) | Dev keys per run |
| **K-SB-PK / KEK / db** | x86 Secure Boot; db signs UKIs and the recovery UKI | PK and KEK offline; db per SBAT plan | Dev keys per run |
| **K-MOD** | Kernel modules and driver packs (SB-6) | HSM; signs only in CI | Dev key per run |
| **K-EXT** | Verity signatures for sysext/confext images (E3, E8) | Under K-ROOT, online in CI | Dev key per run |
| **K-STORE** | OneMind countersignature on plugins (E9); publisher signatures are Sigstore keyless from the publisher's CI (cosign v3.1.4 [C-BRIEF30-003]) | Under K-ROOT | Dev key per run |
| **K-JET** | Signs Jetson payloads; verified by OneMind's own verifier, because NVIDIA's OTA payload is unsigned [C-REF3-DC-security-001] | Under K-RAUC-CA family | Dev key per run |
| Device keys | restic device key, LUKS TPM slot, NATS leaf credentials, k3s token | Generated on the box; never leave it except inside the owner's encrypted recovery kit | Generated in tests |
| Owner keys | LUKS recovery key, restic owner key, optional escrow | Owner (printed/exported at setup; setup cannot finish without the emergency kit, W5-R4) | Test fixtures only |

`CEREMONY.md` contains only placeholders: `<CEREMONY-DATE>`, `<LOCATION>`, `<HSM-OR-TOKEN-MODEL>`, `<CUSTODIAN-1..3>`, `<WITNESS>`, `<ROOT-KEY-FINGERPRINTS>`, `<RAUC-CA-FINGERPRINT>`, `<SB-PK-FINGERPRINT>`, `<ESCROW-LOCATION>`, the script to run on an air-gapped machine (`os/release/ceremony.sh`, tested with dev keys in a VM with networking off), the CA rotation drill using HAOS's cross-signing method [C-W3-024], the revocation and compromised-key procedure, the root lifetime and offline rotation rehearsal for a box that skipped N updates, and the vendor-exit clause (REC-DEC-40). The founder fills it at the P6 ceremony (D-P6.1).

**B4.7 Jetson backend.** OneMind-owned payload verifier (same trust root), gate inside NVIDIA's validation hook, every gate failure turned into a **warm** reset (the retry counter advances only on warm reboots [C-REF3-DC-technical-001]), post-OTA version assertion, refuse to sign a payload whose layout flags differ from the device's recorded layout [C-REF-DC-cost-004]. Code and unit tests here; the run is LT-JET-01.

### B5 · Health gate specification (REC-DEC-07, -23; port of `rauc-1152/scripts/guest/`)

The gate is a POSIX-shell oneshot service `onemind-health-gate.service` with `After=local-fs.target rauc.service onemind-local-api.service`, **never** `After=k3s.service` (k3s is `Type=notify` with no start timeout), `RequiresMountsFor=/data`, `TimeoutStartSec=infinity`, plus `OnFailure=` reboot while in trial mode, a hardware watchdog (`RuntimeWatchdogSec=` in systemd, the board's watchdog driver in the initramfs) and `panic=10`.

**Modes** (from the trial marker `/data/onemind/pending` written by the pre-install handler): *trial* (marker names the booted slot) → run checks; *fell-back* (marker names the other slot) → mark the other slot bad, record the release in `bad-releases`, alert; *committed* (no marker) → `mark-good booted` (resets GRUB's counter) and exit.

**Checks, all on fresh signals** (each prints one reason line; any failure fails the round):

| # | Check | Pass condition |
|---|---|---|
| G1 | Kubeconfig of this boot | `/run/k3s/k3s.yaml` exists (written on this boot); API `/readyz` answers (necessary, never sufficient) |
| G2 | Kubelet | `http://localhost:10248/healthz` answers (use `localhost`, it may bind only `[::1]` [C-LAB-debian-rugix-025]) |
| G3 | Node heartbeat | Node `Ready=True` and its `lastHeartbeatTime` ≥ this boot's `btime` |
| G4 | Core pods | Every Running/Pending pod matching the core selectors (`kube-system k8s-app=kube-dns`, `kube-system app=local-path-provisioner`, `onemind-system app=onemind-core`, `onemind-system app=nats`) is Ready **and** its Ready transition time ≥ `btime`; at least one pod per selector. Market apps are never checked |
| G5 | Data partition | `/data` mounted `rw`; write + fsync + read-back of this boot's `boot_id` |
| G6 | Local API | `onemindd`'s local health endpoint returns this boot's `boot_id` |
| G7 | Version match (SB-4) | kernel `onemind.version` = root `ONEMIND_VERSION` = bundle version in the marker |
| G8 | Extensions | Every enabled sysext/confext and the driver pack re-merged for this `SYSEXT_LEVEL`; a plugin whose `compat` excludes the new level was reported before install (29 §10) |

**Decision:** 3 consecutive passing rounds 10 s apart → `rauc status mark-good booted`, delete the marker, log `RESULT mark-good`. Deadline (default **300 s** in emulation; on hardware set to about 3× the good-commit time measured by LT-X86-01) → `mark-bad booted`, log, reboot (old slot boots). A naive mode exists **only** in the test harness (T10 reproduces the stale-Ready trap [C-LAB-rauc-k3s-gate-008]); a build that ships it fails CI. Jetson uses the same checks in NVIDIA's hook with warm reset (B4.7).

**k3s minor guard (01 §4.2 item 6):** on boot, if the datastore was last written by a newer k3s minor than the slot's binary, k3s is not started; the rescue console offers the version-bound snapshot restore (LT-VM-04).

### B6 · k3s platform and hardening (01 §4.5; REC-DEC-09, -22; SEC-08)

`platform/k3s/config.yaml` (read-only, in the image) sets at least: `write-kubeconfig: /run/k3s/k3s.yaml`, `write-kubeconfig-mode: "0600"`, `secrets-encryption: true`, `protect-kernel-defaults: true` with the matching `sysctl.d` file, `node-name` from `/data/onemind/node-name` (fixed per box; local volumes are pinned to it [C-W5-019]), the audit policy and log rotation, the Pod Security admission configuration (default **Baseline**, **Restricted** for `market-*` namespaces, the narrow `robot-runtime` exception below), `embedded-registry: false` outside a household cluster [C-W4-052], and Traefik with the Gateway API provider. **Open the k3s CIS hardening guide for v1.37 and pin its URL in `handbook/versions.md` before writing these values; never copy them from memory** (rule 3).

| ID | Deliverable | Done when |
|---|---|---|
| D-B6.1 | Hardened config, bind-mounts, sysctls, audit policy, PSA config; default-deny NetworkPolicy per app namespace; AppArmor `RuntimeDefault` | `k3s check-config` passes in the image; kube-bench or the guide's checks recorded |
| D-B6.2 | Node roles: **server** profile (hub-class boxes and single-box Lite) and **agent-only** profile (robots, field kits) enrolled with short-lived credentials; no datastore or admin kubeconfig on agent nodes (Z-23 default) | Agent image contains no server state after join; test asserts it |
| D-B6.3 | **Footprint re-measure with the hardened profile** on a 4 GiB arm64 VM (port `k3s-footprint-restore/`); result decides nothing alone (the real decision is LT-PI5-03) | Numbers recorded next to the lab's +936 MiB idle [C-LAB-k3s-footprint-restore-007] |
| D-B6.4 | `robot-runtime` namespace class: only signed robot apps (E2) get `hostNetwork`, `hostIPC` and `SYS_NICE`; a dedicated policy exception, never a blanket PSS exemption [C-DEC-015, C-W7-033] | Unsigned app requesting it is refused (LT-VM-18 part) |
| D-B6.5 | NATS v2.15.2 [C-LIC-033] as a core chart: JetStream domain per box, leaf to a hub when configured, the locked subject grammar enforced by account permissions (E7), the `onemind.event.v1` envelope (context/02 §8) | Leaf outage test (port `w8-nats-leaf-buffer/`) passes 600/600 [C-W8-050] |
| D-B6.6 | `onemind-probe` (Go) + NFD + node labels `onemind.io/cap.*` and the NodeCapabilities document (11 §5.2); GFD only on NVIDIA nodes | Verdicts ✓/!/→/✗/? computed for the seed apps on the VM (A-8, N-3) |

### B7 · Storage and backups (01 §4.6; 06 W5-R1…R14)

| ID | Deliverable | Done when |
|---|---|---|
| D-B7.1 | StorageClass `onemind-local` (local-path, **reclaimPolicy Retain**, path on `onemind-data`), set as default; k3s's `local-path` class removed from default | Deleting a PVC keeps the data; test asserts it |
| D-B7.2 | Backup agent (Go, in `onemindd` or a core pod): restic v0.19.1 pinned per arch; repository with **three keys** (device, owner recovery, optional escrow); setup cannot finish without the emergency kit | Unit + e2e tests; the owner key alone restores |
| D-B7.3 | Single-box datastore procedure: online `sqlite3 … ".backup"`, `PRAGMA integrity_check` **gating** the backup, plus token, node password and encryption config, all inside the same restic snapshot; every snapshot records the exact k3s version; never a raw copy outside restic | Restore onto a fresh VM brings back all pods with identical data (port `k3s-footprint-restore/` T1–T6) [C-LAB-k3s-footprint-restore-011]; restore passes the original token explicitly [C-LAB-k3s-footprint-restore-012] |
| D-B7.4 | App hooks from the manifest `backup:` block (pre/post, sqlite, exclude, restore.post); app-consistent dumps for Postgres and Kanidm | Seed apps back up and restore in CI |
| D-B7.5 | Schedule (hourly GFS), 2× space check, off-site target to another OneMind box (append-only rest-server) or S3; **pre-update snapshot** called by B4.2 | Tests in VMs |
| D-B7.6 | Verified restores: daily `restic check --read-data-subset`, weekly scratch restore with app probes using **fresh** signals, "last verified restore" exposed to the dashboard; agents may trigger a backup and read status, **restore, key changes, destination changes and deletes need human approval** (W5-R13) | A17 on a fresh VM passes; LT-X86-14 kit written |
| D-B7.7 | Restore drill per shipped k3s version in CI (REC-DEC-28) | Nightly job |

### B8 · Day-one extension points E1–E10 (01 §4.8; 29; A-5, A-6, F-3…F-6)

| ID | Socket | v0 status | Build |
|---|---|---|---|
| **E1** | Market/app controller reading `onemind.app.yaml` | Frozen v1 | `market-controller` (BD-10): `OneMindApp` CR → Helm release; install, upgrade, rollback, uninstall (data kept by default); Compose importer `onemind app import` (kompose-style, through one OneMind library chart) |
| **E2** | Capability broker for host grants | Frozen v1 | Admission webhook: grants (devices, hostNetwork, hostIPC, GPU, RT) only for Verified-or-higher countersigned packages, shown to the owner, removable live; trust rating 1–8 (HA model) |
| **E3** | `systemd-sysext`/`systemd-confext` | Frozen v1 | See **extension enforcement** below |
| **E4** | Per-vendor signed driver packs | Frozen v1 | CI builds each vendor's modules for the exact kernel, signs with K-MOD, packs one sysext per vendor with a **depmod-at-merge** hook (Flatcar's fix [C-REF-W19-cost-010]); travels with the OS release; LT-VM-02 decides the fallback |
| **E5** | UI slot (sandboxed iframes, MCP Apps `ui://`) | v1-beta | Dashboard widget host: separate origin per widget, CSP from declared domains, no inherited credentials |
| **E6** | Capability registry + approval gateway | v1-beta | Core: manifest capabilities projected to REST, MCP tools, CLI verbs and Agent Skills (REC-W9-02); the approval rules themselves are **not** beta |
| **E7** | NATS grants inside the locked grammar | Frozen v1 | Per-plugin NATS account/user with publish/subscribe permissions from the manifest `bus:` block; validator rejects new top-level patterns and wildcard publish on `cmd.>` |
| **E8** | Profiles | v1-beta | Signed bundle = confext + sysexts + app set + defaults; `onemind profile apply <name>`; chosen at first boot |
| **E9** | Trust root, countersignature, digest pinning, revocation | Frozen v1 | TUF repository for plugins with an **expiring, rollback-protected revocation list**; revocation types `delist`, `disable`, `remove`, `disable-capability`; signed configuration objects; rollout-stage/hold field; permanent ID reservation; owner override logged; boxes install digests, never tags (REC-DEC-40) |
| **E10** | Boot-stage overlays | Frozen v1 | Device-tree overlays and early drivers only through the release pipeline (inside the RAUC bundle or boot slot), selected by profile; Pi `force_eeprom_read=0` and auto-detect off; per-kernel CI cell boots each certified overlay and checks its device nodes |

**Image reservations from release 1:** `SYSEXT_LEVEL=1.0` (the plugin API level) and `ONEMIND_VERSION` in `/usr/lib/os-release`; `/var/lib/onemind/extensions/{store,staging,quarantine}` and the confext write-routing directory on `onemind-data`; merge before k3s starts; the module-signing public key in the kernel command line policy; verity signing for extension images under the release root; a boot-slot area for overlays.

**Extension enforcement (the DC-16 condition).** systemd v257 accepts unsigned images by default, treats **any directory** in `/etc/extensions`, `/run/extensions` or `/var/lib/extensions` as an extension, and has no switch that refuses directories [C-BRIEF30-002, C-REF-W19-security-004]. So, as a OneMind design (to be proven by LT-VM-01, which you run in a VM):
1. Images live only in `/var/lib/onemind/extensions/store/`, never in a systemd search path on the data partition. `/var/lib/extensions` and `/var/lib/confexts` are masked by read-only empty bind mounts from the image.
2. At boot, a OneMind unit ordered **before** `systemd-sysext.service`/`systemd-confext.service` verifies each enabled image (signature under K-EXT, digest in the signed local index, `SYSEXT_LEVEL`, revocation list), and only then places a **symlink** to it in `/run/extensions` or `/run/confexts` (tmpfs, rebuilt every boot).
3. The same unit **fails closed** if any search directory (`/etc/extensions`, `/etc/confexts`, `/run/…`, `/var/lib/…`, `/usr/local/lib/…`) contains anything other than its own symlinks: it quarantines the item, skips the merge and raises an alert; the gate's G8 then fails a trial boot.
4. `systemd-sysext` and `systemd-confext` run with an explicit signed-only `--image-policy` (drop-in override), so a bypass of step 2 still meets the kernel-side policy.
5. Confext runs in a write-routing mode that cannot create files under `/etc/extensions` or `/etc/confexts`; a test plants one through the routed `/etc` and expects step 3 to catch it.
6. Validate every image in staging before it can be enabled, because one bad image stops every image from merging [C-REF-W19-cost-005].
LT-VM-01 must pass (unsigned image, plain directory, tampered image, a symlink to an unsigned image and a planted `/etc/extensions` entry all refused after reboot **and** a RAUC slot switch) before BD-15 can be lifted.

**SDK and CLI (29 §7):** `onemind plugin init|validate|dev|test|pack|publish|install|rollback|disable|remove` with the validator rules 1–10 of 29 §6 in one Go package used by the CLI, the store and the box. `.ompkg` offline package = OCI image layout tarball (chart, images by digest, extension images, SBOM, provenance, both signatures, latest revocation list). DX targets to measure and record: `init` → working widget on a dev box < 15 min; `validate` < 10 s.

### B9 · Core: the secure vertical slice (context/02 §3–§10; 10; M1)

**Authority rule (context/02 §4):** a UI, LLM, MCP descriptor or bus message only *requests*; the gateway authenticates the principal, validates resource and policy, checks current conditions and records the outcome; only the executor holds the upstream credential.

| ID | Deliverable | Done when |
|---|---|---|
| D-B9.1 | Kanidm on the box (BD-03): owner account with a passkey at first boot (mandatory owner credential, SEC-15), household roles (owner, adult, child, guest, operator) | First-boot flow works offline |
| D-B9.2 | Gateway (FastAPI): OIDC auth-code + PKCE for clients, same-origin cookie + CSRF for the web, identity headers stripped at ingress; **MCP authorization-server façade** (RFC 9728 metadata, RFC 8707 audience binding) in front of Kanidm; MCP target revision 2026-07-28 with a 2025-11-25 compatibility path (REC-W9-01, -05) | MCP conformance auth scenarios pass in CI |
| D-B9.3 | Principals: person, device, workload/plugin, **agent** (own identity; acts as user ∩ grant, never as the owner, REC-W9-04), automation, remote instance | A02: forged actor header and over-scoped request denied |
| D-B9.4 | Policy: `allow = authenticated ∧ active principal ∧ active device/workload ∧ grant ∧ resource scope ∧ context ∧ current approval when required` (context/02 §7) | Denial fixtures per rule |
| D-B9.5 | Action ledger in PostgreSQL: lifecycle `requested → awaiting_approval → accepted → dispatched → succeeded | failed | outcome_unknown | expired | cancelled`; idempotency key, expiry and expected version required on `POST /v1/actions`; transactional outbox to NATS; no unsafe redispatch after a timeout | A07, A08 |
| D-B9.6 | Approvals: bound to exact normalized parameters, resource, expiry and grant revision; delivered to the dashboard and the phone (Web Push / ntfy in v0; APNs relay design only, D-005); passkey-signed approval where the client supports it (REC-W9-06); **no self-approval by agents** | LT-VM-18 approval part |
| D-B9.7 | Audit: every gateway decision to an append-only, hash-chained JetStream stream (REC-W9-07); robot decisions kept ≥ 1 year (W7-R11) | Chain verification test |
| D-B9.8 | API routes of context/02 §4 (`/v1/instance`, `/v1/devices`, `/v1/plugins`, `/v1/capabilities`, `/v1/actions`, `/v1/sync`, `/v1/exports`) with the error set `permission_denied`, `stale_precondition`, `expired`, `offline_not_supported`, `conflict`, `outcome_unknown`; OpenAPI published (REC-W11-02) | Contract tests |
| D-B9.9 | Reference adapters at read scope: **Home Assistant** (REST + WebSocket; entity/service allowlists; one test light with desired-state action, TTL and observed confirmation), **TAK** (bounded CoT parser, XXE off, stable UID, stale time; observation and injection are separate permissions), **Knowledge** (Markdown vault; traversal and symlink escapes denied; hash-checked atomic writes), **Hermes/Legacy** (agent principal over NATS `svc.*` and `agents.*`, REC-W9-12) | A03 (Core works with model and agent stopped), A15 partial, A16 |
| D-B9.10 | Offline-first: device store, capture queue, cursors, conflict policy per record type (context/02 §10) | A09, A10 in VMs |
| D-B9.11 | Exports: versioned archive (manifest, checksums, JSONL, Markdown, plugin digests, policy relationships, restore instructions); tokens excluded; separate encrypted secrets package | Export restores into a clean instance |

**Test fixtures:** HA runs as a container with its built-in demo entities in the VM (no real devices); TAK fixtures are recorded CoT files; the knowledge vault is a generated fixture. No founder data ever enters fixtures.

### B10 · First apps and profiles (13 §3.4, §8.3; 09 §8; A-1, P-8)

1. **Wave 1 internal modules** (D-003, 13 §8.3): Home, Market, Alerts, Nodes, Family & Users, AI & Agents, Settings, Files, Vault: each a module of the dashboard **and** a Market package with its own `onemind.app.yaml` (scaffolds for every other APPS.md module: manifest stub + README, no code).
2. **Seed Market apps for v0** (each needs a `license-matrix.csv` row at a pinned SHA and class L1/L2 to be preinstallable): Home Assistant, Mosquitto, Node-RED, ESPHome, Zigbee2MQTT, ntfy, Uptime Kuma, Vaultwarden, OpenTAKServer, Actual Budget. If a row is missing (critic pass-2 N5 lists several), add it before packaging, or leave the app out.
3. **Profiles (E8):** `lite` (single x86 box), `tak-node` (Pi 5 8 GB: OpenTAKServer, NATS CoT bridge on `tak.cot.inject`/`tak.cot.>`, mesh gateway stub, chrony; manual updates in the field), `greenhouse` (Pi 5 4–8 GB: HA + ESPHome + Zigbee2MQTT + Mosquitto + NATS; ESPHome `reboot_timeout: 0s` and explicit `restore_mode` per relay [C-W8-029, C-W8-030]; setpoints with TTL on `cmd.greenhouse.{zone}.set_*`; AI may advisory-write within bounds only), `robot-agent` (k3s agent only, robot-runtime class). 09 §8 says "Rugix" in its profile tables; under 01 these run on RAUC.
4. **Fit test** T-W12-2: the Pro set alongside k3s on the 8 GiB arm64 VM; record `MemAvailable`.

### B11 · Dashboard MVP (12 REC-W11-01…20; UX-1, UX-4, P-1)

React + TypeScript SPA served by the gateway; one web shell for browser, PWA, and later Capacitor/Tauri shells. WCAG 2.2 AA from the first screen (axe-core in CI, 0 serious/critical). No global "Pro" toggle: role-gated views and a status reducer that hides Kubernetes words from household roles. Every dashboard action is a gateway capability an agent could call under the same rules (REC-W11-20).

| Screen | v0 content |
|---|---|
| Sign-in / first boot | Owner passkey, recovery-kit step that cannot be skipped, profile choice, LUKS recovery key shown once |
| Home | Fresh site status with source and observation time (never a cached value shown as live), customizable grid (importers later) |
| Approvals | Pending requests with exact parameters, requester (person vs agent), expiry; approve/deny |
| Market | Browse seed apps, capability verdict (✓/!/→/✗/?), grants and trust rating shown before install, install/remove/rollback |
| Nodes | Each node: role (server/agent/leaf), booted slot and version, update channel and window, last gate result, capabilities |
| Updates | Check, install (approval-gated), schedule, rollback, history with the **booted** slot |
| Backups | Last backup, last **verified** restore, destinations, emergency-kit status |
| Alerts | NATS `evt.*` + Alertmanager feed; Web Push and ntfy delivery |
| Agents | Agent principals, their grants, audit trail, revoke |
| Robots | Registry and the onboarding flow (B12), observe-only badge, safety settings, teleop widget slot (E5) |
| Settings | Users and roles, remote access app (off), keys and owner takeover docs, export |

**Rescue console** (REC-W11-04): served by `onemindd` on the host, outside k3s, LAN-only HTTPS with the per-box local CA (REC-W11-11), owner credential cached locally; shows health, gate log, slots, logs, update/rollback and restore, and works when k3s is down.

### B12 · Robot onboarding MVP ("connect a robot → use OneMind"; 29 §11; F-3)

**Scope v0:** one simulated arm in QEMU (agent-runnable) and one founder kit for a real SO-101-class arm (LT-PI5-13j). ROS 2 drivers are wrapped, not rewritten (W7-R8).

1. **Simulated arm** (`adapters/sim-arm`): a small program that speaks a simple serial protocol and simulates joints, limits and an e-stop line; attached to the VM through QEMU's emulated USB serial device. Read the VID:PID it presents with `lsusb` inside the VM and record it; do not assume it.
2. **Discovery:** udev event → `onemindd` publishes `evt.sys.device.{id}.attached` (grammar `evt.{domain}.{entity}.{event}`) with VID:PID, serial path and box capabilities.
3. **Match:** the Market controller looks up a signed, digest-pinned adapter in the local or offline `.ompkg` mirror by VID:PID and capability requirements.
4. **Consent:** dashboard and phone show "Arm found. Install adapter? Needs `/dev/onemind-robot0`, RT priority 50"; installing, connecting and granting are **three separate actions** (context/02 §3).
5. **Install:** E1 installs the adapter; E2 applies grants; E3 adds the udev rule sysext (OneMind-built only, BD-15).
6. **Observe-only start:** capability detection and a self-test with **no motion**; `tel.{robot-id}.arm.joint_state` flows; AI may read.
7. **Safety settings:** workspace limits, maximum speed, e-stop presence confirmed by the owner; until then every `actuate` capability is refused.
8. **Register:** E6 registers `robot.arm.move` (`effect: actuate`, `requiresApproval: true`, safety block); MCP tool and CLI verb projected; teleop widget in E5.
9. **Act:** an agent's `cmd.robot.{id}.move` request with TTL and idempotency key waits for human approval; a stale command after its TTL is refused (A12).
10. **Revoke:** revoking the adapter drives the arm to its safe state within its stop time, disables the plugin and audits it (T-W19-04 / LT-VM-18).

**Done when:** the full flow passes in a VM with no internet (offline `.ompkg`), including revoke-to-safe-state; `lab-kits/LT-PI5-13j/` contains the SO-101 run with 22's criteria.

### B13 · Test harness (QEMU in CI + founder hardware kits; 20 D-P1.5; 22)

1. **QEMU battery** `test/qemu/run-tests.py` (port of `rauc-1152/scripts/run-tests.py`, run with `python3 -I`), parameterised by board, leg, engine route and RAUC build. Tests, with criteria copied verbatim from the lab READMEs: T0 build, T1 first boot, T2 wrong-key refused, T3 good update commits after 3 fresh passes, T4 k3s broken → rollback, T5 stale-Ready trap, T6 kernel panic (3 tries on GRUB), T7 hang + watchdog, T8 power cut mid-write, T9 power cut in commit window/first trial boot, T10 naive gate (observation) / T10r, T11 verity-only policy, plus T-SB2, T-SB4, T-SB5, T-SB5b on the Secure Boot variant.
2. **CI matrix:** Debian x86_64-efi (GRUB and `efi`), Debian arm64-efi (LT-VM-08), Ubuntu 26.04 x86 leg, newest-kernel cell, Secure Boot variant (OVMF SB build + swtpm), Mender comparison nightly (LT-VM-05/-06 kits ported), k3s footprint/restore, sysext (LT-VM-01, -02), NATS leaf outage, restore drill per k3s version, LT-VM-04 cross-minor rollback, LT-VM-11 delta over a 64 kbit/s lossy link, LT-VM-14 air-gapped rebuild (release blocker).
3. **Acceptance tests** `test/acceptance/A01…A24/`: criteria pre-registered from context/02 §18; each result records date, commit, digests, versions, topology, negative cases and artifacts; results are `pass`, `fail`, `blocked` or `not-tested` (the Blueprint's performance fixture: 10 devices, 20 capabilities, 10 users, 50 events/s, p95 ≤ 300 ms for local metadata reads).
4. **Founder kits** `lab-kits/<LT-ID>/` for every hardware test 20 schedules in P1–P3 at least: LT-X86-00…04, -06, -12, -14; LT-PI5-01…04, -12; LT-JET-01…03; LT-GPU-01. Each kit: 22's criteria verbatim, prerequisite checks (target disk size checked twice), scripts, expected output, the result template (22 §2.5), and a redaction script. Results land in `research-output/evidence/lab/founder-hardware/<LT-ID>.md` and become `C-BUILD-…` rows.

---

## 7. Milestones, mapped to the 180-day plan and the acceptance tests

Weeks follow 20's calendar (Day 1 = 2026-11-16). The agent's own pace may be faster; the **order** and the **gates** are what matter. A milestone is done only when its tests are green in CI (or kit-ready where hardware is required).

| Milestone | 20 phase · gate | Blueprint | Workstreams and key deliverables | Acceptance tests advanced | Founder kits due |
|---|---|---|---|---|---|
| **BM0** Workbench + CI | P1 wk 1–2 · G0 | M0 | B1 all; repo skeleton; hygiene gate; RAUC build job; QEMU battery in CI on the lab images; M0 contract inventory template (`handbook/m0-reconcile.md`, filled by the founder from LT-CLU) | A01 partial | LT-X86-00, LT-VM-09 |
| **BM1** Image from the same layers | P1 wk 2–4 · G1 | M0 | B2.1–B2.4, B3.1–B3.3, B4.1–B4.3, B5, B6.1–B6.2, B7.1; dev install (P6) and image share layers; LT-VM-01, -05, -07, -08, -12 run in VMs | A18 (emulated), A17 (VM) | **LT-X86-01, LT-X86-02, LT-PI5-01**, LT-X86-08 |
| **BM2** Secure vertical slice | P2 wk 5–8 · G2, G3 | M1 | B9.1–B9.8, B9.9 (HA read + test light), B7.2–B7.6 (backups v0), B4.4 combined spike + SB-1…SB-10, B4.6 hierarchy docs, B2.5 + B4.7 Jetson v0, B6.3–B6.5; LT-VM-03, -04 in VMs | A02, A03, A07, A08, A17 (VM), A19 partial | LT-X86-03, -04, -06, -07, LT-PI5-02…04, -12, LT-JET-01…03 |
| **BM3** Extensions and Market | P3 wk 9–13 · G4 | M2 | B8 all (E1–E10 at the stated status), plugin SDK/CLI, four reference adapters at read scope, B3.4 NVIDIA module job, B3.5 K2 dry run, B6.4 robot-runtime; LT-VM-02, -10, -13, -18 | A04, A05, A06, A12, A16, A22 partial | LT-X86-12, -13, LT-GPU-01…02, LT-PI5-08, -09, LT-JET-04 |
| **BM4** Field node and profiles | P4 wk 14–17 · G5 | M3 | B10 profiles, B9.10 offline sync, NATS leaf buffering, PWA, TAK write path with denied injection, LT-VM-11, -15, -16, -17 in VMs | A09, A10, A11, A14, A15, A21 | LT-PI5-10, -13a–d, LT-X86-15 |
| **BM5** Owner alpha | P5 wk 18–21 · G6 | M4 | B2.3 installer ISO, first-boot onboarding, QR join for a second node (bootstrap token TTL ≤ 1 h, REC-W11-16), B7 whole-box restore, B6.6 capability detection, B10 seed apps + licence linter, B11 all screens, alert centre v0, rescue console | A01, A17, A19, A20, A22, A23 | LT-X86-14, -16, LT-PI5-05, LT-JET-06, -07 |
| **BM6** Appliance beta candidate | P6 wk 22–26 · G7 | M5 | B4.6 ceremony script dry run, release pipeline with TUF + SBOM + VEX, LT-VM-14 air-gapped rebuild, release-candidate re-run kits, B12 robot onboarding demo, second-operator rehearsal kit | A18, A24 (kit), A01 by a second person (kit) | Release-gate re-runs (D-P6.3), LT-PI5-13j, A24 |

**A13 (site partition) is deferred to year 1 with M6**, as 20 §6 states. **Cut rules:** apply 20 §8's cut list in its order; never cut the never-cut list (LT-X86-01/02/03/04/06, LT-PI5-01, LT-VM-01, LT-VM-04, LT-JET-01, LT-X86-14 and A17, A18, LT-VM-14, LT-VM-18, A24, the hygiene scan).

---

## 8. Deliverables (all in the repo)

| Path | Content |
|---|---|
| `os/`, `platform/`, `cmd/`, `internal/`, `core/`, `dashboard/`, `sdk/`, `apps/`, `adapters/` | The implementation per §5–§6 |
| `test/` | Battery, acceptance A01–A24, e2e, unit, fixtures |
| `lab-kits/` | Founder kits per LT-ID |
| `handbook/` | `README.md` (reading order for Zeus), `adr/` (one ADR per BD-xx and per gate decision), `versions.md`, `findings.md`, `hygiene.md`, `trace.md`, `keys/` (HIERARCHY, CEREMONY, enrolment, owner-takeover), `workbench.md`, `update-flow.md` (with a boot → update → gate → commit/rollback sequence diagram), `extensions.md`, `backups.md`, `security.md` (SB-1…SB-10, threat model summary), `robot-onboarding.md`, `k2-dry-run.md`, `watch.md`, `outreach-drafts.md`, `release-notes/` |
| `research-output/evidence/claims/BUILD.csv` + `research-output/evidence/sources/BUILD.md` (+ `BUILD/` saved pages with sha256) | New verified facts and lab results |
| `research-output/evidence/lab/founder-hardware/` | Empty except a README; filled by the founder |
| `.github/workflows/` | ci, image, battery, release (dry-run), hygiene, nightly |
| PR body | Status per milestone and workstream (done / kit-ready / partial / not started), gate inputs ready for each G, the §11 founder-decision table with the defaults applied, and links |

---

## 9. Git workflow

1. Work in `<repo>` (`onemindos/ONEMINDOS`). Branch **`build/core-v0`** from `main` (BD-01). If the branch or its PR already exists, add commits; never open a second PR.
2. If you lack push access, fork and open the PR from `yourfork:build/core-v0` to `onemindos/ONEMINDOS:main`.
3. Open a **draft PR** titled `Build: OneMind OS core v0` once BM0 is green. Push after every milestone and after any workstream deliverable that took more than a few hours.
4. Commits are signed off (`-s`, DCO), small and conventional. Never force-push; never rewrite history. If personal data slips into a pushed commit, mask it in a new commit and list it for the founder (a history rewrite is a founder decision, as in critic pass-2 N1).
5. `make hygiene` before **every** push (rule 9); CI's hygiene job is a required check.
6. Do not edit `docs/`, `context/`, `research/` or `research-output/` except `research-output/evidence/claims/BUILD.csv`, `research-output/evidence/sources/BUILD*` and `research-output/evidence/lab/founder-hardware/README.md`. If you prove a factual error in a research file, record it in `handbook/findings.md` with the evidence and a suggested fix for its owner.
7. Mark the PR *Ready for review* only when §10 is met.

---

## 10. Definition of done

- [ ] **BM0–BM6 deliverables exist**, each with a passing test in CI, or marked `kit-ready (blocked: founder-hardware)` with its kit, or explicitly listed as not done with the reason.
- [ ] The **QEMU battery** passes in CI for Debian x86_64-efi (GRUB route and `efi` route) and arm64-efi with OneMind's RAUC v1.15.2 and `bundle-formats=verity`; the naive-gate observation still reproduces the stale-Ready trap; the Ubuntu 26.04 leg passes the x86 battery.
- [ ] The **combined `efi` + k3s + power-cut spike** has a pre-registered verdict, and BD-08 is resolved accordingly.
- [ ] **SB-1…SB-10** each have an implementation and a test (QEMU) or a kit.
- [ ] **LT-VM-01** (extension security variant) has a verdict; BD-15 is applied accordingly.
- [ ] **Core slice:** A02, A03, A07, A08 pass in VMs; an agent's request to switch the HA demo light waits for human approval and runs only after it; the agent cannot approve itself.
- [ ] **Backups:** A17 passes on a fresh VM with the owner key only; the restore drill runs per k3s version.
- [ ] **E1–E10** exist at their stated status; a signed package installs, disables and updates without editing Core; tampered, wrong-digest, unknown-signer, bad-schema and stale-trust packages are refused (A04); a plugin update does not widen grants (A05); revocation rejects online calls within 60 s (A06).
- [ ] **Robot MVP:** the simulated-arm flow passes offline, including observe-only start, approval-gated motion, TTL refusal (A12) and revoke-to-safe-state (LT-VM-18).
- [ ] **Dashboard MVP:** every §6 B11 screen exists, axe-core reports 0 serious/critical issues, and the rescue console works with k3s stopped.
- [ ] **Release dry run:** TUF metadata, RAUC bundles, SBOM, VEX and provenance are produced and verified on a fresh VM with throwaway keys; the ceremony script runs in an offline VM with dev keys; **LT-VM-14** (air-gapped rebuild) passes or is the named release blocker.
- [ ] **Founder kits** exist for every hardware test in §7's "kits due" column through BM3, and for the never-cut list.
- [ ] `handbook/trace.md` maps every requirement ID listed in this file's header to code and tests; `handbook/versions.md` and `os/versions.lock.yaml` pin every component; every new component has a licence-matrix row.
- [ ] `make hygiene` is clean (or every hit is a reviewed false positive in `handbook/hygiene.md`) on the final commit and on `origin/main..HEAD`.
- [ ] The PR body holds the status table, the gate inputs and the §11 table; the PR is marked ready for review.

**If you cannot finish everything**, finish in this order and say exactly what remains in the PR body: (1) B1 + hygiene; (2) B2/B4/B5 on x86 with the battery green (the update path); (3) B7 restore; (4) B9 slice with approvals; (5) B6 hardening; (6) B8 E1/E2/E3/E9 enforcement and LT-VM-01; (7) the never-cut kits; (8) B11; (9) B12; (10) everything else. Never trade a safety test for breadth ("Do not weaken safety to hit a date", context/02 §17).

---

## 11. Founder-decision items: the defaults this build applies

Each default below is applied and recorded as an ADR in `handbook/adr/`. The founder can overrule any of them in one line; the code is arranged so each switch is a configuration or a single module.

| Item | Default applied | Where it bites |
|---|---|---|
| Z-01 Canonical/counsel | Not answered: **no Ubuntu-based artifact is published** (Ubuntu leg is CI-only; Jetson package is dev-kit only) | B1.8, B2 |
| Z-02 Security updates default | (a) auto security, manual feature, opt-out, window | BD-09 |
| Z-03 Update engine | (a) RAUC; engine-neutral layout kept | B4 |
| Z-04 Key custody | (a) offline root 2-of-3, placeholders only | B4.6 |
| Z-07 k3s floor | (a) server on ≥ 8 GB recommended, 4 GB + SSD as slim profile, leaf below; the 4 GB answer waits for LT-PI5-03 | B6 |
| Z-12 Default TAK server | OpenTAKServer on 4–8 GB profiles; TAK Server container only on 8 GB+ (not packaged in v0) | B10 |
| Z-13 Mirror meaning | Not built in v0 (warm standby is year 1) | — |
| Z-14 / Z-24 Platform-first and script sunset | (a): dev install from the same layers, unsupported, localhost-bound | B2 |
| Z-15 Fusing | Never in this window (SB-8) | B4.5 |
| Z-16 Jetson base | L4T for dev kits; meta-tegra is LT-JET-06 | B2.5 |
| Z-18 x86 boot route | (a) `efi` + UKI if the combined spike passes, else GRUB | BD-08 |
| Z-19 Secure Boot key model | (a) factory db enrolment; K2-hybrid only for the enforcing release | SB-6, SB-7 |
| Z-20 Fleet server | (a) OneMind release service (TUF + NATS); no Mender/hawkBit server | B4.3 |
| Z-21 Plugin contracts | (a) E5/E6/E8 v1-beta, rest frozen v1 | B8 |
| Z-22 Third-party host plugins | Off in v0 (BD-15) | B8 |
| Z-23 k3s on robots | (a) agent only | B6.2 |
| Z-25 FIPS | (a) not a P0 property; no FIPS work in v0 | — |
| Z-26 Desktop plugins | Out of scope for v0 | — |
| New: build-session items | BD-01…BD-18 (§4.2): repo, languages, **Kanidm**, PostgreSQL, **image builder**, ext4 root, Pi layout, Market controller without Argo CD, SQLite datastore, networking, **task system = GitHub Issues/Projects**, manifest envelope, agent sandbox, no default local model, `handbook/` location | §4.2 |
| New: does the second session run in parallel with the founder's P1 hardware work? | Yes; kits are ordered by the founder's 20 calendar | §7 |
| New: confirm weekly founder hours (20 §12) | 45 h/week assumed; the kit order assumes it | §7 |

---

## 12. What competitors do (constraint fit) for the build choices

| Choice in this brief | Home Assistant OS | umbrelOS | Olares | Others | Constraint fit with OneMind | What we take |
|---|---|---|---|---|---|---|
| Image build | Buildroot `make <board>`, genimage, img/qcow2/vmdk/ova [C-TD-home-assistant-os-003, C-TD-home-assistant-os-006] | Dockerfile-defined Debian rootfs + Rugix Bakery [C-W2-043, C-W18-015] | No OS image; script on Ubuntu/Debian [C-TD-olares-007] | ZimaOS: Buildroot + RAUC [C-TD-casaos-zimaos-008] | umbrelOS **high** (Debian, Pi + x86, small team); HAOS high for outputs | Container-defined rootfs (umbrelOS) + lab-proven assembler; HAOS's five VM formats |
| Update engine | RAUC, verity bundles, 3 tries [C-LAB-rauc-010] | Rugix (earlier Mender) [C-W3-040] | None | SteamOS: RAUC + casync [C-W18-044] | HAOS high for the engine; **no product combines Debian + RAUC + k3s** [C-DEC-013] | RAUC built from a tag (HAOS pins its own [C-LAB-ubuntu-2604-leg-009]); our labs are the proof |
| Testing updates | QEMU/OVMF + labgrid in Actions on every change [C-LABPLAN-001, C-LABPLAN-002] | 116 VM test files, emulated Pi 4 [C-LABPLAN-003] | — | balenaOS: QEMU per PR, AutoKit power rigs [C-LABPLAN-004, C-LABPLAN-005] | High | QEMU battery in CI + founder power-pull kits |
| Release signing | cosign over SHA256SUMS via GitHub OIDC [C-TD-home-assistant-os-015]; CA rotation by cross-signing [C-W3-024] | Stable channel ran a server-supplied script [C-W3-034] | No release signatures found [C-TD-olares-006] | Talos Image Factory publishes a cosign key [C-TD-talos-009] | HAOS high | Offline root + TUF + cosign provenance; never a server-supplied script |
| Health gate | Commits while unhealthy in some paths [C-W3-025] | Commits at daemon start [C-W3-036] | n/a | ZimaOS UI said "succeeded" on a panicking slot [C-TD-casaos-zimaos-044] | — (anti-patterns) | Fresh-signal gate; UI reports the booted slot |
| App platform | Docker Supervisor | Docker Compose | k3s + Helm/OAC, linter [C-TD-olares-028] | TrueNAS left k3s for Docker [C-DEC-007] | Olares high for k3s; TrueNAS medium (single-box) | k3s + Helm compiled from `onemind.app.yaml`; Compose importer; no k3s-only features in apps |
| Identity | HA's own auth | Single user + app gateway | Authelia + LLDAP [C-TD-olares-036] | Founder cloud: Authentik | Olares medium (8 GB floor) | Kanidm on-box (C-BRIEF30-001), gateway as MCP auth façade |
| Plugin trust | Quality scale, HACS force-uninstall [C-W19-015, C-W19-018] | Community stores follow mutable heads [C-W19-012] | Linter exempts its own images [C-TD-olares-030] | Flatcar per-vendor kmod sysexts [C-REF-W19-cost-010] | Flatcar medium (same mechanism) | Digest pinning, countersigning, expiring revocation, no self-exemption |

---

## 13. Glossary

| Term | Meaning |
|---|---|
| **A/B slots** | Two copies of the OS. Updates go into the copy that is not running; a failed copy is abandoned and the old one boots. |
| **RAUC** | The open-source A/B update engine Home Assistant OS uses. OneMind builds it from the official v1.15.2 source. |
| **Bundle (verity)** | A signed RAUC update file whose every block is hash-checked while it is read. |
| **Trial boot / commit** | The first boot of a new slot is a trial. Only the health gate commits it ("mark-good"); otherwise it rolls back. |
| **Fresh signal** | Evidence produced on this boot, not status left over in the database from an earlier boot. |
| **UKI** | Unified kernel image: one signed file with kernel, initrd and command line, checked by the firmware in one step. |
| **PCR** | A TPM register that records what booted. Disk keys can be sealed so they unlock only when the PCRs match. |
| **SBAT** | A generation number inside signed boot files; raising it lets the firmware refuse old signed files. |
| **TUF** | The Update Framework: signed metadata roles with expiry and version numbers that stop old or frozen updates from being replayed. |
| **sysext / confext** | systemd features that lay a signed add-on image over `/usr` or `/etc` on a read-only OS. |
| **Driver pack** | A sysext carrying kernel modules built and signed for one exact kernel. |
| **k3s server / agent** | The server holds the cluster database and every Secret; an agent only runs workloads. |
| **NATS leaf** | A small NATS server on a device that forwards to the main bus and stores messages while the link is down. |
| **Capability gateway** | The one place where every request (person, app, AI) is authenticated, checked against policy, approved if needed and audited. |
| **Action ledger** | The database record of every requested action and its outcome, with idempotency keys so nothing runs twice. |
| **Kit** | A folder of scripts and pass/fail rules that the founder runs on real hardware. |
| **Gate (G0–G7)** | A dated review in the 180-day plan where test results choose a pre-written branch. |
| **BD-xx** | A build default this brief chose where the research left a gap; the founder can override it. |
| **DCO** | Developer Certificate of Origin: a one-line sign-off on each commit. |
| **Provenance / SBOM / VEX** | Signed record of how an artifact was built / list of everything inside it / statement of which known CVEs actually affect it. |

---

## 14. Recommendations → requirement IDs

| ID | Recommendation (this brief) | Implements | Requirement IDs |
|---|---|---|---|
| REC-B30-01 | Build v0 in this repo with the §5 layout, pinned versions and the hygiene gate | BD-01, BD-18, rule 9 | F-9, M-6, D-001, RS-4 |
| REC-B30-02 | Container-defined rootfs + lab-proven assembler for x86, arm64, Pi 5 and VM; Jetson dev-kit package on NVIDIA's path | BD-05, B2, REC-DEC-01/-17/-18 | F-7, F-8, F-14, P-7, D-002, M-7 |
| REC-B30-03 | Kernel contract in CI, newest-kernel cell, NVIDIA module signing in CI, K2 dry run | B3, REC-DEC-12/-25/-31/-37 | F-7, R-3, N-8, M-8 |
| REC-B30-04 | OneMind RAUC v1.15.2, TUF release contract, `onemindd` update service, Jetson verifier | B4, REC-DEC-05/-06/-31/-32/-35 | R-1, R-3, M-2, M-7, U-4 |
| REC-B30-05 | Secure Boot rules SB-1…SB-10 and the key hierarchy with ceremony placeholders | B4.5–B4.6, REC-DEC-20/-21/-36 | R-1, M-2, U-4, M-8 |
| REC-B30-06 | Fresh-signal health gate G1–G8 | B5, REC-DEC-07/-23 | R-1, R-2, AI-4 |
| REC-B30-07 | Hardened k3s, node roles, NATS core, capability probe | B6, REC-DEC-09/-22 | N-9, N-3, N-6, F-14, U-4, A-8 |
| REC-B30-08 | Retain storage, restic three-key backups, online SQLite procedure, verified restores | B7, REC-DEC-11/-28 | R-2, M-2, UX-6, M-5 |
| REC-B30-09 | E1–E10 with the extension enforcement design and LT-VM-01 as its proof | B8, REC-DEC-24/-40 | A-5, A-6, F-3, F-4, F-5, AI-3, AI-5, U-4, P-8 |
| REC-B30-10 | Core slice: Kanidm, gateway as MCP auth façade, agent principals, approvals, ledger, audit, four adapters | B9, REC-DEC-13, REC-W9-01…07/-12 | AI-2, AI-3, AI-4, AI-5, AI-7, AI-9, U-1, U-4, M-2 |
| REC-B30-11 | Wave-1 modules, seed apps with licence rows, `tak-node` and `greenhouse` profiles | B10 | A-1, A-4, P-8, F-11, F-13, D-003 |
| REC-B30-12 | Dashboard MVP and rescue console | B11, REC-W11-01/-04/-05/-20 | UX-1, UX-4, P-1, P-2, R-2 |
| REC-B30-13 | Robot onboarding MVP with observe-only start, approval-gated motion and revoke-to-safe-state | B12, REC-W19-08 | F-3, N-4, N-7, N-10, AI-5, AI-7, M-7 |
| REC-B30-14 | QEMU battery in CI, A01–A24 harness, founder kits | B13, REC-DEC-34 | R-1, R-3, M-6, H-3, RS-6 |
| REC-B30-15 | Milestones BM0–BM6 on 20's gates; cut list honoured; never-cut list kept | §7 | M-6, F-9, R-1 |

---

## 15. Limits of this brief, and items for other owners

- **Written before any of it was built.** Every design here that no lab has run is labelled as such: the extension-enforcement steps (B8, proven only by LT-VM-01), the combined `efi` spike (B4.4), the PCR 15 check (SB-5b), the Jetson verifier (B4.7) and every hardware path. The brief makes each of them a pre-registered test, not an assumption.
- **SB-1 and SB-6…SB-10 are new names.** 01 references "SB-1…SB-6" (REC-DEC-20) but defines only SB-2…SB-5 in §4.3. This brief writes SB-1 and SB-6…SB-10 from 01's own text; **for the DEC owner:** adopt these names in 01 §4.3 or rename here.
- **28 §7 / REC-W18-7 (Rugix Bakery) is superseded by BD-05** for the reasons given; **for the W18 owner:** mark P0-7 accordingly, as 27 L4 already asked.
- **13 §5.1 and 29 §6 manifests are merged by BD-14**; **for the W12/W19 owners:** align the two examples to one envelope.
- **Kanidm's on-box footprint and its RFC 8707 support were not measured or checked** here; the gateway façade covers the protocol gap either way, and B6.3 measures the footprint. If Kanidm cannot fit the 4 GB slim profile with Core and Postgres, record it and propose an option in `handbook/findings.md`; do not switch IdP inside this session.
- **No VM in this research run exercised QEMU's emulated USB serial device for the robot flow**; B12 tells the agent to read the device identity rather than assume it.
- **Version pins are those current on 2026-11-11** [C-BRIEF30-003…007, C-LIC-033]; re-check at BM0 and record any newer patch release, but move a pinned component only through the standing-trigger process (§4.3).
- **Not legal advice.** CRA, licensing, trademark and export points are flagged for counsel (Z-05).
