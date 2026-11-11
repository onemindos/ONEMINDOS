# Pinned versions (LAB-w19-sysext)

Added 2026-11-11 by SYNC5 (critic N11). Nothing was re-run. Values come from the version block that `scripts/run.sh` prints at the start of the run (`logs/run-1.log` l. 2–6) and from the README's environment line. This file is not listed in `SHA256SUMS`.

| Item | Version / pin | From |
|---|---|---|
| Lab VM | Disposable Lima VM, `vz`, aarch64, Debian 13 "trixie" cloud image; no host mounts, no host credentials | README "Environment" |
| OS | Debian GNU/Linux 13 (trixie), `VERSION_ID="13"` | `logs/run-1.log` l. 3–4 |
| systemd (`systemd-sysext`, `systemd-confext`) | 257 (257.13-1~deb13u1) | `logs/run-1.log` l. 5 |
| Kernel | 6.12.115+deb13.1-cloud-arm64 (the module in H3 was built against its headers) | `logs/run-1.log` l. 6, l. 43 |
| Packages installed by the script | build-essential, `linux-headers-$(uname -r)`, squashfs-tools, kmod from the Debian archive on the run day. **Their exact versions were not logged**; a re-run should add `dpkg-query -W` for them | `scripts/run.sh` step 0b |
| Image level simulated | `SYSEXT_LEVEL=1.0` appended to `/usr/lib/os-release`; a test extension declares 2.0 and must be refused | `scripts/run.sh` steps 0b, 0e |
