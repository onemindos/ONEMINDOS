<!-- Copied verbatim from research-output/22-HARDWARE-LAB-TEST-PLAN.md (LT-JET-01), 2026-11-11. Do not edit: if 22 changes, re-copy. -->

### LT-JET-01 · NVIDIA A/B with the OneMind gate, OTA and power cuts · **G**
**Aliases:** T-W3-06 (extended, DC-07 Result block), LAB-W7-4, Q6, Q47, Q58 · **Time:** about 1 day
1. Flash JetPack 6.2.x with the **redundant (A/B) rootfs layout** (A/B is set at the factory flash, REC-DEC-18 `ROOTFS_AB=1`). Record `cat /etc/nv_tegra_release` and `sudo nvbootctrl dump-slots-info`.
2. Put the OneMind gate in `l4t-rootfs-validation-config`; install a bad update → **Pass:** gate failure falls back to the good slot.
3. Image-based OTA from JetPack 6.2.x (r36) to JetPack 7.2.x (r39); **cut power during the capsule/OTA update** → **Pass:** OTA resumes or falls back; no reflash. **Rev. 4 (DC-08 refuters):** the same r36 → r39 step must also run **unattended, with no console, with `/data` kept**, and record the QSPI bootloader version before and after. The DC-08 refuter found no documented console-free r36 → r39 path that also moves QSPI on production modules. The claim needs a **production Orin NX module** (not in the Day-1 order); the dev kit run is a rehearsal and is recorded as such.
4. Corrupt slot B → **Pass:** boots A; `nvbootctrl dump-slots-info` shows the expected slot.
5. Extensions from the refuters: **cold power cycle after a hang** (NVIDIA's retry counter ignores cold resets [C-REF3-DC-technical-001]); a root mount failure with the watchdog armed; after OTA, assert the running version equals the bundle's.
6. *(rev. 4, E10)* Record the QSPI firmware version in the release manifest and refuse an OS bundle built for another QSPI version (REC-DEC-47).
- **Fail → consequence:** hook cannot block the commit, or a USB reflash is needed → **DC-07 flip condition**: Jetson SKUs need NVIDIA's recovery process or a CRA period limited to one branch; REC-DEC-35 items become release blockers. **Until step 3's r36 → r39 run passes on a production module, every Jetson SKU declares its support period from its current branch only** (DC-08, REC-DEC-49).
