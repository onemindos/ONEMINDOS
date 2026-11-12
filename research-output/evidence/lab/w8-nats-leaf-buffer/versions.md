# Pinned versions and hashes (W8-1 NATS leaf buffer)

Compiled 2026-11-11 by the HYG agent from `README.md` and `results.md`. Nothing was re-run. The run-time folder for this spike is no longer in `<lab-dir>`, so no run-time hash file exists.

| Item | Version / pin | Source |
|---|---|---|
| Host | Apple Silicon (M5 Max), Lima 2.3.0 (`vz`) | README, results |
| Lab VM | Lima `w8lab`, Debian 13 template (cloud image, aarch64), 2 vCPU / 2 GiB, loopback only, no host mounts | README |
| nats-server | v2.15.2 (2026-10-26), `nats-server-v2.15.2-linux-arm64.tar.gz` sha256 `bc2c788dcbf2849af749564e06a0d48c19bced851f2d68a2e21c54d078949b28` (matched release `SHA256SUMS`) | results.md |
| natscli | v0.5.1 (2026-10-26), `nats-0.5.1-linux-arm64.zip` sha256 `91c661f1173ee9bfe07514eef55a29d25ac7757a0868c179e825eba976073adc` (matched release `SHA256SUMS`) | results.md |
| Configs | `hub.conf`, `leaf.conf`, `tel_hub.json`, `run.sh` (hashed in `SHA256SUMS`) | this folder |

Gap: the guest kernel and image serial were not logged for this spike.
