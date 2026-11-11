# Sources: SCORE (scorecard citation pass, rev. 3)

All accessed 2026-11-11 by the SCORE agent. Claims are in `evidence/claims/SCORE.csv` (C-SCORE-001…032). Saved copies are in `sources/SCORE/`, with full hashes in `sources/SCORE/SHA256SUMS`. Web pages were saved as HTML stripped to text, and the sha256 of the original HTML is listed below. Example emails, private IPs and an example join token were masked in the saved copies before hashing. `gitleaks dir` on the folder found no leaks. No Wayback snapshots were made, because Wayback saves are denied in this environment. Each web page is therefore an **ARCHIVE-GAP** covered by the saved text plus its hash.

| # | Source | Type | Claims | Archive / integrity |
|---|---|---|---|---|
| 1 | `k0sproject/k0s@d65558bb77e540ba723067243235b0d0a396b187` (tag v1.37.2+k0s.1): `LICENSE`, `docs/releases.md`, `docs/backup.md`, `ADOPTERS.md`, `docs/commercial-support.md`, `docs/autopilot.md` | PRIMARY (code, pinned) | 001–005 | Saved `k0s-d65558bb-*.txt` |
| 2 | `canonical/microk8s@e254fda97340b3d307a993eac6baafda3fa409ff` (v1.36) `LICENSE` | PRIMARY (code) | 006 | Commit pin |
| 3 | https://canonical.com/microk8s/docs/upgrading | PRIMARY (vendor docs) | 007 | Saved `microk8s-docs-upgrading.txt`; HTML sha256 `eb2d14948baeefe17d5406ee2274bcd6f0baf0eb0f8af055419e7aa11b2d566c` |
| 4 | https://canonical.com/microk8s/docs/high-availability | PRIMARY | 008 | Saved (example IPs and token masked); HTML sha256 `0456afbb0892253d93c038ad116ded7e3229f555042a9ecc16e2c0c1b0dc4a0b` |
| 5 | `moby/moby@70efc0e31da3a115fc87574d1b786fa2b867c346` (docker-v29.9.3): `LICENSE`, `project/BRANCHES-AND-TAGS.md`; `docker/compose@5bceecf985347fcf6dd23029ce440b502a0d4301` (v5.7.0) `LICENSE` | PRIMARY (code) | 009, 010 | Saved `moby-70efc0e3-project-BRANCHES-AND-TAGS.md.txt` |
| 6 | https://docs.docker.com/engine/install/debian/ | PRIMARY | 011 | Saved; HTML sha256 `7017ab50b44ff95cda50fbba80c26ca828aee35d9e757e4003e93156c351e220` |
| 7 | `containers/podman@055de046937d29450f310fce0fe3071485d8bed9` (v6.2.0): `LICENSE`, `docs/source/markdown/podman-auto-update.1.md.in` L84–L86 | PRIMARY (code) | 012, 013 | Saved `podman-055de046-*.txt` |
| 8 | `flightctl/flightctl@f99870eafa95003d1511577efc1c6e8c4ce7d5d1` `README.md` L29–L57, L143 (W2-steelman S-09) | PRIMARY (code) | 014 | Saved `flightctl-f99870ea-README.md.txt` |
| 9 | `vmware-tanzu/velero@4ee1e79a7aed367fd9b767b8219ec65bd0c96892` (v1.18.4): `LICENSE`, release assets, `site/content/docs/main/support-process.md` L7 | PRIMARY | 015, 016 | Saved `velero-4ee1e79a-support-process.md.txt` |
| 10 | `longhorn/longhorn.wiki@2aea6d68f663ededc0b04b7d0a9d5b5fdf701197` `Release-Schedule-&-Support.md` | PRIMARY (project wiki, pinned) | 017 | Saved `longhorn-wiki-2aea6d68-*.txt` |
| 11 | `openzfs/zfs@71a9f9578616a90c3c14bb59629fb4d31bfd68d1` (zfs-2.4.4) `RELEASES.md` L24–L36 | PRIMARY | 018 | Saved `openzfs-71a9f957-RELEASES.md.txt` |
| 12 | `borgmatic-collective/borgmatic@2499e0d75c41ad15b0bfee8e73338922ad56b822` (2.2.0) GitHub licence API | PRIMARY-METADATA | 019 | Commit pin |
| 13 | `sbabic/swupdate@9000ecb52677da7d9676a61b729bab57dba99674` (2026.05.1) `doc/source/signed_images.rst` | PRIMARY | 020 | Saved (author email masked) |
| 14 | https://docs.mender.io/artifact-creation/standalone-deployment | PRIMARY | 021 | Saved; HTML sha256 `b4a54f19c3187688d2a4f62396d60a020936e1c42d47bb75f5626083afdbb26f` |
| 15 | `agherzan/meta-raspberrypi@72f7dfc6a6fea2490ad28ae9c660fb5728f87c40` `conf/machine/raspberrypi5.conf` | PRIMARY (code) | 022 | Commit pin |
| 16 | https://canonical.com/blog/bosch-rexroth-adopts-ubuntu-core-and-snaps-for-app-based-ctrlx-automation-platform (2020-02-19) | PRIMARY (vendor announcement) | 023 | Saved; HTML sha256 `7cfcbeca8cda0521a493f089d91a9598c1a685aa4ad3ed43ce9f18ae2f8fb43e` |
| 17 | https://apps.boschrexroth.com/microsites/ctrlx-automation/en/portfolio/ctrlx-os/ | PRIMARY (vendor product page) | 024 (partial) | Saved (service email masked); HTML sha256 `dba761133e1164f925b3a47d5d297b0f5624417491aedc871a6c19e5f7995214` |
| 18 | `AlmaLinux/bootc-images-rpi@bb8e83e6b898db63ca2b53a69343f067dfa4f28a` `README.md` L3–L44 (W2-steelman S-01) | PRIMARY (code) | 025 | Saved `almalinux-bootc-images-rpi-bb8e83e6-README.md.txt` |
| 19 | `kfox1111/rpi-bootc-bootloader@82739f4c9ae6de9ce071014bff9dee16842fb978` `README.md`; repo metadata (W2-steelman S-03) | PRIMARY (code) | 026 | Saved `rpi-bootc-bootloader-82739f4c-README.md.txt` |
| 20 | https://nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/ (2026-10-27, Fedora ARM/IoT lead's blog; W2-P0-2-technical "NEW") | SECONDARY (maintainer's personal blog) | 027 | Saved; HTML sha256 `de22d08d8c5137e53c7fa5e2548e7dbfabcc1b2f7ce3eac1af88a4ec14091164` |
| 21 | https://fedora.yaasharc.me/posts/bootc/fedora-bootc-rpi5-report/ | UNVERIFIED (blocked: HTTP 403 on 2026-11-11) | 028 | Not saved. **ARCHIVE-GAP** |
| 22 | https://repo.almalinux.org/almalinux/10/RT/x86_64/os/Packages/ | PRIMARY (repo listing) | 029 | Saved; HTML sha256 `92688eb23570db3f37371e0416af60672bf52f014d28e761249c3a4567d95258` |
| 23 | https://developer.download.nvidia.com/compute/cuda/repos/ (W2-steelman S-05) | PRIMARY (repo listing) | 030 | Saved; HTML sha256 `e065d0f19ec126283ff00b3b1e2bd5c69025a7e3b54b0875fb228f2e3665f8b8` |
| 24 | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html | PRIMARY | 031 | Saved; HTML sha256 `3d75171d2b3ad62bcab798c60b9b929a6a404c6ecfc636603430158404338d10` |
| 25 | `kopia/kopia@72ec08fd8edb86c67ed27099bf1b955e1f308ffa` (v0.23.1) GitHub licence API at the commit | PRIMARY | 032 | Commit pin |

**Opened but not used as evidence:** the Red Hat Edge Manager application docs (HTTP 403), a web search for a named MicroK8s appliance product (none found; this is why MicroK8s C4 is at the floor), and https://docs.docker.com/engine/release-notes/ (it states no Engine version lifecycle; the Moby branch file is used instead).

**#11b, W2 steelman sources not re-ledgered here:** S-02 (AlmaLinux `raspberrypi` kernel repo listing), S-04 (Red Hat KB 7140448, JetPack for RHEL bootc) and S-06 (CentOS Stream 10 RT compose) were not reopened. RHDE on Orin is already covered by C-W2-041, and the RHEL-family RT kernel by C-SCORE-029.
