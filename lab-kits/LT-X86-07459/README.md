<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-X86-07459 · Dell Inspiron 7459 all-in-one as the daily hub (bare metal)

**Status:** kit-ready (blocked: founder-hardware) · **Time:** about 1.5 hours · **Serves:** #234 (M-LIVE), #242 (the box's own screen), D-007, brief 30 B2 · **Based on:** [../LT-X86-01/INSTALL-BEELINK.md](../LT-X86-01/INSTALL-BEELINK.md) (same installer stick and screens)

**Id note:** `LT-X86-00` to `LT-X86-16` are taken in `research-output/22-HARDWARE-LAB-TEST-PLAN.md`, so this kit uses the sprint id `LT-X86-07459` (the model number), as the Dell 5540 kit does. Rename it if Zeus prefers another.

> **UNVERIFIED.** Nothing here has run on this exact machine. The model details (32 GB RAM, 1 TB storage, made 2017) come from the founder's note, not from a datasheet. Every "expect" is what the build notes and tests say; write down what differs.

> **Explain it like I'm the founder.** The Beelink (8 GB) is too small to be the hub. The Dell all-in-one (32 GB, 1 TB) is the daily hub, and the lab server joins it as a **worker** (a machine that runs apps for the hub but cannot see its admin keys). You check the Dell from a live USB first (so you do not erase a machine that cannot work), install OneMind from the installer stick, sign in, then join the lab server. **The install erases the Dell's internal disk.**

## What you need
- The Dell, its keyboard and mouse, a **wired** network cable to the router your Mac is on.
- A **4 GB+ USB stick** for the OneMind installer, and a second stick with any **Debian 13 live** image (for step 1). Debian live images: <https://www.debian.org/CD/live/>.
- Your Mac with the newest `dev-*` pre-release files from <https://github.com/onemindos/ONEMINDOS/releases>.
- This repo on the Mac. Copy the folder `lab-kits/LT-X86-07459` onto a third small stick (or the live stick's data partition if it has one) so the Dell can run the check script.

## 1. Pre-install check (from the live USB, before erasing anything)
1. Boot the Dell from the Debian live stick. Open the BIOS with **F2** at power-on, and the one-time boot menu with **F12** (UNVERIFIED for this model: Dell usually uses these; if not, watch the on-screen hint).
2. In the BIOS (page names vary), write down: BIOS version, **Boot mode = UEFI** (not Legacy), **Secure Boot = Disabled**, SATA mode (AHCI is best; "RAID On" can hide the disk from Linux, so switch to AHCI if the disk is missing later). Save with **F10**.
3. In the live system open a terminal, mount the small stick, and run:
   ```bash
   sh /path/to/LT-X86-07459/preinstall-check.sh | tee precheck.txt
   ```
   It is read-only and prints no serial numbers or addresses. It ends with `READY`, `WARN` or `NOT-READY`.
4. What it checks, and how to read each by hand if you want to see it yourself:

| Check | By hand | Needs |
|---|---|---|
| CPU model and x86-64 level | `lscpu \| grep 'Model name'`; `/lib64/ld-linux-x86-64.so.2 --help \| grep supported` lists `x86-64-v2 (supported, searched)` lines | **x86-64-v2 or better** (v1 chips lack instructions modern Debian builds use) |
| Memory | `free -h` | more than 8 GiB (target 32) |
| Disk type | `lsblk -d -o NAME,ROTA,SIZE,MODEL` (`ROTA 1` = spinning hard disk, `0` = SSD or NVMe) | 32 GiB or more; **SSD recommended** |
| UEFI mode | `ls /sys/firmware/efi` exists | UEFI |
| Secure Boot / TPM | `mokutil --sb-state` (if installed); `ls /sys/class/tpm` | Secure Boot **off** for dev builds; a TPM is not needed yet, write it down |
| Wired Ethernet | `ip -br link` shows a non-`wl` port; `UP` with the cable in | wired link up |

5. **If the disk is a hard disk (ROTA 1): fit an SSD before installing.** OneMind runs k3s (the app scheduler), a database and the update system on one disk. They do many small writes, and a spinning disk answers those about 100 times slower than an SSD, so the dashboard feels stuck and the 5-minute boot checks in the pass table can time out. A 1 TB SATA SSD is cheap. The 2017 all-in-one models are usually opened from the back or bottom and the drive swaps like a laptop drive (UNVERIFIED for this model: check the service manual first).
6. `NOT-READY` on CPU level, UEFI or disk size: stop and send `precheck.txt`. `WARN` is your call; note each in the results.

## 2. Install from the installer image
Follow **sections A to D of [../LT-X86-01/INSTALL-BEELINK.md](../LT-X86-01/INSTALL-BEELINK.md)** with these changes:
- The target is the Dell's internal disk. Boot menu key: **F12** (UNVERIFIED).
- BIOS settings: Secure Boot **Disabled**, boot mode **UEFI**, USB boot enabled (you already set these in step 1).
- Pick the **internal** disk by size (about 1 TB) and model, not the stick. Role: **`hub`**. Name: for example `OneMind`. Type `ERASE`.
- If the all-in-one has no extra USB ports free for the keyboard and stick at once, use a USB hub.

## 3. First boot, owner sign-in and the box's own screen
1. After the reboot (pull the stick) wait a few minutes. The built-in display shows `ONEMIND-FIRSTBOOT:` lines and a line `ONEMIND OWNER TOKEN:`. **Photograph or copy the token now; it is shown once.** Never write it into the results.
2. The local screen (UX-07 part 1, #242, `onemind-screen.service` on tty1) is a **text console, not a graphical desktop**. For a hub it should show, in order: `ONEMIND IS STARTING` (first start takes a few minutes), then `ONEMIND IS RUNNING` with a line "Open the dashboard on a phone or computer on this network", the box's address, a QR code of that address, and "Sign in with your owner token". It never draws the token. Expect no mouse pointer and no browser: the kiosk dashboard is not built yet.
   - **Known difference to watch:** the screen prints `http://<address>:8080/`, but for a hub plain HTTP on `:8080` listens on the box itself only. From the Mac use `https://onemind.local` (or `https://<dell-ip>`) as in the Beelink kit. Write down whether the QR and the address on screen worked from your phone. That is a finding for #242, not a failure of this kit.
   - All-in-one displays can go blank or show a different resolution on a text console: note it.
3. From the Mac, open `https://onemind.local`, accept the box CA warning (check the fingerprint on screen), and sign in with the owner token.

## 4. Join the lab server as a worker
The lab server runs Proxmox, so the worker is a **Debian 13 virtual machine** on it (4 vCPU, 8 GB RAM, 40 GB disk, bridged to the same LAN, UEFI). Hub-side and worker-side steps are the ones documented for main (`deploy/install.sh`, issue #234); the exact Proxmox VM wizard clicks are UNVERIFIED.
1. On the **Dell hub**, make a one-time code (it works once and expires after 15 minutes):
   ```bash
   read -rs ONEMIND_TOKEN && export ONEMIND_TOKEN     # paste the owner token (not shown)
   onemind fabric ticket                              # prints onemind-join:v1?...
   ```
   Or use **Add a device** on the dashboard.
2. In the VM (fresh Debian 13, this repo checked out), as root:
   ```bash
   sudo deploy/install.sh --role node --join 'onemind-join:v1?...'
   ```
   Keep the single quotes. If the VM cannot find the hub by its `.local` name, add `--hub-addr <the Dell's LAN IP>`. The VM must reach the hub on ports 6443 and 4222.
3. The script waits. On the hub dashboard open **Approvals**, check that the code matches, and approve (or `onemind fabric approve`). Nothing joins without this.
4. Within about 10 seconds the VM appears on **Nodes** as a worker.

## 5. Pass checks
Every line needs a yes without touching the Dell after the install reboot.

| # | Check | Pass looks like |
|---|---|---|
| 1 | Pre-install check | `precheck.txt` ends `READY` or `WARN` with every warning noted |
| 2 | Stick verified, booted, install wrote and checked | `shasum` OK, menu shows the 1 TB disk, `verified sha256=` seen |
| 3 | Restart into OneMind alone | After pulling the stick, `ONEMIND-FIRSTBOOT:` lines appear |
| 4 | Owner token shown once | `ONEMIND OWNER TOKEN:` seen on the built-in display |
| 5 | Local screen | `ONEMIND IS RUNNING`, an address and a QR code on the built-in display; no token drawn |
| 6 | Dashboard from the Mac | Loads within 10 minutes of the reboot; the token signs in; Home shows the Dell online as `hub` |
| 7 | Worker joined | Nothing joined before you approved; after approval the VM shows on Nodes as a worker |
| 8 | Power cycle | Hold the power button, power on again, wait 5 minutes: dashboard loads, same token signs in, the worker is back on Nodes without a new code |
| 9 | Memory headroom | After first boot and the worker joining, the dashboard (or `free -h`) shows more than 20 GiB available |

**PASS** = all 9. **BLOCKED** = a firmware or boot-menu problem (record the behaviour and BIOS version). **FAIL** = anything else after one clean retry.

## 6. If it fails
| You see | Try |
|---|---|
| Live stick does not boot | F12, pick the USB entry; Secure Boot off; boot mode UEFI. Still no: BLOCKED, photograph the BIOS pages |
| Check says no internal disk | Set SATA mode to AHCI in the BIOS and re-run |
| Check says Legacy boot | Switch the boot mode to UEFI; the installer cannot boot Legacy |
| CPU below x86-64-v2 | Stop: the image will not run on this chip. Send `precheck.txt`; the Dell cannot be the hub |
| Hard disk, slow install or dashboard timeouts | Fit an SSD (step 1.5) and retry |
| Black screen after GRUB | Wait 2 minutes; photograph; note BIOS version. All-in-one panels can need a different video mode: BLOCKED with the photo |
| Built-in display blank but the network works | Use the Mac dashboard; note it for #242 |
| `onemind.local` not found | Use `https://<dell-ip>` (look it up in the router's device list) |
| Join waits forever | The code expired (15 min) or the hub was not approved: make a new code. Check the VM reaches the hub on 6443 and 4222 |
| `FAILED` or "check failed" in the installer | Do not use the disk. Write the stick again and retry once |
| Token missed | Re-run the install (the box stores only a hash); this is a test box |

## 7. Record
Copy [RESULT.template.md](RESULT.template.md) (based on `../common/RESULT-TEMPLATE.md`) to `research-output/evidence/lab/founder-hardware/LT-X86-07459.md`. No serial numbers, MAC addresses, your home IP, hostnames, the owner token or home paths. Run `sh lab-kits/common/redact.sh` over any pasted log and `make hygiene` before committing.
