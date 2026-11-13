<!-- SPDX-License-Identifier: Apache-2.0 -->
# Images: every deployment boots straight into OneMind (CORE-IMAGE)

**Date:** 2026-11-12 · **Status:** built (x86_64-efi, arm64-efi, vm, vm-do and rpi5 from one Containerfile; rpi5 not yet booted on a Pi, §8); Jetson not yet · **Founder request:** 2026-11-12, "images for every deployment that boot straight into OneMind" · **Serves:** D-007, brief 30 B2.1/B2.2 (layers "… → gate → `onemindd` → …"), B4.2 (updater in the image), BD-DO-1, BD-08; contract `sdk/contracts/poc-v0.md` §1–§3 · **Tests:** `test/qemu/CRITERIA-FIRSTBOOT.md` (F0–F4, pre-registered) on top of `test/qemu/CRITERIA.md` (T0–T11)

> **Explain it like I am the founder**
> Before this change the image was a bare, safe Linux: read-only, A/B updates, k3s and the health gate, but no OneMind on it. Now the same image carries OneMind itself: the node agent, the bus (NATS), the gateway with the dashboard, and the updater.
> Nothing runs until the box knows **what it is**: a **hub** (dashboard + bus), a **worker** (joins a hub) or a **leaf** (an edge device that forwards to a hub). It learns that at first boot from a cloud seed, from a small text file you edit on the flashed disk, or from a setup page at `http://onemind.local:8080/`.
> Everything the box creates (its secrets, database, tokens) lives on the data partition, so an OS update or a rollback never touches it.

## 1. Where each deployment stands

| Deployment | Board | Built by CI | Boots OneMind (QEMU) | Real hardware | Next step |
|---|---|---|---|---|---|
| Beelink / any UEFI x86 PC | `x86_64-efi` | yes (`image.yml`) | F0–F4 (§6) | kit LT-X86-01, not yet run | founder runs LT-X86-01 with this image |
| Generic arm64 UEFI (servers, VMs, Ampere) | `arm64-efi` | yes | F0–F4 (§6) | none | — |
| Local VMs (UTM, Proxmox, VirtualBox; qcow2/vhdx/vmdk/vdi/ova) | `vm` | yes | same tree as x86_64-efi; battery not run on `vm` | n/a | — |
| DigitalOcean droplet (BIOS, cloud-init) | `vm-do` | yes | T0–T5 + TC1; first-boot test not run on it yet (cloud-init's user-data path is supported, §3) | kit LT-DO-01, not yet run | founder runs LT-DO-01; put `onemind: {role: hub}` in the droplet's user-data |
| Raspberry Pi 5 (also CM5, Pi 500) | `rpi5` | yes (`image.yml`, arm64 runner): `.img.xz` + Raspberry Pi Imager entry; structure test in CI (§8) | not possible (QEMU cannot run the Pi firmware); desk check of the A/B path in a VM (§8) | kit LT-PI5-01 route P, not yet run | founder runs LT-PI5-01 route P |
| Jetson Orin (dev kit) | `jetson-orin` | OneMind **layer** only (`make jetson-layer`); the flash package is built on the owner's x86 Linux host from the owner's own NVIDIA downloads and never published (D-007, Z-01; §7) | no (NVIDIA boot chain; gate and verifier unit-tested) | LT-JET-01 steps 1–6 runnable, not yet run | founder runs LT-JET-01 |
| Clouds: AWS, Google Cloud, Azure, Hetzner, Proxmox VE | `cloud-aws`, `cloud-gcp`, `cloud-azure`, `cloud-hetzner`, `cloud-proxmox` (one `cloud` rootfs) | yes (`image.yml` job `cloud`) | C0–C4 PASS on each uploaded artifact, C5 (Hetzner) and C6 A/B update (AWS) PASS (`CLOUD-IMAGES.md` §5) | no real account yet | founder runs `os/cloud/<cloud>-import.sh` (`CLOUD-IMAGES.md` §3) |
| Machines OneMind does not own | none | — | — | — | developer install (`deploy/install.sh`, branch `feat/deploy-v0`) |

## 2. What is in the image (the OneMind layer)

Built by `os/rootfs/Containerfile` in builder stages; every download is pinned (version + sha256) in `os/versions.lock.yaml` → `onemind_layer` and fetched by `os/rootfs/fetch-onemind.sh`.

| Path in the slot (read-only) | What | Built from |
|---|---|---|
| `/usr/bin/onemindd`, `/usr/bin/onemind` | node agent (+ `onemindd update`) and CLI, static | `cmd/`, `internal/` with Go 1.26.11 (`go mod verify`, `-trimpath`) |
| `/usr/bin/nats-server` | NATS v2.15.2 | release tarball, tarball **and** binary sha256 checked |
| `/usr/lib/onemind/gateway/{python,venv}` | gateway (`onemind_core`) in a venv on Python 3.12.16 (python-build-standalone, fetched and hash-checked by uv 0.13.7) | `core/uv.lock` exported with hashes by uv on the build machine, installed by the target's own pip with `--require-hashes --only-binary :all:` (uv crashes under qemu-user, so it never runs emulated) |
| `/usr/lib/onemind/dashboard/` | built dashboard, served by the gateway at `/` | `dashboard/` with Node v24.22.3, `npm ci` from `package-lock.json` |
| `/usr/lib/onemind/apps/`, `/usr/lib/onemind/sdk/schema/` | Market seed catalog and app manifest schema | `apps/`, `sdk/schema/` |
| `/usr/lib/onemind/tuf/<channel>/root.json` | the update channel's trust root (os/update/CHANNEL.md §2) | placed by the release pipeline; **empty in dev images**, so the updater stays inert |
| `/usr/lib/onemind/onemind-firstboot`, `onemind-setup` | first boot and setup wizard (Python, stdlib + PyYAML) | `os/rootfs/layers/onemind/` |
| `/usr/lib/onemind/manifests/onemind-gateway.yaml` | the gateway's Kubernetes identity (admin role + namespaces, not cluster-admin) | applied by k3s |
| `/etc/avahi/services/onemind.service` + `avahi-daemon` | the box answers as `onemind.local`, announces :8080 | Debian package |
| units: `onemind-firstboot` (enabled), `onemind-nats`, `onemindd`, `onemind-gateway`, `onemind-gateway-kube`, `onemind-update`, `onemind-setup` (all **disabled**) | | `os/rootfs/layers/onemind/usr/lib/systemd/system/` |
| health gate: `onemind-health-gate`, `onemind-local-api` (enabled, unchanged) | | `os/gate/` |

The image units are the developer-install units (`deploy/systemd/`) adapted to a read-only root: binaries in `/usr/bin`, no `StateDirectory` (it would write to `/var/lib` on the read-only slot), settings and state on `/data`.

## 3. First boot

`onemind-firstboot.service` runs on **every** boot (after `/data` is mounted):

1. **Already configured** (`/data/onemind/firstboot/state.json` exists): print `ONEMIND-FIRSTBOOT: already configured role=…` and start the role's units. Nothing is regenerated.
2. Otherwise read the settings, first match wins:
   1. **cloud-init / NoCloud seed:** the `onemind:` mapping of the `#cloud-config` user-data. On cloud boards cloud-init's copy (`/var/lib/cloud/instance/user-data.txt`); elsewhere a filesystem labelled `CIDATA`/`cidata` is mounted read-only and read directly.
      ```yaml
      #cloud-config
      onemind:
        role: hub          # hub | worker | leaf
        name: Home         # optional
      ```
   2. **`/boot/efi/onemind.conf`:** every image ships this file on its FAT partition (any computer can open it after flashing), all lines commented out. Set `role = hub` (and for a worker or leaf `hub = …` and `join_token = …`). After use it is renamed `onemind.conf.applied`.
   3. **Nothing:** start the setup wizard on `:8080` (`http://onemind.local:8080/`): pick the role, and for a hub the page shows the owner token once. The wizard then exits and the gateway takes the port.
3. **Configure** (writes, in this order, `state.json` last so a power cut just reruns it):
   - a node id (`/data/onemind/etc/node-id`; the read-only root has no persistent machine-id, so the agent and the gateway are told this id),
   - NATS credentials (per-service passwords; hub: a `node` join token for workers and leaves),
   - the per-box CA in `/data/onemind/identity/` (EC P-256, 10 years; kept if a CA module created it first, NETWORKING.md §8),
   - hub: the owner token (only its sha256 is stored, `core/onemind_core/auth.py`), `gateway.env`, the gateway's data directory,
   - prints `ONEMIND OWNER TOKEN: …` and the join token **on the console only** (never in the journal); the wizard gets it through `/run` (tmpfs, deleted when shown).
4. **Start the role's units** (runtime `systemctl start`; enabling would write to the read-only `/etc`):

| Role | Units | NATS |
|---|---|---|
| hub | `onemind-nats`, `onemindd`, `onemind-gateway`, `onemind-gateway-kube` | server on :4222 (clients) and :7422 (leaf nodes), user/password per service |
| worker | `onemindd` | publishes to the hub's NATS (`nats://node:<join token>@<hub>:4222`) |
| leaf | `onemind-nats` (leaf mode), `onemindd` | local NATS on 127.0.0.1:4222, forwards to `nats-leaf://<hub>:7422` |

## 4. State on /data (read-only root)

| Path | Contents | Mode |
|---|---|---|
| `/data/onemind/firstboot/state.json` | role, source, node id, when | 0644 |
| `/data/onemind/etc/` | `role`, `node-id`, `onemindd.env`, `gateway.env`, `nats.conf` | dir 0700, secrets 0600 |
| `/data/onemind/secrets/join-token` | hub's join token | 0600 |
| `/data/onemind/identity/` | `ca.pem`, `ca.key` | 0700 / key 0600 |
| `/data/onemind/gateway/` | `tokens.yaml` (hashes only), `onemind.db`, `audit.jsonl`, `kubeconfig` | owned by `onemind` (uid/gid 961, fixed so updates keep ownership) |

An A/B update replaces only the slot; F4 proves `/data` and the owner token survive it.

## 5. v0 shortcuts (known, tracked)

- **NATS:** user/password, no TLS, no per-subject permissions; one shared `node` join secret for all workers and leaves. NETWORKING.md N-R6 (TLS with the box CA, per-node credentials) replaces it.
- **Workers still run their own k3s server** (the base image's k3s unit and the health gate's G1–G3 assume a server). Joining the hub's cluster as a k3s agent needs a gate variant for agents.
- **Wizard:** plain HTTP, first come first served on the LAN (the HAOS onboarding model) until the owner passkey flow (D-B9.1, BM2).
- **mDNS names:** every box is `onemind`; a second box on the same LAN gets avahi's `onemind-2.local`.
- **Health gate G6** still uses the stand-in local API (`onemind-local-api`); switching it to `onemindd`'s `/healthz` is a separate gate change with its own battery run.
- **Updater:** inert until the release pipeline ships a channel's `root.json`.

## 6. Test results (2026-11-12, local Lima VM on an Apple-silicon Mac)

Criteria `test/qemu/CRITERIA-FIRSTBOOT.md` (sha256 `4a312852…5a`, committed before the code). Raw results: `test/qemu/results/`. Build: Debian 13 leg, snapshot `20261111T000000Z`, rootfs built in the VM (amd64 through qemu-user), QEMU from the arm64 tools image.

| Board | Accel | F0 contents | F1 first boot as hub | F2 dashboard | F3 reboot keeps state | F4 A/B update keeps /data | Minutes |
|---|---|---|---|---|---|---|---|
| arm64-efi | KVM (nested) | PASS | PASS (gateway up 31 s after boot start) | PASS | PASS | PASS (`mark-good slot=B version=2`) | 3 |
| x86_64-efi | TCG | PASS | PASS (58 s) | PASS | PASS | PASS (gate committed B after 123 s, inside the 300 s budget) | 7 |

The existing battery on the same image, T0, T1, T2, T11, T3, T4, T4v, T5, T5v: **all PASS on arm64-efi** (KVM, 16 min) and **all PASS on x86_64-efi** (TCG, 30 min; T4/T5 decided at about 350 s after the reboot, as designed). The OneMind layer does not disturb the gate. CI (`image.yml`) runs F0–F4 on x86_64-efi (KVM) and arm64-efi on every change to `os/`, `core/`, `dashboard/`, `cmd/` or `internal/`.

**Not tested yet:** worker and leaf roles end to end (unit tests only: `test/unit/test_firstboot.py`); the setup wizard in a booted image (unit-tested over HTTP); `/boot/efi/onemind.conf` in a booted image (unit-tested); `vm-do` first boot through cloud-init's user-data path; the gateway's kubeconfig and an app install from the image.

## 7. Jetson Orin: a layer and a builder, not an image (2026-11-12)

**Why no image.** D-007 keeps Jetson on NVIDIA L4T. NVIDIA's BSP may be redistributed only unmodified, with its licence, for NVIDIA hardware [C-LIC-002, C-LIC-003], and NVIDIA's rootfs is Ubuntu, which may not be redistributed modified without Canonical's approval [C-LIC-011]; Z-01 is still open (`research-output/evidence/license-matrix.md` H-3, H-4). So OneMind publishes only what it owns: the **OneMind layer** (`make jetson-layer` → `out/onemind-layer-jetson-orin-<version>.tar.gz`, the same agent, NATS, gateway, dashboard, catalog, first boot and k3s as §2, plus the Jetson gate) and the scripts in `os/boards/jetson-orin/`. The owner downloads NVIDIA's files, and `build-flash-package.sh` checks them against the pins in `os/versions.lock.yaml` → `jetson`, installs the layer into NVIDIA's rootfs and flashes with `ROOTFS_AB=1`. The combined rootfs never leaves the owner's host.

**How updates work there.** NVIDIA's rootfs A/B (`APP`, `APP_b`) and image-based OTA do the slot work; OneMind adds the release contract around them (01 §4.2 item 1, brief 30 B4.7): a signed manifest (CMS, same CA as RAUC) checked on the box before NVIDIA's `nv_ota_start.sh` runs, the trial marker on `/data`, the same gate checks as §3 inside NVIDIA's hook `/usr/sbin/user_rootfs_validation.sh`, and `nvbootctrl verify` held back until the gate passes. Details, verified facts and open items: `os/boards/jetson-orin/README.md`.

**Tested:** `test/unit/test_jetson_orin.py` (gate decisions, verifier, signer, layout tool, pins); the layer build in the Lima VM. **Not tested:** anything on a Jetson; that is LT-JET-01.

## 8. Raspberry Pi 5: `rpi5` (2026-11-12)

> **Explain it like I am the founder.** A Pi 5 has no GRUB and no UEFI. Its own firmware (in the EEPROM chip on the board) reads a tiny file, `autoboot.txt`, on the first partition: "boot partition 2" (copy A) or "boot partition 3" (copy B). It also has a one-shot mode, **tryboot**: "boot the other copy once; if that boot never confirms, the next power-on goes back". OneMind's update engine (RAUC) drives that through a small script, so a Pi gets the same "a bad update rolls itself back" promise as the x86 box, with one difference: a new version gets **one** try, not three.

**What the image is.** Debian 13 arm64 (the same Containerfile and OneMind layer as every board, §2) with **Raspberry Pi's kernel 6.18.60** from `archive.raspberrypi.com`. Both kernel flavours ship in every boot slot: `kernel_2712.img` (16 KiB pages, the Pi 5 default, used) and `kernel8.img` (4 KiB pages, the fallback if k3s fails on 16 KiB pages, LT-PI5-01 step A1). Output: `onemind-rpi5-<version>.img.xz`, two bundles, and `os_list.json` for Raspberry Pi Imager (`make imager-json`).

| Choice | What | Why |
|---|---|---|
| A/B method | RAUC 1.15.2 `bootloader=custom` + `os/boards/rpi5/rootfs/usr/lib/onemind/rpi-tryboot-ab.sh`; firmware `tryboot_a_b=1` switches **whole boot partitions** | 01 §4.2 item 1 and brief 30's rpi5 row name this; it is the vendor-documented layout (autoboot.adoc) and the backend is the F-PI5 kit's, desk-checked [C-LAB-rauc-1152-013, -017]. The documented alternatives were weaker for us: HAOS's single boot partition with `os_prefix` folders shares one FAT for both slots; Rugix is a different engine (01 §6.7, kept as the fallback if LT-PI5-01 fails); U-Boot adds a bootloader the Pi does not need |
| Layout (BD-07) | MBR: p1 64 MiB FAT `ONEMIND` (`autoboot.txt`, `slot-A.good`/`slot-B.good`, `onemind.conf`), p2/p3 512 MiB FAT boot A/B, p5/p6 8 GiB ext4 root A/B, p7 ext4 data; 20 GiB image | the kit's layout with 04 §11's labels. MBR because Pi 5 tryboot on GPT is UNVERIFIED. Partitions are found by PARTUUID `4f4d5035-NN` (MBR has no names) |
| SD, USB SSD, NVMe | one image for all three; `root=PARTUUID=…` works on each; `onemind-rpi5-grow` grows p4 and p7 to the device at every boot (no-op once grown) | a hub belongs on NVMe or USB SSD (BD-07); worker and leaf may run from a ≥ 32 GB SD card |
| `config.txt` / `cmdline` per slot | one `config.txt` in both slots, `[boot_partition=2] cmdline=cmdline_a.txt` / `[boot_partition=3] cmdline=cmdline_b.txt`; `force_eeprom_read=0`, camera and display auto-detect off, no `os_prefix` | brief 30 B2 rpi5 row (E10). Generated and unit-tested in `os/boards/rpi5/rpi5_boot.py` |
| Kernel pins | four debs pinned by pool path + sha256 (`os/versions.lock.yaml` → `rpi5`), read from the trixie index whose InRelease verified with the Raspberry Pi Archive Signing Key `CF8A1AF5…7FA3303E`; `pin-rpi.sh` re-derives them | the archive has no snapshot service, but its pool keeps old versions, so a pin stays buildable |
| EEPROM | **not shipped** (no `rpi-eeprom`, so no vendor auto-update, E10); the image targets bootloader 2026-09-25 (rpi-eeprom 28.36-1) and warns on the console if the Pi's is older | the owner updates the EEPROM on purpose (Imager → Bootloader). An EEPROM update inside an OS release is out of scope (22 LT-PI5-01 "Not covered") |
| Watchdog | `RuntimeWatchdogSec=10s` | the Pi's `bcm2835_wdt` accepts about 15 s at most; the base layer's 30 s would not arm (F-PI5 kit value) |
| Gate | the same `onemind-health-gate`; on rpi5 it sources `/usr/lib/onemind/gate-slot-env`, which reads slot state from the backend's markers instead of grubenv | one gate for every board (F-PI5 kit §5) |

**Test results (2026-11-12, arm64 Lima VM on an Apple-silicon Mac; QEMU cannot boot the Pi firmware, so no boot test):**
- `make image BOARD=rpi5` → `onemind-rpi5-0.1.0-dev.img` (20 GiB, **515 MB** as `.img.xz`), two verity bundles (boot + rootfs, ~540 MiB each), `os_list.json`. Pinned kernel debs sha256-verified in the build; the Debian kernel and GRUB EFI removed.
- `make rpi5-check` (`os/boards/rpi5/check-image.py`, also in CI): **37/37 PASS**: the MBR as planned (sfdisk reads it back with "No errors detected"), both kernels, `bcm2712*` device trees and overlays in boot A, `config.txt`/`cmdline_*.txt` byte-equal to the generator, boot B empty, RAUC custom backend and PARTUUID slots, OneMind binaries, no Debian kernel, no `rpi-eeprom` updater, bundle verified.
- `make fixtures BOARD=rpi5 UPTO=T10 HW=1`: T0 PASS, the 8 LT-PI5-01 bundles built.
- `os/boards/rpi5/desk-check.sh` on that disk (loop devices, the image's own RAUC 1.15.2 as a D-Bus service): **PASS**. `wrong-key` and `plain-good` refused; `good` installed from slot A into boot B + root B, trial marker `B 2`, one-shot `0 tryboot` armed, `autoboot.txt` untouched; with a faked device tree (tryboot boot of partition 3) `rauc status mark-good booted` swapped `autoboot.txt` to B.
- **Found and fixed by the desk check:** the kit's backend synced only the directory after renaming `autoboot.txt.new`. On vfat the renamed file's directory entry is written only when that file is synced, so after a "successful" commit the medium still held the old `autoboot.txt`, pointing at a freed cluster (`fsck.vfat`: "cluster chain length is 0"). A power cut in the following seconds would have lost the commit and left the FAT inconsistent. The backend now fsyncs the renamed file and then the whole filesystem; the desk check reads the medium after the commit and requires the new content and a clean FAT.
- `onemind-rpi5-grow` on a loop device standing in for a larger card: /data 2.9 → 6.8 GiB online, a no-op on the second run. Unit tests: `test/unit/test_rpi5.py` (17: layout, MBR round trip, boot config, backend state machine with a faked device tree, pins, Imager entry).
- **Not tested:** anything on a real Pi 5 (firmware `tryboot`, the watchdog, 16 KiB pages with k3s, NVMe/SD boot). That is LT-PI5-01 route P.

**Known limits (v0):** one tryboot try per update, so a power cut during the trial abandons the update (expected; re-offering it is B4.2/REC-DEC-32, not built); no Wi-Fi or Bluetooth firmware yet (Debian `main` only; Ethernet works); no Pi secure boot (irreversible OTP, out of scope); the console is `serial0` + HDMI `tty1`.

## Cloud images (AWS, Google Cloud, Azure, Hetzner, Proxmox), 2026-11-12

One `cloud` rootfs (the `vm-do` cloud layer: cloud-init on a read-only root, sshd, `admin` user) and five boards assembled from it, each with its own cloud-init datasource order and RAUC `compatible`, packaged in the format that cloud imports (raw, `disk.raw` in a tar.gz, fixed VHD, qcow2; Hetzner by rescue-mode snapshot). The role comes from user-data as in §3; the owner token is on the serial console and, until the first reboot, in `/run/onemind/owner-token` over SSH. Details, import scripts and results: [`CLOUD-IMAGES.md`](CLOUD-IMAGES.md).
