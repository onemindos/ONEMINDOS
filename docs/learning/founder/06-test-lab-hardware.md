<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 06: the test lab, machine by machine

**Date:** 2026-11-17 · **Asked by:** Zeus ("pick the best machine to test the OS live … confirm this, no assuming").
**Follows:** D-004 (use the hardware that exists, buy in phases). This note adds the machines Zeus listed on 2026-11-17 to that inventory. It changes no decision.
**Ties to:** M-LIVE live tests after the sprint, #242 (local screen), #149 / #318 (grow `/data`), #322 (CPU level), #281 (VMs), #148 (Secure Boot), the LT-X86 kits in `research-output/22-HARDWARE-LAB-TEST-PLAN.md`.

> **In plain words.** Keep **one server, the R530**, and run Proxmox on it. Proxmox is a system whose only job is to run virtual machines (VMs: whole computers simulated in software). Put every OneMind image on it as a VM. Test the real product on **real machines** too: the **Dell laptop** (Secure Boot and the TPM security chip), the **Dell all-in-one** (its own screen, 32 GB, VMs inside OneMind) and the **Beelink** (the old, small box). The **Mac** builds and tests the arm64 image. Sell the R610; the R320 and R510 are optional.

---

## 1. The decision table

| Machine | Verdict | Its job | Why |
|---|---|---|---|
| **Dell PowerEdge R530** | **Keep, always on** | Proxmox VE 9: every OneMind image as a VM, multi-node tests, Home Assistant in a VM | The newest server here. Xeon E5-2600 v3/v4, the only server CPUs here with AVX2, which is x86-64-v3 [1][2][3]. DDR4, up to 384 GB [4] |
| **Dell Latitude 5540** (laptop) | **Keep: main real-hardware x86 box** | Secure Boot (#148), TPM, A/B rollback on metal. OneMind boots from a USB SSD, so Windows stays | Already the main x86 test box in D-004 / `docs/HARDWARE.md`: i5-1345U, TPM 2.0, Secure Boot with a custom key mode [HW] |
| **Dell all-in-one** (32 GB, model to record) | **Keep: bare metal** | Local screen (#242), real-disk grow (#318), **VMs inside OneMind (#281)**, the "big box" | It has its own screen, and 32 GB meets #281's 16 GB floor |
| **Beelink U55** (8 GB) | **Keep: bare metal**, after Home Assistant moves to the R530 | The old, minimum-spec box; second node for join tests | Its D-004 role. 8 GB is above the 4 GB k3s floor (`research-output/11-hardware-line.md`) |
| **Mac** | Keep | Development, the CI runner (#303/#305), the **arm64-efi** image in a VM | Apple silicon runs arm64 VMs natively |
| **Dell PowerEdge R320** | Optional; boot when needed | A real server for the old-CPU test (#322) | Xeon E5-2400 or E5-2400 v2: AVX but no AVX2 [5][6]. A Proxmox VM with CPU type `x86-64-v2-AES` gives the same test on the R530 [3] |
| **Dell PowerEdge R510** | Optional; sell if unused | A plain Debian backup target (restic) | 2U, up to 8 or 12 drive bays depending on chassis [7]. Xeon 5500/5600 and DDR3 [7] |
| **Dell PowerEdge R610** | **Sell** (wipe the disks first) | Nothing the R530 can't do better | 1U, six 2.5" bays, Xeon 5500/5600, DDR3 (up to 192 GB) [7]. Measured idle: 60–63 W bare to about 140 W configured [8] |

**Correction to the chat answer:** the R610 and R510 **do** boot UEFI. Dell's manuals for both describe a Boot Mode switch between BIOS and UEFI [9]. That is not a reason to keep them: their age, DDR3 RAM and power draw are.

## 2. Flags (nothing changed; Zeus decides)
1. **#281 step 1 names the Beelink** for the LT-MACH-2 measurement, but the feature itself only installs on x86 hubs with **at least 16 GB**, and the Beelink has 8 GB. Running LT-MACH-2 on the **all-in-one** (32 GB, bare metal) covers both the measurement and the done-when boxes. Nested KVM inside a Proxmox VM would measure the wrong thing.
2. **The all-in-one is not in the inventory** (`docs/HARDWARE.md` §1). Its model, CPU, TPM and Secure Boot support are unknown. Run the LT-X86-00 commands on it (§4).
3. **The R530 does not replace the buy list.** The reference Lite box (N150 / i3-N300, 16 GB) and the Pi 5s (#214) are still the shipping targets. The R530 is a lab, not a product.

## 3. The R530 upgrade (only if the iDRAC check says it is needed)
| # | What | Why | Rough cost (asking prices, Nov 2026; check eBay's *sold* filter) |
|---|---|---|---|
| 1 | **RAM to 128 GB**: 4 × 32 GB DDR4 RDIMM, PC4-2400T-R or PC4-2133P-R, 2Rx4, 1.2 V | About 10 OneMind VMs plus Home Assistant | Used 32 GB sticks list at about $18–60 each [10] |
| 2 | **SSDs for the VMs**, if it only has spinning disks | VMs on hard drives boot slowly and make tests flaky | Price at purchase |
| 3 | **E5-2600 v4 CPUs**, only if it has v3 | A little faster and cooler; the R530 takes both [1][2] | Price at purchase |
| — | Skip: a GPU for AI | It is a 2014–2016 platform. Local AI runs better on the Mac; the GPU box is on the HARDWARE.md "Later (Pro)" list | $0 |

R530 memory rules [4]: 12 slots; **8 usable with one CPU**, all 12 with two; RDIMM and LRDIMM never mixed. Proxmox VE 9.0 is built on Debian 13, the same base as OneMind (D-007) [11]. Home Assistant OS runs on Proxmox from its official KVM (qcow2) image [12].

## 4. Before buying anything: record each machine
Boot each one from a Debian 13 live USB and run the LT-X86-00 block (`research-output/22-HARDWARE-LAB-TEST-PLAN.md` §3): `lscpu`, `grep MemTotal /proc/meminfo`, `lsblk -d -o NAME,ROTA,TRAN,SIZE`, `systemd-analyze has-tpm2`, `mokutil --sb-state`. Do **not** record serial numbers in the repo. For the R530 the iDRAC page shows the CPUs, memory and disks without booting anything. Its power page shows live watts.

## 5. Which image goes where (from `os/boards/`)
| Order | Image | Machine |
|---|---|---|
| 1 | `vm` | R530 Proxmox: boot, A/B update, rollback, health gate, with snapshots |
| 2 | `installer-x86_64` → `x86_64-efi` | Beelink, then the all-in-one: the customer path (USB, install, first boot, phone setup) |
| 3 | `x86_64-efi` from a USB SSD | Latitude 5540: Secure Boot and TPM |
| 4 | `cloud-proxmox` template | R530: clone 3 or 4 and join them to a bare-metal hub, for a real multi-machine OneMind |
| 5 | `arm64-efi` | Mac |
| Later | `rpi5`, `jetson-orin`, `cloud-aws/azure/gcp`, `vm-do`, `cloud-hetzner` | Pi 5 (#214), a Jetson, real cloud accounts. `vm-do` and `cloud-hetzner` boot BIOS (SeaBIOS) and can be smoke-tested on Proxmox |

Each image comes from the latest green `image` run on `main` (artifact `image-debian-<board>`).

## Check yourself
1. Why is a VM not enough to test #318 and #148? (A VM fakes the disk, the firmware and the TPM.)
2. Why does the R320 matter for #322 even though the R530 is faster? (It has no AVX2, so it shows OneMind refusing an app the CPU can't run. A Proxmox CPU type can fake the same thing.)
3. Which machine runs LT-MACH-2 for #281, and why not the Beelink?

## Sources
- [HW] `docs/HARDWARE.md` §1 and `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §3 (Latitude 5540 and Beelink U55).
- [1] Dell, PowerEdge R530 spec sheet (E5-2600 v3 at launch): https://i.dell.com/sites/doccontent/shared-content/data-sheets/en/Documents/DE9CHNE47509-PowerEdge-R530-Spec-Sheet.pdf
- [2] StorageReview, Dell PowerEdge 13G R530 review: https://www.storagereview.com/review/dell-poweredge-13g-r530-review
- [3] Proxmox VE manual, "QEMU/KVM Virtual Machines", CPU types: x86-64-v2-AES works from Intel Westmere, x86-64-v3 from Intel Haswell: https://pve.proxmox.com/pve-docs/chapter-qm.html
- [4] Kingston, PowerEdge R530 memory: https://www.kingston.com/en/memory/search/model/90887/dell-alienware-poweredge-r530
- [5] Dell R320 spec sheet (third-party copy): https://www.xbyte.com/content/PDF/Dell-PowerEdge-R320-Spec-Sheet.pdf
- [6] Intel, Xeon E5-2600 v2 technical overview (Ivy Bridge: AVX, no AVX2): https://www.intel.com/content/dam/develop/external/us/en/documents/intel-xeon-processor-e5-2600-v2-product-family-technical-overview.pdf
- [7] Dell R610 and R510 spec sheets (third-party copies): https://www.xbyte.com/content/PDF/Dell-PowerEdge-R610-Spec-Sheet.pdf, https://www.xbyte.com/content/PDF/Dell-PowerEdge-R510-Spec-Sheet.pdf
- [8] SPECpower_ssj2008, PowerEdge R610: https://www.spec.org/power_ssj2008/results/res2010q2/power_ssj2008-20100504-00258.html; configured measurement: https://lonesysadmin.net/2010/05/13/power-consumption-of-a-dell-poweredge-r10
- [9] Dell R610 UEFI deployment guide: https://www.manualowl.com/m/Dell/PowerEdge-R610/Manual/189646?page=6; Dell community, R510 UEFI: https://www.dell.com/community/en/conversations/poweredge-hardware-general/poweredge-r510-uefi-support/647f87b9f4ccf8a8de6f6fcd
- [10] Example listings: https://ubbcentral.com/store/item/Lot-of-6-Micron-32GB-2Rx4-PC4-2400T-RB2-11-Server-Memory-ECC-RDIMM-DDR4-288-pin_276559352415.html, https://www.ebay.com/itm/235613843419
- [11] Proxmox, VE 9.0 press release: https://www.proxmox.com/en/about/press-releases/proxmox-virtual-environment-9-0
- [12] Home Assistant community guide, HA OS on Proxmox 9 (official image link on https://www.home-assistant.io/installation/alternative): https://community.home-assistant.io/t/installing-home-assistant-os-using-proxmox-9/201835

**UNVERIFIED until the machines are checked:** the R530's actual CPUs, RAM and disks; everything about the all-in-one except its 32 GB; whether this Beelink is the i3-5005U (one source says N100).
