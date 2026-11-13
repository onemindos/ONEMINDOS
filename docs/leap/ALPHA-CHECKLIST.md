<!-- SPDX-License-Identifier: Apache-2.0 -->
# v0.1.0-alpha checklist (Wave G #9)

**Why this exists.** Alpha means a stranger can download an image, install it, get updates they can trust, and read how it works. This is the list of what that takes and where each item stands. Source: [NEXT-WAVE.md](NEXT-WAVE.md) item 9, [LANES.md](LANES.md) B8. Checked against `origin/main` on 2026-11-13. Anything I could not confirm in git is marked UNVERIFIED.

**Words used.** *Image*: the disk file you flash onto a board or USB stick. *TUF*: the signed-metadata scheme our updater uses so a fake update is rejected. *Root ceremony*: the one-time, offline step where the founder creates the signing keys. *LUKS2*: disk encryption.

Status key: **DONE** (merged, PR cited), **IN PROGRESS** (open PR), **BLOCKED ON FOUNDER** (decision named), **TODO** (nobody has started, not blocked).

## 1. Images

| Item | Status | Evidence |
|---|---|---|
| Installer, os/ patches, first-boot and QEMU boot battery, release job | IN PROGRESS | Open PR #66 (`feat/image-line`). Not on main yet. |
| Image build skeleton (os/ layout: rauc, rootfs, boards, assemble, gate) | DONE | `os/` exists on main; `image.yml` and `battery.yml` workflows exist. Which PR added it: UNVERIFIED. |
| Developer install script (`deploy/install.sh`, offline bundle) | DONE | #26 (deploy v0), #78 (deploy port). |
| LUKS2 disk encryption in the image | BLOCKED ON FOUNDER | F-61 / F-62 (LANES.md B1). F-62 has no entry in DECISIONS-NEEDED.md: UNVERIFIED what it asks. |
| Boot on real Raspberry Pi 5 / Jetson / x86 USB | BLOCKED ON FOUNDER | F-25 hardware order. QEMU in CI covers the software until then. |

## 2. Downloads page

| Item | Status | Evidence |
|---|---|---|
| Website (Astro + Starlight) builds in CI | DONE | `site/` and `.github/workflows/site.yml` on main. |
| A page that lists the image, checksums and signature | TODO | No downloads page exists in `site/src/pages/`. Cannot be filled until there is a signed image (section 3). |
| Hosting and domain | BLOCKED ON FOUNDER | F-5 (site.yml says it does not deploy until decided). |

## 3. Signed releases

| Item | Status | Evidence |
|---|---|---|
| Updater verifies TUF metadata (rollback and replay refused) | DONE | #15 (`internal/update`); replay test in commit 139f1cb. |
| Release job refuses unsigned images | IN PROGRESS | Part of #66. |
| Create the TUF root and signing secrets, publish a signed release | BLOCKED ON FOUNDER | F-27 (offline root ceremony). Nothing can be published as "signed" before this. |

## 4. Upgrade path

| Item | Status | Evidence |
|---|---|---|
| OS update service and `onemind update` CLI | DONE | #15. |
| Pre-update snapshot of `/data` | DONE (own restic settings) | `internal/update/engine.go`. Moving it onto the backup agent is open (a signed `backup.run` job, see PR #97). |
| App updates: health-gated, with rollback | DONE | #72 (app lifecycle). |
| A/B slots with automatic rollback on a real board | IN PROGRESS | RAUC config is in `os/rauc`; proof on the booted image is in #66. Real-board run waits on F-25. |
| First alpha-to-next upgrade tested end to end | TODO | Needs a signed release first (F-27). |

## 5. Docs

| Item | Status | Evidence |
|---|---|---|
| Install and first steps | DONE | `site/src/content/docs/docs/getting-started/` (install, first-steps, mac). First-run owner settings are in open PR #96. |
| Backups and restore | DONE | #86, #91; user pages `concepts/backups.md`, `guides/backups.md`. |
| Security basics | DONE | #71 threat model refresh; `concepts/security.md`. |
| Updates and rollback | DONE | `concepts/updates-and-rollback.md`, `guides/updates.md`. |
| Remote access (mesh, HTTPS, joining machines) | IN PROGRESS | Open PR #88 (WIP, waits on other PRs). Docs must describe what is built when it lands. |
| Docs say only what the code does | IN PROGRESS | Slop audit 2 landed (#81); open fix PRs keep trimming drift (for example #97). |

## Founder decisions that gate alpha

| Id | Decision | Blocks |
|---|---|---|
| F-27 | Run the offline TUF root ceremony, add signing secrets | Signed releases, upgrade test |
| F-25 | Order the hardware | Real-board boot and A/B proof |
| F-61 / F-62 | LUKS2 decisions | Encrypted image |
| F-5 | Website domain and hosting | Downloads page |
| F-32 | Headscale vs Tailscale for the mesh (default chosen: Headscale) | Final wording of remote-access docs and #88 |

## Next steps

1. Land #66 (image line), then #88 (mesh, HTTPS, join).
2. Founder: F-27 and F-25 unblock the most.
3. After F-27: build the downloads page and run the first signed-release upgrade test.
