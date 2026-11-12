# Sources: LAB-debian-rugix (lab spike `evidence/lab/debian-rugix/`)

All accessed 2026-11-10/11 (UTC). Code and docs were read from shallow clones pinned to the commits below, so each permalink is immutable. That pinning is the archive for those sources. sha256 values are of the exact source files read.

| # | Source | Type | Pinned / archive | sha256 of file read |
|---|---|---|---|---|
| S1 | https://github.com/rugix/rugix (tag v1.4.0) | PRIMARY (code, tests, CHANGELOG) | commit `6d7fc277919b0048893c80d7e1e6e488ddc7b27b` | `tests/test_update_interruption.py`: 2490dc21de7c8f7b66d860f79d6063e1a10b40be345dce8b72868e9bf46b1efc |
| S2 | https://github.com/rugix/rugix-bakery (tag v0.9.4) | PRIMARY (code, core recipes, GRUB scripts) | commit `c43fdc11b88ee3ae8807f6b62802c85213c57be0` | `boot/grub/cfg/first.grub.cfg`: 07fe81444b5c6a5e7f484a4ceffa7f5eb42da1d5bb2b6a0b7c61efce42920499 |
| S3 | https://github.com/rugix/rugix-docs (source of rugix.org docs, Ctrl 1.4 and Bakery 0.9 trees) | PRIMARY (official docs) | commit `227f902790fe876b5a0d0df02e9c56e7cf1f6459` | `docs-ctrl/1.4/updates/system-updates/boot-flows.md`: 0e0f3a4b1a15c440e4385febc1a7e86c9cba2164a29e8ff96a64b00f06c0da10; `.../update-reliability.md`: cbbb4a2426109e3c680f3800a0d0a0c0302f4582b47535534dbefca34650fec3; `.../system-updates/index.mdx`: b9ea3617efc2a828156c724943f0b9d22e9cd38d77f45db621ffe26196b4ab31 |
| S4 | https://rugix.org/docs/ctrl/updates/system-updates/boot-flows/ | PRIMARY (rendered docs, same text as S3) | Wayback: https://web.archive.org/web/20261111013709/https://rugix.org/docs/ctrl/updates/system-updates/boot-flows/ | — |
| S5 | https://rugix.org/docs/ctrl/updates/system-updates/ | PRIMARY (rendered docs) | Wayback (existing): http://web.archive.org/web/20260807102425/https://rugix.org/docs/ctrl/updates/system-updates/ (older than Ctrl 1.4; S3 is authoritative) | — |
| S6 | https://github.com/rugix/rugix-testkit | PRIMARY (test layer used by upstream tests) | commit `f78ae636418d2fb4c58458d12d96fa22a4cb5b35` | — |
| S7 | GitHub release API: rugix/rugix v1.4.0, rugix/rugix-bakery v0.9.4, k3s-io/k3s v1.37.2+k3s1 | PRIMARY-METADATA | `gh api repos/<o>/<r>/releases` output, 2026-11-10 | — |
| S8 | https://update.k3s.io/v1-release/channels/stable (redirect target) | PRIMARY-METADATA | redirect observed 2026-11-10 → v1.37.2+k3s1 | — |
| S9 | https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1/ (k3s, k3s-arm64, air-gap tarballs, sha256sum-*.txt) | PRIMARY (artifacts, verified with the release's own sha256 files) | hashes in `evidence/lab/debian-rugix/versions.md` | see versions.md |
| S10 | https://deb.debian.org/debian/dists/trixie/Release | PRIMARY | Release header: Version 13.7, Date 2026-09-12 | — |
| S11 | https://snapshot.debian.org/archive/debian/20261109T000000Z/ | PRIMARY (package source for the images) | snapshot timestamp is itself the pin | — |
| S12 | Lima `template:debian-13` → https://cloud.debian.org/images/cloud/trixie/20261103-2651/debian-13-genericcloud-arm64-20261103-2651.qcow2 | PRIMARY (build VM image) | sha512 in `scripts/lima-builder.yaml` | — |
| S13 | Own lab logs, `evidence/lab/debian-rugix/logs/` | PRIMARY (first-hand observation) | in this repo | — |

**Not archived:** Wayback "save" requests for the update-reliability and system-updates pages were refused by this session's permission system (not by archive.org). Those pages are pinned through S3 (git commit plus file sha256) instead.
