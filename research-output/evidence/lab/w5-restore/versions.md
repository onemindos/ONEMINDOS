# Pinned versions and hashes (W5 k3s restore drill)

Compiled 2026-11-11 by the HYG agent from this folder's README and logs and the `SHA256SUMS` the spike wrote in `<lab-dir>/w5-restore/` at 2026-11-10T20:29-05:00 (after the drills). Nothing was re-run.

| Item | Version / pin | Source in this folder |
|---|---|---|
| Host | Apple M5 Max, macOS 27.2; Lima 2.3.0 (`vz`) | README |
| Lab VMs | two Lima VMs `w5a`, `w5b`, `template:debian-13`, image `debian-13-genericcloud-arm64-20261103-2651.qcow2` (Lima-pinned sha512 `5d3ecec4…adc0c2`), 2 vCPU / 4 GiB / 20 GiB | README, `logs/create-w5a.log` |
| Guest kernel | 6.12.115 (Debian 13 cloud) | `logs/` |
| k3s | v1.37.2+k3s1 (`f6973cb8`), binary fetched and checked by the installer against `sha256sum-arm64.txt` | `logs/a1.log` |
| k3s installer | `shared/install.sh`, sha256 `c2a2643dd7c259121a876d16538844c60928de3d38ae98f22f7b95a7ffcfab9d` (hashed before each use; unchanged in the repo) | `logs/a1.log`, `logs/b1.log` |
| restic | 0.18.0 (Debian 13 `apt`), go1.24.4 | `logs/` |
| sqlite3 | 3.46.1 (Debian 13) | `logs/` |

## Run-time hashes vs the committed copies

| File | sha256 at run time | Now | Same? |
|---|---|---|---|
| README.md | `b9f663fd8a842ca68be1a0dd50ec60d60a3e9dc1c890041b2be45a62134afe52` | same | yes |
| shared/install.sh | `c2a2643d…ab9d` | same | yes (upstream k3s installer, unmodified) |
| scripts/drill.sh | `c52abf87…b8b9` | `3f0212ad…7887` | no: host home path masked |
| shared/reverify.sh | `2710f766…f10d` | `1e284cde…d0d5` | no: host home path masked |
| logs/*.log | listed in the run-time file | differ | masked (host paths, VM addresses) |

The run-time folder also holds the restic repository, `state.db`, the k3s token and a restic password file. **They are not, and must not be, committed.** `shared/drill.sh` is a copy of `scripts/drill.sh`. `SHA256SUMS` here hashes the committed files as they are now.
