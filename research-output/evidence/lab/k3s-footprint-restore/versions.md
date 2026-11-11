# Pinned versions and hashes (LAB-k3s-footprint-restore)

The authoritative table is README §"Pinned versions and hashes"; this file restates it and adds the download hashes re-computed on 2026-11-11 from the files still in `<lab-dir>/k3s-footprint-restore/dl/` (they match the README).

| Item | Version | sha256 |
|---|---|---|
| Host | Apple M5 Max, macOS 27.2, Lima 2.3.0 (`vz`) | — |
| Guest OS | Debian 13.7, kernel 6.12.115+deb13.1-cloud-arm64, 2 vCPU / 4 GiB / 20 GiB | — |
| k3s | v1.37.2+k3s1 (`f6973cb8`), `k3s-arm64` | `a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b` |
| k3s release checksum file | `sha256sum-arm64.txt` | `b017cfc151c92e30530c7d1830048ee5afabe53a4520ae513d584b7b2c2ee564` |
| k3s installer | `install.sh` at tag v1.37.2+k3s1 | `ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b` |
| restic | 0.19.1 `restic_0.19.1_linux_arm64` (unpacked) | `2fb45ac6f9071b6f20eb883953a188f9e7c7cb6bbe43c67a2e47ada4e85ee7f0` |
| restic archive | `restic_0.19.1_linux_arm64.bz2` (release `SHA256SUMS`) | `a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465` |
| Test images | `nginx:1.29-alpine`, `postgres:17-alpine`, `busybox:1.37` (digests in README) | — |

`SHA256SUMS` hashes the committed scripts and logs.

**Masking (2026-11-11, critic pass-3 P3-10):** `scripts/host-fetch.sh`, `host-restore.sh`, `host-source.sh` and `run-all.sh` no longer default `LAB` to a lab-host path; they now stop with an error unless `LAB` is set (`${LAB:?…}`, pointing at `<lab-dir>/k3s-footprint-restore`). `SHA256SUMS` carries the masked hashes; the original hashes and the unmasked originals (commit `414d60a`) are listed in `../PREREGISTRATION.md` §"Masking log". Nothing was re-run.
