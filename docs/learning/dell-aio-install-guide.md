<!-- SPDX-License-Identifier: Apache-2.0 -->
# Install OneMind on the Dell all-in-one: a guide for a first-time owner

**Serves:** #234 (M-LIVE, OneMind running live on real hardware), D-007 (Debian 13 base), D-019 (Secure Boot, dev keys for now), D-020 (disk encryption), D-028 (recovery). **Founder-requested** (the Dell is the daily hub).
**Status:** UNVERIFIED on the real machine. Every "expect" below comes from the repo's build notes and QEMU test criteria, not from a run on this Dell. Write down anything that differs.
**Companions:** the model-specific kit [`lab-kits/LT-X86-07459/`](../../lab-kits/LT-X86-07459/README.md) (pre-install check, pass table), the hardware check [`scripts/hw-check.sh`](../../scripts/hw-check.sh) with its [checklist](../../lab-kits/LT-X86-07459/HW-CHECKLIST.md), and the [file-system readiness conditions](dell-aio-file-conditions.md) that must pass before real files go on the box.

> **In plain words.** You download one installer file on your Mac, check that it is genuine, copy it onto a USB stick, tell the Dell's firmware (the BIOS, the small program that runs before any operating system) to start from that stick, and answer three questions on screen. The Dell then erases its own disk and becomes a OneMind box. You sign in from your Mac with a one-time secret, and you print a recovery kit so a dead disk or a lost phone is never the end of your data. **The install erases the Dell's internal disk.** Do not put real files on it until the readiness conditions pass.

Terms: **UEFI** is the modern firmware mode (the installer needs it, not the old "Legacy" mode). **Secure Boot** makes the firmware refuse unsigned boot files; development builds are not signed yet, so it stays off for now. **TPM** is a small security chip that holds the key to the encrypted data disk. **Owner token** is the long secret that proves you own the box. **Slot A/B** are the two copies of the operating system, so a bad update can roll back.

## 0. What you need
- The Dell, a USB keyboard and mouse, and a **wired** network cable to the same router as your Mac. Use a USB hub if the all-in-one has too few ports.
- A USB stick of 4 GB or more that you can erase, and your Mac.
- The internal disk must be 32 GiB or larger. An **SSD** is strongly advised: a spinning disk makes the dashboard crawl and can fail the 5-minute boot checks ([kit step 1.5](../../lab-kits/LT-X86-07459/README.md)).
- A printer, or a pen and paper, for the recovery kit (step 9).

## 1. Download the installer from a green build
Use a build whose checks are all green, so you never install something CI did not accept.

1. Open the repository's **Releases** page and take the newest `dev-*` pre-release, or open the latest green run of the **image** workflow on `main` and download the artifact `installer-debian-x86_64` (it is kept 14 days). You need two files: `onemind-installer-amd64-<version>.img.xz` and `SHA256SUMS`.
2. If the newest run is red or still running, wait or take the previous green one. Write the release tag or run number down for the results file.

## 2. Verify the download
In the folder that holds both files:
```bash
shasum -a 256 -c SHA256SUMS --ignore-missing
```
Expect `onemind-installer-amd64-<version>.img.xz: OK`. Anything else means a damaged or tampered file: download again and do not use it.

## 3. Write the USB stick (Mac)
1. Plug the stick in and find its number with `diskutil list external`. It is `/dev/diskN`. **Your Mac's own disk is `disk0` or `disk1`; never use those.**
2. Run the safety check from the repo root (it writes nothing and asks you twice): `sh lab-kits/common/check-target-disk.sh /dev/diskN`.
3. Write it: easiest is [balenaEtcher](https://etcher.balena.io/) (pick the `.img.xz`, pick the stick, Flash). Terminal alternative:
   ```bash
   diskutil unmountDisk /dev/diskN
   xz -dc onemind-installer-amd64-<version>.img.xz | sudo dd of=/dev/rdiskN bs=4m
   diskutil eject /dev/diskN
   ```
   macOS may say the disk is unreadable afterwards. That is normal; click Eject.

## 4. BIOS settings on the Dell
Power on and tap **F2** to open the setup (UNVERIFIED for this model; Dell usually uses F2, and **F12** for the one-time boot menu). Menu names vary; photograph each page you change. Set only these:

| Setting | Value | Why |
|---|---|---|
| Boot mode | **UEFI** (not Legacy or CSM) | The image boots with GRUB EFI. |
| Secure Boot | **Disabled** for now | Development builds are unsigned. D-019 plans signed images with OneMind's key later; turning Secure Boot on changes what the TPM measures (PCR 7), so settle this before the box holds real files. |
| TPM | **On** (Dell often calls it "TPM 2.0 Security" or "PTT") | With a TPM the data disk is encrypted and unlocks by itself after a restart (D-020). Without one it stays unencrypted. |
| SATA mode | **AHCI** (not "RAID On") | "RAID On" can hide the disk from Linux. |
| USB boot | Enabled | To start from the stick. |
| Boot order | USB first for the install; **internal disk first afterwards** | See steps 5 and 6. |

Write down the BIOS version (first page). Save and exit (usually **F10**). If a later step fails because of any of these, see step 11.

## 5. Boot the installer
1. Plug in the stick, cable, keyboard and mouse. Power on and tap **F12**; pick the entry that names your USB stick (for example "UEFI: <brand>"). If F12 does nothing, set the stick first in the BIOS boot order.
2. GRUB shows for about 3 seconds, then Linux starts. No login prompt appears: the installer menu starts by itself.
3. Expect `OneMind installer: writes OneMind <version> (x86_64-efi) to a disk of this computer.` and a numbered disk list. The stick, read-only disks, mounted disks and disks under 32 GiB are shown as `not offered`. If your internal disk is missing, stop, photograph the screen, and check the SATA mode.

## 6. Install
1. Type the number of the **internal** disk (compare the size, about 1 TB, and the model; it is not the stick) and press Enter.
2. Role: type `hub` (the owner's main box; it shows the owner token on its own screen). Name: press Enter for `OneMind`.
3. A red warning names the disk. Type `ERASE` and Enter. Anything else writes nothing.
4. Wait 5 to 15 minutes. Expect progress lines and then `verified sha256=...`, then a countdown and a restart. **Pull the stick when it says so.** Set the boot order to the internal disk first if the Dell tries the stick again. A line with `FAILED` means do not use the disk: write the stick again and retry once.

## 7. First boot
1. Wait a few minutes. The screen prints `ONEMIND-FIRSTBOOT:` lines. The first start makes the box's own certificate authority and starts k3s and the gateway.
2. **With a TPM**, the first boot also prints a data-disk recovery key on the screen: a line `ONEMIND-DATA-CRYPT: RECOVERY KEY` followed by eight groups of eight letters. It is shown once and the box does not keep a copy. **Photograph the screen now**, then go to step 9.
3. The screen then prints a line `ONEMIND OWNER TOKEN:` and the token. **Photograph it now.** It is shown once; the box stores only a hash. Never paste it into a chat, a commit or the results file.
4. Without a TPM, the first boot instead says `making it plain btrfs, NOT encrypted`. That is allowed (D-020) but it is a finding for this machine: note it, and re-check the BIOS TPM setting.
5. The box's own screen is a text console, not a desktop, and the kiosk dashboard is not built yet (kit section 3). A blank or oddly sized all-in-one panel is worth a photo for #242.

## 8. Owner setup
1. On your Mac (same network) open `https://onemind.local`, or `https://<dell-ip>` if the name is not found (look the address up on the Dell's screen or in your router's device list). Use `https`, not `http:8080`.
2. The browser warns about the certificate: that is the box's own CA. Check that the fingerprint matches the one on the Dell's screen, then continue.
3. Sign in with the owner token. The Home screen should show the Dell online with the role `hub`.
4. Register a **passkey** (the sign-in page, "Add passkey") so you no longer depend on the token, and confirm the kit when the setup asks (step 9). Setup choices you can change later are owner actions that go through the approval queue; the AI never acts without your approval (D-027, D-028).

## 9. Print the recovery kit
Do this **before** real files arrive and before you leave the box. Two different secrets matter. The repo documents both; whether the dashboard has a print button yet is UNVERIFIED.

| Secret | Where you get it | What it unlocks |
|---|---|---|
| **Data-disk recovery key** (eight groups of eight letters) | Printed once on the Dell's screen at first boot (TPM boxes), step 7.2 | The encrypted data disk if the TPM does not release the key, for example after a BIOS change, a moved disk or a new motherboard (D-020, D-028). |
| **Emergency kit** (thirteen groups of four characters plus a check group) | Shown once when you set up backups (the Backups screen shows its status); you type two groups back to prove you saved it | Your backups, with the free tool `restic`, even without a OneMind box ([BACKUPS.md](../leap/core/BACKUPS.md) section 3.2). |

How to keep them:
1. Write or print **both**, on paper. If you print from the Mac, print the text you typed or photographed, not a file synced to a cloud drive; a shared network printer keeps a copy of the job on its disk, so use a printer you trust (an unverified precaution, not a repo rule).
2. Make **two copies and keep them in two places away from the box** (for example a drawer and a relative's house). The box never stores either key (D-028: reading, exporting, restoring and unlocking never depend on a key the box alone holds).
3. Practice once: the readiness conditions ([conditions 3 and 4](dell-aio-file-conditions.md)) have you prove the printed key works on this machine.
4. If you lose the kit while the box works, make a new one and destroy the old copies. A new kit adds a key; it does not remove the old one.

## 10. Rescue console and a first hardware check
The **rescue console** is a small page on the box that keeps working when the apps are down ([help page](../../os/rootfs/layers/onemind/usr/share/onemind/help/rescue.html)). Open `https://<dell-ip>:7443` from a computer on the home network; type any user name and use the owner token as the password. It shows slots A and B, lets you **roll back** to the other slot (type `rollback`), and downloads the recent logs. A root terminal exists but is off by default and needs a fresh passkey step (`docs/security/rescue-terminal.md`). Bookmark the address and test it once while everything works.

Then run the read-only hardware check from your Mac, as the owner (the exact steps and what each line means are in the [hardware checklist](../../lab-kits/LT-X86-07459/HW-CHECKLIST.md)):
```bash
ssh <owner>@onemind.local 'sh -s' < scripts/hw-check.sh | tee hw-check.txt
```
It changes nothing and masks serial numbers and addresses. Expect some `SKIP` lines where the image does not ship a tool yet (for example `vainfo`, PipeWire or CUPS): that is a finding for the build, not a fault in your Dell.

## 11. If it does not work
| You see | Try |
|---|---|
| The stick does not boot | F12, pick the USB entry; Secure Boot off; boot mode UEFI. Still nothing: BLOCKED, photograph the BIOS pages |
| No internal disk offered | SATA mode to AHCI; the disk may be under 32 GiB or mounted |
| Boots the old system | F12 and choose the USB entry; check the boot order |
| Black screen after GRUB | Wait 2 minutes. All-in-one panels can need another video mode: BLOCKED, photograph it, note the BIOS version |
| `onemind.local` not found | Use `https://<dell-ip>` |
| The data disk asks for a key after a BIOS change | Type the printed data-disk recovery key (step 9). This is the TPM doing its job: the boot state changed |
| Token missed | Reinstall (the box stores only a hash). Fine on a test box; with real files on it, use the recovery path instead of reinstalling |
| `FAILED` in the installer | Do not use the disk: rewrite the stick and retry once |

## 12. Record and then check the file system
Fill [`RESULT.template.md`](../../lab-kits/LT-X86-07459/RESULT.template.md) and file it under `research-output/evidence/lab/founder-hardware/` with no serial numbers, MAC addresses, home IP, owner token or home paths (`sh lab-kits/common/redact.sh`, then `make hygiene`). Then go through [the readiness conditions](dell-aio-file-conditions.md). **Only when all nine pass do real files go on the Dell.**
