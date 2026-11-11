# Sources · LAB-minimal-image-dc20 (DC-20 minimal image, distro vs from source)

Accessed 2026-11-11. Saved copies (text/JSON + sha256) are in [`LAB-minimal-image-dc20/`](LAB-minimal-image-dc20/) (`SHA256SUMS`). Code is cited at pinned commits.

| # | Source | Type | Saved copy | Supports |
|---|---|---|---|---|
| S1 | https://buildroot.org/download.html (release table: LTS 2025.02.x, EOL March 2028, 2025.02.19 of 2026-10-22; stable 2026.08.1, EOL December 2026; 2026.05.x, EOL September 2026) | PRIMARY | `buildroot-download-page.txt` | C-LAB-minimal-image-dc20-001 |
| S2 | Buildroot git tag `2025.02.19` = `4f924fd52841608d68ac3dcb83fccee8b8c90316` (https://gitlab.com/buildroot.org/buildroot): `configs/pc_x86_64_efi_defconfig` (kernel 6.1.24), `linux/linux.hash` (newest 6.12 entry 6.12.112), `utils/generate-cyclonedx` | PRIMARY (code) | shallow clone in `<lab-dir>`; files used are reproduced in the lab folder's `scripts/` | -002, -003 |
| S3 | Buildroot git tag `2026.02.3` = `679b9ead7620bbf193620d1ebf56f53c1764d37a`: `configs/pc_x86_64_efi_defconfig` (kernel 6.12.47) | PRIMARY (code) | shallow clone in `<lab-dir>` | -002 |
| S4 | https://www.kernel.org/releases.json (longterm 6.12.117 released 2026-11-10; 6.18.63 longterm) | PRIMARY-METADATA | `kernel-org-releases.json` | -004 |
| S5 | https://sources.debian.org/api/src/mkosi/ (trixie 25.3-7; forky/sid 27.1-1) | PRIMARY-METADATA | `debian-sources-mkosi.json` | -005 |
| S6 | https://update.k3s.io/v1-release/channels (stable = v1.37.2+k3s1) and https://github.com/k3s-io/k3s/releases/tag/v1.37.2%2Bk3s1 (published 2026-11-03); binary sha256 checked against `sha256sum-amd64.txt` | PRIMARY-METADATA | `k3s-release-channels.json`, `k3s-release.json` | -006 |
| S7 | https://github.com/anchore/syft/releases/tag/v1.57.1 and https://github.com/anchore/grype/releases/tag/v0.121.3 (published 2026-11-09); tarballs checked against the release `checksums.txt` | PRIMARY-METADATA | `syft-release.json`, `grype-release.json` | -007 |
| S8 | Lab observations (build logs, `size.txt`, syft/grype JSON summaries, serial logs) | PRIMARY (own measurement) | `evidence/lab/minimal-image-dc20/` | -008 onwards |
