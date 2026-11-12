# Sources: STEEL4-bootc (independent steelman for RHEL-family bootc as the core)

All accessed 2026-11-11 by the STEEL4-bootc agent. Claims are in `evidence/claims/STEEL4-bootc.csv` (C-STEEL4-bootc-001…025). Saved copies are in `sources/STEEL4-bootc/`, with hashes of the saved text in `SHA256SUMS` and hashes of the original HTML in `HTML-SHA256.txt`. Web pages were saved as HTML stripped to text; e-mail-shaped strings were masked (`<email-masked>`) before hashing. No Wayback snapshots were made (Wayback saves are denied in this environment), so each web page is an **ARCHIVE-GAP** covered by the saved text plus its hash. Code was read from shallow clones in `<lab-dir>/src/` at the pinned commits below.

| # | Source | Type | Claims | Archive / integrity |
|---|---|---|---|---|
| 1 | `AlmaLinux/bootc-images-rpi@bb8e83e6b898db63ca2b53a69343f067dfa4f28a`: `10-rpi/Containerfile`, `10-rpi/kernel.yaml`, `10-rpi/almalinux-raspberrypi.repo`; GitHub API (repo, contributors, releases, issues #19, #22) | PRIMARY (code) + PRIMARY-METADATA | 001, 002, 003 | Saved `almalinux-bootc-images-rpi-bb8e83e6-*`, `*-contributors-2026-11-11.json`, `*-releases-2026-11-11.json`, `*-issue22.json` |
| 2 | https://repo.almalinux.org/almalinux/10/raspberrypi/aarch64/os/Packages/ | PRIMARY (repo listing) | 004, 005 | Saved `alma10-raspberrypi-aarch64-Packages.txt` |
| 3 | `kfox1111/rpi-bootc-bootloader@82739f4c9ae6de9ce071014bff9dee16842fb978` `LICENSE` | PRIMARY (code) | 006 | Saved `rpi-bootc-bootloader-82739f4c-LICENSE.txt` |
| 4 | https://repo.almalinux.org/almalinux/10/RT/ | PRIMARY (repo listing) | 007 | Saved `alma10-rt-index.txt` |
| 5 | https://mirror.stream.centos.org/10-stream/RT/ (aarch64 and x86_64 `os/Packages/`) | PRIMARY (repo listing) | 008 | Saved `cs10-rt-index.txt`, `cs10-RT-aarch64-Packages.txt`, `cs10-RT-x86_64-Packages.txt` |
| 6 | https://www.centos.org/download/ | PRIMARY | 009 | Saved `centos-download.txt` |
| 7 | https://access.redhat.com/support/policy/updates/errata | PRIMARY (lifecycle policy) | 010 | Saved `rhel-lifecycle.txt` |
| 8 | https://www.redhat.com/en/about/press-releases/red-hat-nvidia-pair-enterprise-open-source-rack-scale-ai-faster-production-ready-innovation (2026-01-05) | PRIMARY (vendor announcement) | 011 | Saved `rh-press-rhel-for-nvidia.txt` |
| 9 | https://www.redhat.com/en/blog/red-hat-device-edge-now-available-run-nvidia-jetson-orin (2026-05-12) | PRIMARY (vendor announcement) | 012 | Saved `rh-blog-rhde-orin-ga.txt` |
| 10 | https://repo.download.nvidia.com/jetson/rhel-9.4/r36.3.1/ (`nvidia-l4t.repo`, `repodata/repomd.xml`, primary metadata); https://repo.download.nvidia.com/jetson/ index | PRIMARY (vendor repo metadata) | 013 | Saved `nvidia-l4t-rhel94-r3631.repo.txt`, `nvidia-jetson-rhel-9.4-r36.3.1-repomd.xml.txt`, `nvidia-jetson-rhel-9.4-r36.3.1-primary.xml.txt` |
| 11 | https://almalinux.org/p/the-almalinux-os-trademark-usage-policy/ ; https://almalinux.org/p/the-almalinux-os-licensing-policy/ | PRIMARY (policy) | 014 | Saved `alma-the-almalinux-os-*.txt` |
| 12 | https://almalinux.org/blog/future-of-almalinux/ (2023-07-13) | PRIMARY (project announcement) | 015 | Saved `alma-blog-future-2023.txt` |
| 13 | https://wiki.almalinux.org/release-notes/ | PRIMARY | 016 | Saved `alma-release-notes.txt` |
| 14 | `bootc-dev/bootc@27f1e64ea93639929ed0088cdc230c220dac0fe6` (after v1.17.4): `ADOPTERS.md`, `RELEASES.md`, `docs/src/bootc-composefs.7.md`, `bootc-boot-failure-detection.7.md`, `bootc-security.7.md`, `bootc-registries-and-offline.7.md`, `bootc-logically-bound-images.7.md`, `bootc-installation.7.md` | PRIMARY (code/docs, pinned) | 017–023, 025 | Saved `bootc-27f1e64e-*.txt` |
| 15 | GitHub API: `fedora-iot/greenboot-rs` issue #219 and PR #223 (and the 15 newest PRs), `fedora-iot/iot-distro` issue #82, `coreos/bootupd` PR #935 | PRIMARY-METADATA | 024 | Saved `issue-states-2026-11-11.jsonl` |

**Searched and not used as evidence:** web-search summaries about JetPack RPMs on RHEL (NVIDIA forum thread, RidgeRun wiki, personal blogs). They pointed to source 10, which was then opened directly. A Red Hat developer learning path on RHDE for Jetson returned HTTP 403 and is **UNVERIFIED (blocked)**; nothing rests on it.
Note: example private IPs in bootc-27f1e64e-bootc-installation.7.md.txt were masked as <vm-private-ip> before hashing.
