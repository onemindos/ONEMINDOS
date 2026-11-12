# LT-X86-00 · Inventory of the founder machines (Beelink, and the Dell if available)

**Status:** kit-ready (blocked: founder-hardware) · **Time:** 30 min per machine · **Milestone:** BM0 (brief 30 §7) · **Serves:** Q290, X-1, X-3, W2-HW-5; feeds every x86 kit below
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §3. They are not edited here.

> **Explain it like I'm the founder.** Before we test OneMind on your Beelink we need to know exactly what it is: which CPU, whether it has a TPM (the security chip that can lock the data disk to this machine), what Secure Boot says, and which **watchdog** chip it has. The watchdog is a hardware timer that restarts the box if the OS freezes; our image must load the right driver for it, or a frozen update would sit there forever instead of rolling back. You boot a Debian 13 **live USB** (it runs from the stick and installs nothing), run one script, and paste the redacted output.

## What you need
- A USB stick with the Debian 13 live image (any "debian-live-13.*-amd64-standard.iso" from debian.org, checked against its SHA256SUMS).
- The Beelink (and the Dell 5540 if you still have it). Nothing on the internal disk is touched.

## Steps
1. Boot the box from the live USB (firmware boot menu, often F7 or F12 on Beelink). Choose the live system, not "install".
2. Get this kit onto the live system (a second USB stick, or `git clone` if the box has network).
3. Run:
   ```bash
   sudo apt-get update && sudo apt-get install -y mokutil fwupd dmidecode   # live system only
   sudo sh lab-kits/LT-X86-00/inventory.sh | tee inventory.txt
   ```
4. On the Mac (22's last line): `sysctl -n machdep.cpu.brand_string hw.memsize; sw_vers -productVersion`.
5. Fill [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md) as `research-output/evidence/lab/founder-hardware/LT-X86-00.md` (brief 30 §9 allows that one folder). Run `make hygiene` before you commit.

## Expected output (what "good" looks like)
- `Model name:` a real CPU name (for the U55, probably an i3-5005U; 22 marks it unconfirmed).
- `ls /sys/class/tpm` lists `tpm0` and `systemd-analyze has-tpm2` says `yes`, or it shows nothing (then the box is "no TPM": the data disk uses a recovery key only, X-3).
- `SecureBoot enabled` or `disabled`; either is fine for v0, just record it.
- A watchdog line such as `iTCO_wdt: Found a ... TCO device` or `sp5100_tco`. The image already loads `iTCO_wdt` and `sp5100_tco` (os/rootfs/layers/base/usr/share/initramfs-tools/modules.d/onemind-watchdog); if yours is different, say so in the result and we add it.
- `x86-64-v3 (supported)` or not. Below v3 only excludes the year-2 bootc Industrial profile (W2-HW-5).

## Pass / fail
As in [CRITERIA-22.md](CRITERIA-22.md): every field filled, no "unknown"; U55 CPU confirmed.

## Why this matters for the build
The watchdog driver and the TPM answer change two things in the image (initramfs module list, data-disk unlock mode). The CPU and Secure Boot state decide whether the Beelink can also carry the Secure Boot kits (LT-X86-03/04) if the Dell is gone (`docs/learning/06-…` §5, PR #4).
