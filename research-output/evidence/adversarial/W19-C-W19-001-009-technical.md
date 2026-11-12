# Refuter (technical): W19 DC-16 HOST EXTENSION MECHANISM [C-W19-001 … C-W19-009]

**Refuter:** independent, technical lens. **Date:** 2026-11-11. Read: the conclusion, the saved man page `evidence/sources/W19/systemd-sysext.txt`, `evidence/lab/w19-sysext/README.md` and both logs.

## Target
sysext/confext merge read-only images over `/usr`, `/opt` and `/etc`, gated by ID and SYSEXT_LEVEL. Debian 13 ships systemd 257.13. Lab W19-1 showed clean add and remove and the SYSEXT_LEVEL refusal.

## Check of the cited sources
- The man page text matches C-W19-001…003: L17-L38 (immutable images, `/var/lib/extensions`), L56-L60 (ID and SYSEXT_LEVEL matching), L155-L157 (confext).
- The lab log matches C-W19-006…009: `touch: cannot touch '/usr/bin/w19-probe': Read-only file system` (run-1 L39); taint line (L48-L49); API-level refusal (run-2).
- The pass/fail criteria were written before the run, and the README states its limits: n=1, a VM with a mutable root, no verity, no Secure Boot.

## Strongest counter-argument
The facts are correct, but the summary leaves out a property that matters: **merging any confext makes all of `/etc` read-only** (man page L155-L157: "Merging confexts on mutable host file systems will result in /etc/ becoming read-only"). The lab never tested a writer of `/etc` while a confext was merged. On a running OneMind node, k3s, NetworkManager, Tailscale and similar daemons write to `/etc`. Field reports show this combination has been fragile:
- systemd#31392: one confext makes the whole `/etc` read-only. The fix is mutable mode or write routing (systemd PR #31000). https://github.com/systemd/systemd/issues/31392
- systemd#36378: a confext masked `/etc/machine-id` on a read-only root (256.5). Fixed upstream; whether Debian's 257.13 has the fix is not verified here. https://github.com/systemd/systemd/issues/36378
- flatcar/Flatcar#2187 (open; last comment 2026-10-29): `systemd-sysext refresh` logs `device-mapper: reload ioctl ... failed: Required key not available` because the sysext signing key is not in the kernel's built-in trusted keys. systemd then falls back to userspace verification. The verity-signed path that the lab did not test is noisy even on the reference distribution. https://github.com/flatcar/Flatcar/issues/2187

## Verdict: **UPHELD (with an omission to add)**
Every factual statement checks out against primary text and the lab log. Add: "confext merges make `/etc` read-only unless `--mutable=` write routing is configured; Lab W19-1 did not test this with live `/etc` writers or with verity signatures."

## What would flip it
- **To WEAKENED:** T-W19-01 shows that k3s or the network stack fails with a confext merged in `--mutable=auto` mode on Debian 13. Or Debian 257.13 lacks the #34381 fix, so `/etc/machine-id` is masked on a read-only root.
- **To REFUTED:** a re-run (n ≥ 3) on a real RAUC read-only root where sysext/confext images do not merge at boot before k3s, or leave files behind after removal.
