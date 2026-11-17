<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 04: before the big build — code check, process fixes, seeing the OS, and open decisions

**For:** Zeus · **Date:** 2026-11-14
**Status:** founder-requested review. It adds no decision and reopens none. Where something needs a founder call, it says so.
**Builds on:** the Foundation Report rev 4 (`research-output/report/chapters/10-competitors.md` and `14-decisions.md`), [`research-output/26-OPEN-QUESTIONS-FOR-ZEUS.md`](../../../research-output/26-OPEN-QUESTIONS-FOR-ZEUS.md), [`docs/strategy/roadmap-pillars.md`](../../strategy/roadmap-pillars.md), and a review of `main` on 2026-11-14 (code, CI history, branch settings).
**Feeds:** issues #226–#253 (the stabilise wave CI-01..CI-08 and DEV-SEE-01, plus 18 competitor gaps), already placed on the [OneMind OS Roadmap](https://github.com/orgs/onemindos/projects/2) and the pillar boards.

> ### In plain words
> The code is real, not "AI slop": almost no stubs, tests in every part, sane file sizes. The risk is the **process around it**: pull requests merge with no review, most test suites are not required, core tests take 90 minutes, and the status docs no longer match the code. Fix those first (about one short wave), then point Codex and a second Claude at the board. Opus reviews. Meanwhile you can see OneMind running on your Mac **today**.

---

## 1. What the code looks like (main, 2026-11-14)

| Part | Size (source lines) | Tests | Health |
|---|---|---|---|
| `core/` gateway (Python, FastAPI) | ~30k | ~980 | Good. 23 API routers, all wired. CI green 17 of 20 runs |
| `cmd/` + `internal/` daemon `onemindd` (Go) | ~17k | ~250 | Good. All pass except one test that fails only on macOS |
| `dashboard/` (web UI) | ~5k | ~100 | Medium. Several pages say "Coming soon" though the gateway already serves them (#141) |
| `ui/` design system | ~20k | ~240 + visual snapshots | Good. Backups and secrets screens are built but unused by the dashboard |
| `desktop/` (Tauri tray app) | ~4k | ~40 (Rust) | Early. No UI tests |
| `mobile/` | ~9k | ~200 | Medium |
| `sdk/` | ~23k (mostly generated) | ~90 | Generated from the API spec, but no client uses it |
| `os/` image build | ~5k | ~180 | Good design, but the image test battery is **red on main** (below) |

Two corrections found while checking: PR #88 (merged today) wired the mesh, HTTPS and join code, so `mesh.py` and `ca.py` are no longer orphaned. `proxy.py` is imported by the network router, but its header still says "NOT MOUNTED YET".

**Signs of slop to watch:** four hand-written API clients (dashboard, mobile, desktop, plus the generated SDK nobody uses) and two separate mock backends. When agents add an endpoint, they must edit three places, and types drift. That is CI-08 (#233).

## 2. Main is red right now, and why

- **The image battery test has failed since PR #123 merged** (data-disk recovery mode). The new test TD1 boots with the data disk detached and waits for the recovery screen, which never prints. It owns CI-01 (#226).
- **How it got in:** the merge queue only requires `dco`, `hygiene`, `lint` and `unit`. The image battery is not required, so the queue merged #123 while that test was red. I had queued it on your "merge when green". The lesson is the bottleneck below, not a one-off.
- **The nightly build has failed three nights running**, for older reasons: a harness bug that reads `version=2;` as `2;`, and the Ubuntu CI hedge always configuring Debian's package mirror. Both are in CI-01.

## 3. Fix these before the big multi-agent push (in order)

| # | Fix | Why it matters with many agents | Issue |
|---|---|---|---|
| 1 | Make main green | Every later PR is tested on a broken base | CI-01 #226 |
| 2 | Require each component's tests and the image battery (via a "gate" job that always reports) | Today red core, UI, mobile or image tests can merge | CI-02 #227 (needs you: a repo setting) |
| 3 | Review gate: Opus reviews every PR before it queues | All ~115 PRs since 11-12 merged with no recorded review; median PR is ~1,260 lines | CI-04 #229 |
| 4 | Agent engineering guide: commands per component, a "definition of done", PR template, CODEOWNERS | Agents follow what is written. Today AGENTS.md says why, not how | CI-04 #229 |
| 5 | Core CI from ~90 to <20 minutes | Slow CI is the speed limit for the whole team | CI-03 #228 |
| 6 | Local dev loop works on a Mac | Agents on Macs see false red tests today | CI-05 #230 |
| 7 | STATUS.md true again, then generated | Agents pick "todo" work that is already done | CI-07 #232 |
| 8 | Fewer shared hot files (app.py, actions.py, intake queue, generated SDK) | Parallel agents collide on the same lines | CI-06 #231 |

**The definition of done** (goes into AGENTS.md with CI-04): tests in the same PR; the feature is reachable from a route, the UI or the CLI, or the PR says why not; no new mock backend; under ~600 changed lines unless labelled `large`; one issue per PR; a `changes/` fragment.

### How to run the coders and the checker
- **Writers:** Codex and the second Claude account each take **one issue at a time** from the board, claim it with a draft PR titled with the ID, and work in their own branch or worktree. Give them different pillars, so they don't touch the same files: for example, one on Lane A (apps, gateway, dashboard) and one on Lane B (image, networking, updates).
- **Checker:** Opus (this account) runs a code review on each PR, checks it against the issue's "Done when" list, and only then queues it.
- **Cheap helpers:** use small, fast models for searching, inventories and log reading, and save the big model for design and review. This review used six parallel helpers that way.
- **Size of a wave:** finish one pillar's *Now* items before opening the next pillar. A board full of half-done PRs is the main slop pattern.

## 4. Seeing OneMind run (you have never seen it)

Easiest first. Every command comes from the repo's own docs.

| Step | What you see | Time | How |
|---|---|---|---|
| 1. Screen demo | Every dashboard screen with fake data | ~5 min | `cd ui && npm ci && npm run dev`, open `http://localhost:5173/#/home` (Node 22.6+) |
| 2. Real hub on the Mac | The real gateway, dashboard, message bus and two simulated machines (a Pi 5 and a Jetson). Apps don't really install (the "noop" executor). | ~45 min first time | Docker Desktop, then `cd deploy/compose && ./gen-tokens.sh && docker compose up -d --build`, open `http://127.0.0.1:8080` |
| 3. The whole OS in a Mac VM | The real image booting: A/B slots, first-run setup | 1–2 h | CI already builds `image-debian-arm64-efi`. Convert to qcow2 with `qemu-img` and boot in UTM (ARM64, UEFI). **Not yet tried by anyone**: DEV-SEE-01 #234 writes the guide |
| 4. Beelink | The real thing on real hardware | ~1 h | CI builds `installer-debian-x86_64`. Write it to a USB stick, boot with Secure Boot off, pick the disk and role `hub`, type `ERASE`. **Wipes the internal disk.** Then open `http://onemind.local:8080`. Lab kit LT-X86-01 |
| 5. DigitalOcean | A cloud hub | ~1 h, costs money | Upload `image-debian-vm-do` as a custom image. **Create a Cloud Firewall allowing only your IP before first boot**: the v0 gateway is plain HTTP. The kit's "no user data" step is wrong: the image needs a hub role (DEV-SEE-01) |

There is no published release yet: publishing waits on the signing ceremony (F-27, REL-01 #153). CI artifacts expire after 14 days. Until then, a nightly "dev build" pre-release, clearly labelled, would save digging. That is part of DEV-SEE-01.

**Order I'd use:** steps 1 and 2 this week on the Mac, so you learn the product. Step 4 on the Beelink when CI-01 is green, since that is the first-tier box (chapter 14: "Lite x86 mini PC first"). DigitalOcean last, and only with the firewall.

## 5. Desktop or headless?

- **OneMind is headless, like its competitors.** The box has no desktop. You use it from a browser, the phone app or the small desktop tray app (`desktop/`). umbrelOS ("no monitor, no keyboard"), Home Assistant OS, CasaOS/ZimaOS and Olares all work this way. umbrelOS's "desktop" in screenshots is its web page, with wallpaper and a dock.
- **A full desktop OS is a different product.** Z-32 recommends treating the desktop edition as a client and plugin pack on a normal laptop, not an Arch image of our own, because Omarchy ships about 32 releases a year.
- **A cheap middle step:** when someone plugs a monitor into the box, show the setup address, a QR code and, if the owner turns it on, a read-only dashboard. Today it shows a text console. That's UX-07 #242. It's a proposal, not in the report.

## 6. Internal apps, plugins, and what to copy from Omarchy

Omarchy (omarchy.org, MIT licence) gets four things right. Copy the patterns and write our own code:

1. **One manifest and one validator,** used both when publishing and when loading. OneMind already plans this (PLG-P2; Z-26 recommends Omarchy's manifest shape for desktop plugins).
2. **Submission by an issue form,** then automatic checks on an exact commit, then a maintainer's "verified". OneMind goes further: pin by digest and sandbox. Omarchy's plugins run unsandboxed, and its own marketplace says "not a security audit".
3. **"Try it first":** small Mac and Windows apps that download a roughly 2–3 GB VM image and run it, with Apple's hypervisor on Mac and QEMU on Windows. Home Assistant also runs a public web demo. That's BIZ-05 #243, after signed releases.
4. **A signed ISO with its fingerprint published,** plus a short installer (Omarchy says "answer five questions"). OneMind's installer is already a short text menu.

**Internal apps** are what the Blueprint calls the first vertical slice (chapter 14, REQ Q5): sign-in, site status, an approved Home Assistant toggle, offline sync and restore. The plugin contracts E1–E10 are the community path. Z-21 recommends freezing E1–E4, E7, E9 and E10 first.

## 7. Chapter 10 gaps: what competitors have that OneMind lacks

A full feature audit against about 30 products' teardowns found these missing on `main`. The 18 marked with an issue are now on the boards:

| Rank | Feature | Who has it | Issue |
|---|---|---|---|
| 1 | SMB network shares (+ Time Machine) | TrueNAS, Synology, Unraid, CasaOS | FILES-SHARE-01 #235 |
| 2 | One login for all apps (OIDC) | Cosmos, YunoHost, Cloudron | SEC-SSO-01 #236 |
| 3 | Share links for files and albums | Synology, Nextcloud | FILES-02 #237 |
| 4 | Your own domain with certificates | Cloudron, YunoHost, Coolify | NET-DOM-01 #238 |
| 5 | Network settings screen | FreedomBox, Synology, HA | NET-UI-01 #239 |
| 6 | Model manager ("fits this box") | HexOS, Olares | AIG-05 #240 |
| 7 | Snapshots and "previous versions" | TrueNAS, Synology | BAK-04 #241 |
| 8 | Try-it demo and VM | Home Assistant, Omarchy | BIZ-05 #243 |
| 9 | UPS clean shutdown | Synology, TrueNAS, Unraid | IMG-06 #244 |
| 10 | Cameras (NVR) | Synology, HA + Frigate | MKT-NVR-01 #245 |
| 11 | Local voice assistant | Home Assistant | AIG-06 #246 |
| 12 | Photo search | ZimaOS, Synology | AIG-07 #247 |
| 13 | Desktop file sync | Synology Drive, Nextcloud | UX-05 #248 |
| 14 | Energy view | Home Assistant | FLD-06 #249 |
| 15 | Matter/Thread | Home Assistant | FLD-07 #250 |
| 16 | Wake-on-LAN | Unraid, Synology | NET-02 #251 |
| 17 | Deploy from Git | Coolify, Dokploy | PLG-GIT-01 #252 |
| — | VMs, web terminal, Tor | Proxmox, Unraid; CasaOS; StartOS | **Your call** (DEC-CMP-01 #253): each touches a locked rule |

**The biggest gap is not a missing feature.** 40 of 61 catalogue apps are blocked, including Home Assistant, Nextcloud and Immich (UMB-P10 #147). Unblocking them adds more "all in one" than any row above.

Where OneMind is already ahead of everyone (chapter 10): the only health-gated update commit, signed OS and apps, an AI permission layer with approvals, and robots.

## 8. Chapter 14: what is still open

Of the 41 Z-decisions, **3 are settled**:
- **Z-38:** Debian 13 (D-007).
- **Z-28:** history purge; done, with GitHub's support purge still pending.
- **Z-03:** RAUC, decided by building it.

**Partly settled:** Z-10 (bootc in year 2; the Pi 5 test approval is open), Z-16 (L4T for dev kits) and Z-05 (Apache-2.0 core by D-001).

**Parked with robotics and TAK:** Z-12, Z-17 and part of Z-23.

**Note:** chapter 14's text still recommends Ubuntu for Z-38. D-007 wins; the report chapter wasn't updated.

**Decide soon (they block code or dates):**

| When | ID | Question | Recommendation in the report |
|---|---|---|---|
| This week | Z-04 / F-27 / REL-01 #153 | Signing keys and the offline ceremony | Offline root on a hardware key you hold; 2-of-3 signers; written succession plan |
| This week | F-25 / LAB-01 | Hardware order | Order now; the Pi soak must start by **2026-12-11** |
| Before G1 (2026-12-13) | Z-40 | Write four scoring rules before the next tests | Yes |
| Before G1 | Z-10 (W2-HW-3) | Approve the bootc Pi 5 test | Yes |
| Day 1 (2026-11-16) | Z-41 | Run the Ubuntu Secure Boot test | Was "yes". Under D-007 it only informs the Ubuntu CI hedge, so **you may drop it**. Your call |
| Before alpha | Z-02 | Security updates on by default | Yes, with opt-out, window, health gate and rollback |
| Before alpha | Z-19 / F-61 / F-62 / IMG-01 #148 | Secure Boot key model and disk encryption | Factory key; TPM2 where present, else ask at boot. **The F-61/F-62 numbers clash between documents** |
| Before alpha | Z-18 | x86 boot route | Signed UKIs if the power-cut test passes, else GRUB |
| Before alpha | Z-07 | k3s floor | k3s server ≥ 8 GB; 4 GB + SSD limited; smaller = leaf |
| Before alpha | Z-34 / F-32 | Remote access default | Headscale (self-hosted) default; Tailscale hosted opt-in |
| Before alpha | Z-13 | What "mirror" means | Warm standby; live HA only on 3+ nodes |

**Business and legal (can't skip, not blocking code):**
- Z-29: trademark.
- Z-30: company entity.
- Z-05 and Z-36: counsel on the open-core and CRA route.
- Z-37: vendor quotes.
- Z-06: support period.
- Z-31: first 100 customers.
- Z-01: Canonical, now needed only for Jetson and GPU boxes.

**Later:** Z-08, Z-09, Z-11, Z-14, Z-15, Z-20 to Z-22, Z-24 to Z-27, Z-32, Z-33, Z-35 and Z-39.

The repo's other open lists are LANES D3 to D14, D18 and D19, and the F-items in `docs/leap/DECISIONS-NEEDED.md`, which marks none of them as done.

**How to cross them off:** answer in chat or on the issue, and the decision goes into `docs/DECISIONS.md` (D-008 onward) or LANES.md with its date. The roadmap issues that wait on it lose their `needs-founder` label.

## 9. Domain: onemindos.org

**Buy it. It's worth about ten minutes and roughly $10–15 a year,** not more.
- **Why:** for an open-source OS, `.org` is where people expect the community (Omarchy uses `.org`). It's also the obvious address for someone to squat or use for phishing. It was unregistered when checked on 2026-11-14.
- **Use:** redirect it to `.com` for now. Later it can host the community, docs and plugin index, and `.com` sells boxes.
- **What matters more:** trademark clearance (Z-29) before spending on branding, and keeping `.com` on auto-renew.

## 10. Words used
- **CI (continuous integration):** the robot that builds and tests every change on GitHub.
- **Required check:** a CI test that must pass before GitHub lets a change into `main`.
- **Merge queue:** GitHub tests changes one after another against the latest `main` before merging them.
- **Battery:** OneMind's set of boot tests (T0 onward) that boot the image in a virtual machine and pull the plug at bad moments.
- **Headless:** no screen or keyboard on the box; you use it over the network.
- **qcow2:** a virtual-disk file format that UTM and QEMU use.
- **Mock / noop executor:** a fake backend that answers like the real one but changes nothing; good for demos, bad when every client has its own.
- **OIDC:** the standard behind "Sign in with…"; lets one account sign in to many apps.
- **SMB / Samba:** the Windows file-sharing protocol, and the Linux program that speaks it.
