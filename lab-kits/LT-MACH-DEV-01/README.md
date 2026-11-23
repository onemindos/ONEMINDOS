# LT-MACH-DEV-01 · A spare GPU and a USB device handed to a machine, on real VT-d hardware

**Status:** kit-ready (blocked: founder-hardware, and machines stay gated off until LT-MACH-2 passes) · **Time:** about 1 hour · **Issue:** #690 (part of #281, MACH-01) · **Needs:** LT-MACH-2 done on the same box

> **Explain it like I'm the founder.** A virtual machine can be given a real device of your box: a
> graphics card for a Windows game machine, or a USB stick or radio. The machine then owns it
> completely, and your box cannot use it while the machine runs. OneMind only does this when you
> approve it, refuses a device your box is using until you say "yes, take it", and refuses a
> graphics card that is wired together with other parts of the board (its *IOMMU group*), because
> those parts would go to the machine too. The tests in CI prove the rules; this kit proves that a
> real card really shows up inside a real machine.

**Words.** *IOMMU* is the chip feature (Intel calls it VT-d, AMD calls it AMD-Vi) that walls a device
off so a machine can use it without reaching the rest of your memory. An *IOMMU group* is the set of
devices the board cannot wall off from each other: they are passed through together or not at all.
*vfio-pci* is the Linux driver that holds a card for a machine instead of using it for the screen.

## What you need
- The x86 box of LT-MACH-2 with machines turned on, and a **spare** PCIe graphics card in a second
  slot (not the one your screen is plugged into).
- A USB stick you can erase, and a monitor for the machine's console (the dashboard's console works).

## Steps
1. **Firmware.** In the BIOS, turn on VT-d (Intel) or SVM plus IOMMU (AMD). Boot OneMind.
2. **Does the box see an IOMMU?** In the dashboard (or `GET /v1/machines/<name>/devices`), the box
   must say `"iommu": true`. If it says false, step 1 did not take.
3. **Free the spare card.** On the box, as root (lab only):
   ```bash
   lspci -nn | grep -Ei 'vga|3d|audio'          # note the card's address and its vendor:device id
   ls /sys/kernel/iommu_groups/*/devices/        # the card's group must hold only its own functions
   driverctl set-override 0000:01:00.0 vfio-pci  # use your card's address; repeat for its .1 audio function
   ```
   The devices list must now show the card with `"busy": false` and no refusal. A card that shares
   its group with another device shows `iommu_group_shared`: move it to another slot and repeat.
4. **Grant it.** Ask for `machine.attach_device` with `{"name": "<machine>", "kind": "gpu", "device": "<address>"}`
   and approve it in Approvals. The result says the device moves at the next start.
5. **Start the machine** and check inside it that the card is there (Windows: Device Manager; Linux: `lspci`).
6. **USB.** Plug in the stick. The devices list shows it `busy` (`usb-storage`). Ask without
   `confirm_busy`: refused. Ask again with `"confirm_busy": true`, approve, restart the machine, and
   check the stick appears inside it and is gone from the box.
7. **Give both back** with `machine.detach_device`, restart the machine, and check the box has them again.

## What KubeVirt is told (UNVERIFIED on our pinned KubeVirt until this kit runs)
The gateway writes `spec.configuration.permittedHostDevices` on the KubeVirt CR (`pciHostDevices` by
vendor:device id, `usb` by vendor and product) and the machine's `spec.template.spec.domain.devices.gpus`
and `hostDevices`, following the KubeVirt user guide, "Host Devices Assignment":
https://kubevirt.io/user-guide/compute/host-devices/ . If the pinned release needs the `HostDevices`
or `GPU` feature gate, record it below; turning it on belongs in the machines extension's KubeVirt CR.

## Result
| Step | Expected | Seen | Pass |
|---|---|---|---|
| 2 | `iommu: true` | | |
| 3 | card free, no refusal | | |
| 4-5 | card inside the machine | | |
| 6 | busy refused, confirmed grant works, stick inside the machine | | |
| 7 | both back on the box | | |
| feature gates | which, if any | | |
