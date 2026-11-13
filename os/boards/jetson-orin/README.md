# Board `jetson-orin`: OneMind on NVIDIA L4T (Jetson Orin Nano / NX dev kits)

**Serves:** D-007 (Jetson runs NVIDIA L4T), brief 30 B4.7 (Jetson backend) and D-B2.5, 01 §4.2 item 1, REC-DEC-18/-35/-47/-49 · **Kit:** [`lab-kits/LT-JET-01`](../../../lab-kits/LT-JET-01/README.md) · **Status (2026-11-12):** code and unit tests done; nothing has run on a Jetson yet.

> **In plain words.** On every other board OneMind builds the whole disk image. On a Jetson, NVIDIA's software has to be the base (D-007), and we are not allowed to hand out NVIDIA's Ubuntu-based system with our changes in it (the licence section below). So we hand out two things we own: the **OneMind layer** (our programs, packed as one file) and a **builder script**. You download NVIDIA's files yourself; the script checks they are exactly the files we tested, adds the OneMind layer, and flashes your Jetson with NVIDIA's own tool. Updates use NVIDIA's own two-slot system, with OneMind's signature check before an update and OneMind's health check after it.

## Licence: why there is no Jetson image to download

Read from the licence texts themselves (`research-output/evidence/license-matrix.md` H-3, H-4, §6):

- **NVIDIA's BSP** (bootloader, firmware, drivers): may be redistributed **only unmodified**, with the NVIDIA Driver License Agreement given to each recipient, for NVIDIA hardware only; it is revocable, and NVIDIA disclaims "Critical Applications" (navigation, autonomous vehicles, military, medical) [C-LIC-002…005].
- **NVIDIA's sample rootfs is Ubuntu 24.04.** A modified Ubuntu image needs Canonical's approval or a debranded rebuild [C-LIC-011], and NVIDIA's staff say their redistribution answer does not cover the Ubuntu rootfs [C-REF-DC-cost-007]. Z-01 (ask Canonical) is still open.

So OneMind publishes **only** its layer and these scripts. The owner downloads NVIDIA's files, the flash package and OTA bundles are built on the owner's host, and they never leave it. `lint.sh` already refuses any Ubuntu artifact in `image.yml`; nothing here uploads one. The NVIDIA licence text stays in the rootfs where NVIDIA's packages put it (`/usr/share/doc/nvidia-l4t-*`), and the builder never modifies an NVIDIA binary: it changes only text configuration (`nv_ota_run_tasks.sh`'s retry count) and adds files beside NVIDIA's.

## The pieces

| File | Runs on | What it does |
|---|---|---|
| `make-layer.sh` (`make jetson-layer`) | Lima VM / CI (Docker, arm64) | Builds `onemind-layer-jetson-orin-<version>.tar.gz` from the shared Containerfile stages: `onemindd`, `onemind`, NATS, gateway venv, dashboard, catalog, schema, first boot, k3s + air-gap images, the gate checks, and the Jetson files in `rootfs/`. Holds no NVIDIA or Ubuntu file. |
| `pins.sh` | owner's host | NVIDIA download names and sha256 for L4T 39.2.1 (target) and 36.5.2 (OTA base); same values as `os/versions.lock.yaml` → `jetson`. |
| `build-flash-package.sh` | owner's x86-64 Linux host, `sudo` | Verifies NVIDIA's three tarballs, unpacks BSP + sample rootfs, runs NVIDIA's `apply_binaries.sh`, checks NVIDIA's hook contract in the result, installs and verifies the layer, enables OneMind's units, writes the A/B layout with `onemind-data`, records the layout, prints (or with `--flash` runs) NVIDIA's `ROOTFS_AB=1` initrd flash. |
| `build-ota-bundle.sh` | owner's host, `sudo` | Runs NVIDIA's `l4t_generate_ota_package.sh` with `OTA_MAX_RETRY_COUNT=3`, writes the OneMind manifest and signs it (refused if the layout flags differ from the device's recorded layout). |
| `jetson_layout.py` | owner's host | Copies NVIDIA's A/B layout XML and inserts `onemind-data` after `APP_b` (text insertion: NVIDIA's file is kept byte for byte); writes `jetson-layout.json`. |
| `rootfs/usr/sbin/user_rootfs_validation.sh` | Jetson | NVIDIA's customer hook → `onemind-jetson gate`. |
| `rootfs/usr/lib/onemind/jetson/onemind_jetson.py` | Jetson (+ host for signing) | `gate`, `wait-pass`, `ota-verify`, `ota-apply`, `ota-manifest`, `ota-sign`. |
| `rootfs/etc/systemd/system/*.d/` | Jetson | Make NVIDIA's validation service wait for the gate; keep `nvbootctrl verify` behind the gate's pass. |
| `rootfs/usr/lib/onemind/jetson/onemind-jetson-data` + unit | Jetson | First boot: ext4 on the empty `onemind-data` partition (only if it holds no signature at all). |

## How an update works (the OneMind release contract on NVIDIA's A/B)

1. **Build** (owner's host): `build-flash-package.sh` makes the new target tree, `build-ota-bundle.sh` makes `ota_payload_package.tar.gz` with NVIDIA's generator and a manifest (`schema onemind.io/jetson-ota/v1`: version, compatible, layout flags, L4T from/to, the QSPI version it requires, sha256 of every file, expiry), signed with CMS by the OneMind release CA. It refuses to sign if the payload's layout flags (`target_board`, `rootfs_ab`, `external_device`, `rootfs_size`, `rootfs_enc`, `uefi_secure_boot`) differ from the device's recorded layout: a payload built with the wrong layout has needed a USB reflash [C-REF-DC-cost-004].
2. **Verify** (box): `onemind-jetson ota-apply <bundle>` checks the signature against `/etc/onemind/keyring.pem` first, then schema, compatible, expiry, layout flags against `/data/onemind/jetson/device-layout.json` (recorded at the first boot after the factory flash), the running L4T (`/etc/nv_tegra_release`), the QSPI version (`nvbootctrl dump-slots-info`, REC-DEC-47), the bad-release list, and every file's sha256. NVIDIA's payload carries no signature of its own [C-REF3-DC-security-001].
3. **Trial marker, then NVIDIA:** it writes `/data/onemind/pending` = `<other slot> <version>` **before** anything touches the other slot (the RAUC pre-install rule), then runs NVIDIA's `nv_ota_start.sh`. With A/B enabled NVIDIA's OTA writes the non-current slot and makes it active (`nv_ota_update_implement.sh`: "ROOTFS_AB_ENABLED=1: update rootfs on the non-current slot"). A power cut during the update reboots into NVIDIA's recovery kernel and resumes, up to `OTA_MAX_RETRY_COUNT` times (set to 3; NVIDIA's default 0 ends in a recovery shell [C-W3-051]).
4. **Gate** (first boot of the new slot): NVIDIA's validation service runs `/usr/sbin/user_rootfs_validation.sh` → `onemind-jetson gate`. Same checks as every other board (`onemind-k3s-check` G1–G6: fresh kubeconfig, kubelet, node heartbeat, core pods, `/data` rw, local API) plus G7 (booted `/etc/onemind/release` = the bundle's version). Three passes in a row → the gate writes its pass for this boot, and only then does `nv-l4t-bootloader-config.service` run `nvbootctrl verify` (commit). Failure or deadline (300 s) → the version goes on the bad list and the hook exits 1; NVIDIA's script then runs `reboot`, a **warm** reset, which lowers the slot's retry counter [C-REF3-DC-technical-001]. Retry boots of a version already judged bad fail in seconds. After `ROOTFS_RETRY_COUNT_MAX` (3) warm tries the cpu-bootloader marks the slot unbootable and boots the other one, where the gate sees the marker naming the other slot ("fell-back"), records it and passes.
5. **Never auto-retried:** `ota-apply` refuses a version on the bad list, and refuses while a trial is pending.

**A gap the research did not have, closed here:** in both releases NVIDIA ships the validation service as `Type=simple`, and `nv-l4t-bootloader-config.service` is only ordered `After=` it. For a simple service, `After=` waits for the start, not the end, so `nvbootctrl verify` could commit a slot while the hook is still deciding. Two drop-ins close it: the validation service becomes `Type=oneshot`, and `nv-l4t-bootloader-config` gets `ExecStartPre=onemind-jetson wait-pass`, which fails unless the gate passed on this boot (so `verify` never runs on an undecided or rejected slot).

## What is verified, and from where

| Fact | Source (read 2026-11-12) |
|---|---|
| Customer hook path `/usr/sbin/user_rootfs_validation.sh`; non-zero → `reboot` | `nvidia-l4t-bootloader-utils_39.2.1` (`/opt/nvidia/l4t-rootfs-validation-config/nv-rootfs-validation-config.sh`) and `nvidia-l4t-init_36.5.2` (`l4t-rootfs-validation-config.sh`); packages from NVIDIA's apt feed, sha256 in `os/versions.lock.yaml`, unpacked as data |
| Unit names (`nv-rootfs-validation-config.service` on 39.2.1, `l4t-rootfs-validation-config.service` on 36.5.2), `Type=simple`; bootloader-config `After=` it, `Type=oneshot`, runs `nvbootctrl verify` | same packages |
| `OTA_MAX_RETRY_COUNT=0` hard-coded in `nv_ota_run_tasks.sh`; A/B OTA writes the non-current slot and sets it active | `ota_tools_R39.2.1_aarch64.tbz2` (pinned), read as data |
| A/B NVMe layout `flash_l4t_t234_nvme_rootfs_ab.xml`: `APP`, `APP_b` fixed `APPSIZE`, then only `secondary_gpt`; `ROOTFSSIZE=55GiB` halved per slot with `ROOTFS_AB=1` | BSP 39.2.1 tarball (pinned) |
| Flash command shape: `ROOTFS_AB=1 ./tools/kernel_flash/l4t_initrd_flash.sh --external-device nvme0n1 -c <layout> <board> external` | BSP `README_initrd_flash.txt`, "Workflow 4" |
| Retry counter, 3 tries default, `ROOTFS_RETRY_COUNT_MAX` 0–3 | `research-output/evidence/sources/W3/nvidia-jetson-r39.2-RootFileSystem.txt` [C-W3-049] |
| BSP tarball hashes | hashed on download; equal to meta-tegra's `SRC_URI[sha256sum]` (wrynose 39.2.1, scarthgap 36.5.2) |

## UNVERIFIED (each is a step in LT-JET-01)

- That `onemind-data` with allocation `0x808` after `APP_b` is created and fills the disk on an Orin Nano NVMe flash (step 1 records `lsblk`).
- That `ROOTFS_RETRY_COUNT_MAX` is honoured through `l4t_initrd_flash.sh` (it is documented for `flash.sh`), and that `-S` (rootfs size) is accepted by the initrd flash; the builder uses NVIDIA's default size unless `--rootfs-size` is given.
- That 36.5.2 is an accepted base for an image-based OTA to 39.2.1: the saved r39.2 table lists 36.5.0 [C-W3-050]. If NVIDIA's generator refuses `R36-5` for 36.5.2, step 3 re-runs from 36.5.0 (add its pins first).
- That NVIDIA's sample rootfs has every command the layer needs (`python3`, `openssl`, `curl`, `findmnt`, `blkid`, `mkfs.ext4`, `avahi-daemon`); the builder stops with the list if not, because it installs no unpinned packages.
- k3s on the Tegra kernel: a network-policy controller panic has been reported [C-REF-DC-technical-006]. If the gate fails on G1/G2 for that reason, the k3s flags are the fix, not the gate.
- GPU in k3s (CDI, device plugin) is not in this layer; it is a separate driver-pack item (E4).

## Not done here (follow-ups)

- `onemindd update` drives RAUC only; on Jetson the update service stays inert (no `/etc/onemind/update.conf`) and updates go through `onemind-jetson ota-apply`. Teaching `onemindd update` the Jetson backend (TUF channel → bundle → `ota-apply`) is the next step.
- Secure Boot / fused Jetsons (`--uefi-keys`, PKC/SBK) and disk encryption are out of scope; the layout record carries `uefi_secure_boot: false` and `rootfs_enc: false`, so a payload built with them is refused.
- Fuzzing the verifier (01 §4.2 rev. 3 "reviewed and fuzzed like the gate").
- Yocto/meta-tegra (no Ubuntu at all) stays LT-JET-06.
