# LT-DO-01 · First OneMind droplet boot on DigitalOcean (vm-do, BIOS)

**Status:** kit-ready (blocked: founder-access, DigitalOcean account) · **Time:** about 1 hour · **Milestone:** BM1 (BD-DO-1, brief 30 founder box) · **Serves:** F-14 (one OS from edge to cloud), P-4, R-1; BD-DO-1
**New test.** 22 has no DigitalOcean test, so its criteria are written here, **before any run** (brief 30 §2 rule 4). They are frozen by the commit that adds this file; change them only in a new dated section.

> **Explain it like I'm the founder.** DigitalOcean can boot our own disk image, but only the old **BIOS** way (no UEFI), and only if the image runs **cloud-init**, the small program that receives your SSH key and the droplet's network settings at first boot. So the build makes a special `vm-do` image: the same A/B slots and health gate as the Beelink image, booted by GRUB's BIOS version, plus cloud-init and SSH. In QEMU it already passed the battery under SeaBIOS (the same kind of BIOS DigitalOcean uses). This kit checks the one thing QEMU cannot: that a real droplet boots it, takes your key and network, and updates itself A → B. Agents never touch your DigitalOcean account (brief 30 rule 7), so you run this.

## Facts this kit relies on (DigitalOcean docs, fetched 2026-11-11; claim rows C-BUILD-002…005)
- Custom images must boot with **BIOS**; UEFI is not supported.
- Under **100 GB** uncompressed; formats raw (MBR or GPT), qcow2, VHDX, VDI or VMDK, optionally gzip or bzip2.
- **cloud-init ≥ 0.7.7** with the **ConfigDrive** data source before NoCloud; **sshd** starts at boot; an SSH key is mandatory.
- The image must fit the droplet's disk. `vm-do` is a 16 GiB disk (about 17.2 GB), so any droplet with a ≥ 25 GB disk fits; `/data` grows to the rest at first boot.

## Pre-registered pass / fail (frozen 2026-11-11)
| Step | PASS if | FAIL if |
|---|---|---|
| D1 Upload | The `vm-do` qcow2 from the `image` CI run imports as a custom image without an error | Import rejected |
| D2 First boot | A droplet (smallest size with ≥ 25 GB disk, your SSH key selected) reaches the login prompt on the web console within 10 min, and `ssh onemind@<droplet-ip>` with your key works | No boot, no network, or the key is refused |
| D3 Cloud layer | `cloud-init status --long` says `status: done`; the droplet's public IP from the control panel is on `eth0`/`ens3` (`ip -br a`); `/data` is larger than 6 GiB (`df -h /data`; the image's data partition is about 5 GiB, so it grew) | `status: error`, wrong or missing address, or `/data` not grown |
| D4 OneMind | `rauc status` shows `Booted from: rootfs.0 (A)`; `/data/onemind/gate.log` has `RESULT committed-boot slot=A`; `K3S-FRESH ok` within 10 min | Any of these missing |
| D5 Update | `sudo rauc install onemind-vm-do-<v>-next.raucb` then `sudo systemctl reboot`, with no further input: the droplet comes back on slot B, gate `RESULT mark-good slot=B version=<v>-next`, SSH still works with the same host key fingerprint | Stuck, rolled back, needs the console, or the host key changed |
| D6 Read-only root | `touch /usr/x` fails with "Read-only file system"; `ls /etc/ssh/ssh_host_*` lists nothing (host keys live in `/data/onemind/ssh/`) | The root is writable, or host keys ship in the slot |
| Expected limit | No Secure Boot, no TPM, no measured boot on a droplet (BIOS). Record it; it is not a failure | n/a |

**Verdict:** PASS if D1–D6 pass. BLOCKED (not FAIL) if the account cannot create custom images.

## Steps
1. **Get the image.** From the latest green `image` workflow run on the PR, download the artifact `image-debian-vm-do`. It holds `onemind-vm-do-<v>.qcow2`, `onemind-vm-do-<v>.raucb`, `onemind-vm-do-<v>-next.raucb`, `dev-ca.cert.pem` and `SHA256SUMS`. Check: `shasum -a 256 -c SHA256SUMS --ignore-missing`.
   Or build it on the Mac: `make rootfs BOARD=vm-do && make image BOARD=vm-do && make convert BOARD=vm-do` (images land in `out/image-vm-do/`).
2. **Upload** (D1): DigitalOcean control panel → Backups & Snapshots → Custom Images → Upload Image → the `.qcow2`; distribution "Unknown/Debian", the region you use.
3. **Create a droplet** (D2) from that custom image, smallest plan with a ≥ 25 GB disk, **your SSH key** selected, no user data. Open the web console and watch the boot (`GRUB-RAUC: …`, then `HEALTH-GATE: … RESULT committed-boot slot=A`).
4. **Check** (D3, D4, D6) over SSH:
   ```bash
   ssh onemind@<droplet-ip>
   cloud-init status --long; ip -br a; df -h /data
   sudo rauc status; sudo cat /data/onemind/gate.log
   touch /usr/x; ls /etc/ssh/ssh_host_* /data/onemind/ssh/
   ```
5. **Update** (D5): copy the next bundle up and install it.
   ```bash
   scp onemind-vm-do-*-next.raucb onemind@<droplet-ip>:   # into ~onemind, which lives on /data
   ssh onemind@<droplet-ip> 'sudo rauc install ~/onemind-vm-do-*-next.raucb && sudo systemctl reboot'
   ```
   Wait 5 minutes without touching anything, then SSH back in (the host key must not change) and run `sudo rauc status; sudo tail -5 /data/onemind/gate.log`.
6. **Record:** pipe everything you paste through `sh lab-kits/common/redact.sh` (it masks the droplet's IP addresses), write `research-output/evidence/lab/founder-hardware/LT-DO-01.md` from [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md), and **destroy the droplet and the custom image** afterwards (the image carries a throwaway dev CA; it is a test image, not a release).

## If it fails
- **No boot at all on the console:** note the last line. "GRUB" missing means the BIOS boot sector patch (`os/assemble/assemble.py` `install_bios_boot`) did not work on DigitalOcean's firmware even though SeaBIOS passed; a fallback is to let `grub-install --target=i386-pc` write it from a loop device in CI.
- **Boots but no network:** DigitalOcean hands out static addresses through ConfigDrive. cloud-init renders them into `/etc/systemd/network`, which is a tmpfs on this image (`os/boards/vm-do/rootfs/usr/lib/systemd/system/etc-systemd-network.mount`). Capture `sudo cat /run/cloud-init/network-config.json /etc/systemd/network/*` (redacted) for findings F-08.
- **`status: error`:** capture `sudo cloud-init status --long` and `sudo grep -i error /var/log/cloud-init.log` (redacted).
