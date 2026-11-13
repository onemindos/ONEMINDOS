# LT-JET-01 · NVIDIA A/B with the OneMind gate, OTA and power cuts (Jetson Orin Nano)

**Status:** kit-ready for all six steps (blocked: founder-hardware). The Jetson backend B4.7 now exists in [`os/boards/jetson-orin`](../../os/boards/jetson-orin/README.md): the gate in NVIDIA's hook, OneMind's payload verifier, the QSPI field in the manifest. Its logic is unit-tested (`test/unit/test_jetson_orin.py`); none of it has run on a Jetson. · **Time:** about 1 day · **Milestone:** 22 schedules it in week 4; brief 30 lists the Jetson package under BM2 (D-B2.5) · **Serves:** DC-07, DC-08, REC-DEC-18, -35, -47, -49; F-14
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §5. They are not edited here.

> **Explain it like I'm the founder.** On a Jetson, NVIDIA's own boot chain owns A/B: the board has two root filesystems (`APP` and `APP_b`) when it is flashed with `ROOTFS_AB=1`, and NVIDIA's tools switch between them. OneMind does not replace that. It plugs its health check into NVIDIA's "is this new root OK?" hook, and it checks OneMind's signature on an update before NVIDIA's updater may touch the disk. This kit flashes your Jetson with OneMind on NVIDIA's JetPack 6.2 (L4T 36.5.2), proves the slots fall back when one is broken, sends a deliberately bad update and watches the gate roll it back, then updates to JetPack 7.2.1 (L4T 39.2.1) while you pull the power in the middle.

## What you need
- The Jetson Orin Nano (Super) dev kit with an **NVMe SSD** (128 GB or more; the layout puts both root slots and the data partition on it), its PSU, a USB-C cable, a way to pull power, and a network cable (the box must be reachable by SSH as `onemind.local` or by IP).
- **An x86-64 Linux host** for flashing (Ubuntu 22.04 or 24.04; NVIDIA's flash tools do not run on a Mac: brief 30 D-B1.8, [C-W18-021]) with about 60 GB free, `sudo`, `python3`, `openssl`, `curl`. The Beelink booted from a live USB works if it has the disk space.
- The Mac with the Lima VM (`handbook/workbench.md`) to build the OneMind layer.
- **Why you build it yourself:** OneMind may not hand out NVIDIA's Ubuntu rootfs with OneMind inside (Z-01; the board README "Licence"). The scripts download NVIDIA's files from NVIDIA onto your host, check each against the sha256 pinned in `os/versions.lock.yaml` → `jetson`, and everything they make stays on your host. By downloading NVIDIA's files you accept NVIDIA's licence yourself.

## Step 0 · Build the OneMind layer (Mac, Lima VM, ~5 min)
```bash
make jetson-layer VERSION=0.1.0     # inside the Lima VM -> out/onemind-layer-jetson-orin-0.1.0.tar.gz (+ .sha256)
```
Copy the `.tar.gz` and its `.sha256` to the flashing host, next to a checkout of this repo at the same commit. Below, `$K` is that checkout, `$J` a work folder (e.g. `~/onemind-jetson`), `$LAYER` the layer file.

## Step 1 · Flash A/B with OneMind on JetPack 6.2.x (criteria step 1)
```bash
sudo $K/os/boards/jetson-orin/build-flash-package.sh --l4t 36.5.2 --layer $LAYER --downloads $J/dl --fetch \
     --work $J/base-r36 --role hub --accept-nvidia-license
```
It prints the flash command and saves `$J/base-r36/onemind-jetson-release.json` and `$J/base-r36/dev-ca/` (a throwaway signing CA for this test; never publish it). `--accept-nvidia-license` lets NVIDIA's tool create the user `onemind-admin`; its password is in `$J/base-r36/default-user.txt`. Put the Jetson in **recovery mode** (dev kit: jumper the FC REC and GND pins, then power on; check NVIDIA's quick start for your carrier), connect USB-C, then run the printed command from `$J/base-r36/Linux_for_Tegra`. After the first boot (the hub's first-boot screen shows the owner token once), log in and record:
```bash
cat /etc/nv_tegra_release
sudo nvbootctrl dump-slots-info
sudo nvbootctrl -t rootfs dump-slots-info
lsblk -o NAME,SIZE,PARTLABEL,FSTYPE,MOUNTPOINT
systemctl status nv-l4t-bootloader-config --no-pager     # must end 0/SUCCESS
sudo cat /data/onemind/gate.log                           # expect "RESULT committed-boot"
sudo cat /data/onemind/jetson/device-layout.json
```
**Kit pass:** both rootfs slots `normal`; `onemind-data` exists, is ext4 and is mounted on `/data`; the gate log shows a committed boot. If `onemind-data` is missing or tiny, stop: the layout insertion (UNVERIFIED) needs fixing before steps 2–6.

## Step 4 · Corrupt slot B → boots A (criteria step 4; run it now, it needs only step 1)
On slot A (`sudo nvbootctrl -t rootfs get-current-slot` prints `0`):
```bash
sudo dd if=/dev/zero of=/dev/disk/by-partlabel/APP_b bs=1M count=16 conv=fsync   # destroys slot B's filesystem, on the Jetson only
sudo nvbootctrl -t rootfs set-active-boot-slot 1
sudo reboot
```
Wait up to 10 minutes. **Pass:** the box comes back on slot A, and `sudo nvbootctrl -t rootfs dump-slots-info` shows slot 1 `unbootable`. If it hangs instead (a kernel that cannot mount its root and does not reboot), that is the criteria's step-5 "root mount failure with the watchdog armed" case: record how long it hung and whether only a power cycle recovered it. Slot B is rewritten by the update in step 2.

## Step 2 · The OneMind gate in NVIDIA's hook; a bad update falls back (criteria step 2)
Build a **good** update (positive control) and a **bad** one (k3s made unexecutable), both on L4T 36.5.2, signed by the step-1 CA:
```bash
B=$J/base-r36; CA="--cert $B/dev-ca/ca.pem --key $B/dev-ca/ca.key"
for v in 0.1.1 0.1.2-bad; do
  brk=""; [ $v = 0.1.2-bad ] && brk="--break k3s"
  sudo $K/os/boards/jetson-orin/build-flash-package.sh --l4t 36.5.2 --layer $LAYER --downloads $J/dl \
       --work $J/t-$v --version $v --keyring $B/dev-ca/ca.pem $brk
  sudo $K/os/boards/jetson-orin/build-ota-bundle.sh --base $B/Linux_for_Tegra --target $J/t-$v/Linux_for_Tegra \
       --base-l4t 36.5.2 --target-l4t 36.5.2 --downloads $J/dl --device-layout $B/jetson-layout.json $CA \
       --requires-qspi "<the 'Current version' from step 1's dump-slots-info>" --out $J/bundle-$v
done
```
Copy each bundle to the box and apply it (no console needed):
```bash
sudo install -d -o onemind-admin /data/onemind/bundles          # on the Jetson, once
U=onemind-admin; H=onemind.local; BOX="$U"@"$H"     # or the box's address
scp -r $J/bundle-0.1.1 "$BOX":/data/onemind/bundles/
ssh "$BOX" 'sudo onemind-jetson ota-verify /data/onemind/bundles/bundle-0.1.1 && sudo onemind-jetson ota-apply /data/onemind/bundles/bundle-0.1.1 --reboot'
```
After it comes back: `sudo cat /data/onemind/gate.log` must show `RESULT mark-good ... version=0.1.1`, and `cat /etc/onemind/release` shows 0.1.1. Then the same with `bundle-0.1.2-bad`. **Pass (criteria step 2):** the first trial boot of 0.1.2-bad ends with `RESULT reject ... verdict=image-bad`, the retry boots end in seconds ("already judged bad"), NVIDIA falls back, and the box runs 0.1.1 again with `RESULT fell-back` in the log and `version=0.1.2-bad` in `/data/onemind/bad-releases`. Also run `sudo onemind-jetson ota-apply /data/onemind/bundles/bundle-0.1.2-bad` once more: it must be **REFUSED** (no auto-retry). Time the whole fallback.

## Step 3 · Image-based OTA r36 → r39 with a power cut, unattended (criteria step 3)
```bash
sudo $K/os/boards/jetson-orin/build-flash-package.sh --l4t 39.2.1 --layer $LAYER --downloads $J/dl --fetch \
     --work $J/t-0.2.0 --version 0.2.0 --keyring $B/dev-ca/ca.pem
sudo $K/os/boards/jetson-orin/build-ota-bundle.sh --base $B/Linux_for_Tegra --target $J/t-0.2.0/Linux_for_Tegra \
     --base-l4t 36.5.2 --target-l4t 39.2.1 --downloads $J/dl --device-layout $B/jetson-layout.json $CA \
     --requires-qspi "<'Current version' now>" --out $J/bundle-0.2.0
```
If NVIDIA's generator refuses the base (36.5.2 is not in the saved r39.2 support table, which lists 36.5.0 [C-W3-050]), record **BLOCKED** with its message. Otherwise record `sudo nvbootctrl dump-slots-info` (QSPI version **before**) and `sudo cat /data/onemind/firstboot/state.json | head -c 200` (node identity), then apply over SSH only, with no console attached: `sudo onemind-jetson ota-apply <bundle> --reboot`. While the box is in NVIDIA's recovery kernel writing the update (it stops answering ping; a few minutes in), **pull the power once**, wait 10 s, restore it. **Pass:** the update resumes or falls back with no reflash; the box ends on L4T 39.2.1 (`cat /etc/nv_tegra_release`) running OneMind 0.2.0 (the gate's `RESULT mark-good ... version=0.2.0` line is the version assertion of criteria step 5); `/data` and the node identity are unchanged; record the QSPI version **after**. This dev-kit run is a rehearsal; the claim needs a production Orin NX module (criteria step 3, rev. 4).

## Step 5 · Cold power cycle after a hang (criteria step 5)
NVIDIA's retry counter ignores cold resets [C-REF3-DC-technical-001]. Apply any good bundle, and during its trial boot (gate log shows `mode=trial`) crash the box: `echo c | sudo tee /proc/sysrq-trigger`, pull power, restore. Record which slot boots, three times. Steps 4 and 3 already cover "root mount failure" and "the running version equals the bundle's".

## Step 6 · QSPI version in the manifest (criteria step 6)
`cat $J/bundle-0.2.0/manifest.json` shows `bootloader.requires_qspi` and `installs`. Build one more bundle exactly like step 3's but with `--requires-qspi 0.0.0`, copy it, and run `sudo onemind-jetson ota-verify <it>`. **Pass:** `REFUSED: payload requires QSPI 0.0.0 but the device has …`.

## Record
Write `research-output/evidence/lab/founder-hardware/LT-JET-01.md` from [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md): every command above with its output, each step PASS / FAIL / BLOCKED, the fallback and OTA timings, QSPI before/after, the `lsblk` of step 1, and the kit commit. Pipe pasted output through `sh lab-kits/common/redact.sh`. Never run any fuse-burning command (`odmfuse`, SB-8; 22 §2.3 rule 4); the scripts never do. Never publish the flash package, a bundle or the rootfs: they contain NVIDIA's BSP and an Ubuntu rootfs (Z-01). The dev CA in `$J/base-r36/dev-ca` is for this test only.

## Pass / fail
As in [CRITERIA-22.md](CRITERIA-22.md).
