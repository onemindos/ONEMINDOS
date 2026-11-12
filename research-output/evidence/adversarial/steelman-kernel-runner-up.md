# Runner-up steelman: K2, "own the kernel config on an upstream LTS, the Home Assistant way"

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the runner-up. It is advocacy held to the evidence rules. Every fact below was opened on 2026-11-10 (claim IDs `C-STEEL-KRU-###` in `evidence/claims/STEEL-kernel-runner-up.csv`), or is taken from this repo's ledger by claim ID, or is labelled SECONDARY or UNVERIFIED. The honest weaknesses are in §9.
- **Date:** 2026-11-11 · **Re-check by:** 2027-05-11 (kernel, BSP and PR-status facts: 6 months)
- **Verdict:** `steelman`
- **Decision under test:** S5 / DC-21 in `28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md` (§5, P0-3), confirmed in `01-FOUNDATION-DECISION.md` §3.5: **K1, the board maintainer's kernel** (Debian stock on x86_64 and generic arm64, Raspberry Pi's `linux-image-rpi-2712` on Pi 5, NVIDIA L4T on Jetson). K1 scored 71.0, K2 66.0.
- **Runner-up argued here:** **K2** as `28-…` §5 defines it (OneMind builds the kernel.org LTS with its own config fragments), in its strongest form, which this file calls **K2-hybrid**: OneMind builds 6.18 LTS with one shared fragment set for x86_64, generic arm64 and RK3588-class boards; Pi 5 uses the same fragments on mainline 6.18 or on Raspberry Pi's `rpi-6.18.y` (HAOS does the latter); **Jetson keeps NVIDIA's L4T kernel unmodified**, exactly as K1 does, with a "bring your own LTS kernel" track behind a trigger.
- **Serves requirements:** F-7, F-11, F-14, R-3, M-6, M-7, U-4, F-15

> ### Explain it like I'm the founder
> The chosen plan lets three other teams (Debian, Raspberry Pi, NVIDIA) pick your kernel. The runner-up says: for every box except Jetson, **you** pick one kernel version (the current long-term one, 6.18), build it with one written list of features, and ship it in every image. That is exactly what Home Assistant OS does today on PCs, generic ARM boards, its own Rockchip box and the Pi 5, with one person doing most of the work.
> Why it matters for you: Debian 13's kernel (6.12) **cannot run the Pi 5's I/O chip at all**, so on your smallest tier "Debian's kernel" was never really an option. The 6.18 long-term kernel can. Owning the build also means OneMind signs its own kernel modules, so NVIDIA drivers and Secure Boot work together without asking each customer to press keys on a blue boot screen. The cost is real (about one kernel update a week, a 2-year version hop, and a CI build) and §9 says where it could go wrong.

---

## 1. The claim this steelman makes

> **For every non-Jetson tier, OneMind should build one upstream LTS kernel (6.18 now) with its own CI-checked config fragments (K2-hybrid), instead of shipping Debian's 6.12 and Raspberry Pi's kernel as two separate lines. K2-hybrid gives one kernel version from Pi to server (F-14), the only route to a non-experimental-path real-time kernel on the Pi 5 tier and current industrial drivers (F-11), an actively CVE-tracked line that hops forward by image update to 2036 (R-3), a clean module-signing story for Secure Boot with NVIDIA drivers (U-4), and the same Jetson position as K1 (robotics). On the frozen weights it ties K1 rather than losing, and the tie-break evidence the run already accepted favours it.**

## 2. The run's own evidence already points at K2 on the Pi tier

| Run fact (already accepted) | Where | What it means for S5 |
|---|---|---|
| Debian trixie's arm64 kernel config (6.12.107-1) has `CONFIG_ARCH_BCM2835=y` but **no `CONFIG_MISC_RP1` and nothing for BCM2712**; RP1 entered mainline in 6.17 | `W8-P0-1-IIoT.md` counter-argument 1, accepted in `01-…` §5.8 | K1 never used "Debian's kernel" on Pi 5. K1 is really "Debian on x86, someone else on Pi". |
| Raspberry Pi's maintainers call their RT kernel "experimental … support is limited" [C-STEEL-KRU-012]; an RT-only v3d crash on Pi 5 needed upstream DRM work | same file; accepted as "Pi 5 soft real time is OneMind-owned work (G4-M1)" | Under K1, OneMind **already** builds a Pi RT kernel itself (`28-…` §6.1 row 3). K1 therefore already carries a kernel build; K2 just makes it the deliberate, shared one. |
| "A 'bring your own LTS kernel' Jetson track is a watch item" | `01-…` §5.7, FF-2 response | The run already accepts OneMind-built LTS kernels as a future direction; K2 builds the muscle now. |
| Per-SKU CRA support period "capped by the board's kernel window" | `01-…` §5.6, REC-DEC-12 | Under K1 that window is set by three vendors. Under K2 it is set by OneMind's hop discipline on x86/arm64/Pi. |
| §11.2 of `28-…` already concedes K2 gives one kernel version across x86/arm64, its own cadence, and control of config | `28-…` §11.2 | The author's case against K2 is cost and C1/C5, not capability. |

## 3. F-14: one OS from Pi to enterprise means one kernel version, not three

1. **The precedent is concrete, at a pinned SHA.** Home Assistant OS at `ab7d0f1a` (dev, 2026-11-10) builds kernel **6.18.62** for `generic_x86_64`, `generic_aarch64` and `green` (its Rockchip box), and applies the **same fragment files** (`kernel/v6.18.y/haos.config`, `docker.config`, `device-support*.config`) to all of them **and** to `rpi5_64`, which builds Raspberry Pi's tree pinned to commit `9b488bc7` [C-STEEL-KRU-001, -002]. That is the kernel contract of `28-…` §6.2, already turned into config, on four board families, by a small team.
2. **The workload is measured, and it is one person plus a bot.** In the 12 months to 2026-11-10 the x86 defconfig had 63 commits: 45 by one maintainer, 8 by a second, 7 by Renovate [C-STEEL-KRU-003]. This updates the 51-commit figure in C-W18-010 and confirms its shape: about one bump a week, mostly mechanical.
3. **Mainline 6.18 now drives the Pi 5's I/O chip.** At tag v6.18, `drivers/misc/rp1/rp1_pci.c`, `drivers/pinctrl/pinctrl-rp1.c` and `drivers/clk/clk-rp1.c` exist; `bcm2712-rpi-5-b.dts` enables RP1 Ethernet, GPIO and both USB controllers; `macb_main.c` carries a `raspberrypi,rp1-gem` config [C-STEEL-KRU-004, -005, -006]. Debian 13's 6.12 has none of this (W8 refuter). So on the LTS line K2 uses, **one upstream kernel source can boot x86, generic arm64 and a Pi 5 with network, GPIO and USB**. (Display, camera/CSI and HAT peripherals on mainline were **not checked**; HAOS still prefers the Pi fork for Pi 5, see §9.)
4. **Why one version matters to a solo founder:** a bug in cgroups, overlayfs, WireGuard, SocketCAN or the eBPF verifier reproduces the same way on the Pi greenhouse box and the Pro server. Under K1 the same OneMind image runs 6.12 (Debian) on x86 and 6.18 (`rpi-6.18.y`, the Raspberry Pi default branch [C-STEEL-KRU-011]) on Pi 5: two kernel series, two config philosophies, one product.

## 4. F-11: IoT and IIoT need a kernel OneMind controls

- **Real time.** PREEMPT_RT is a config option since 6.12 [C-W18-005] and the run's lab enabled it on 6.18.62 for both arches without patches [C-W18-067]. Under K2 the RT variant is **the same build with one more fragment** on every non-Jetson board, including the Pi 5 on the 6.18 line. Under K1 it is three different stories: Debian's RT package (x86/generic arm64 only, and not on Pi 5 [W8 refuter]), a OneMind-built Pi RT kernel anyway, and NVIDIA's RT build.
- **Industrial drivers and new hardware.** Fieldbus, CAN-FD, TSN NIC and industrial Wi-Fi drivers arrive upstream first. Debian stable stays on 6.12 for its whole life (trixie 6.12.94 at release, 6.12.116 in trixie-security today) [C-STEEL-KRU-007]. The only newer Debian kernel is trixie-backports (7.2.12) [C-STEEL-KRU-007], which is a moving non-LTS series. K2 on 6.18 LTS is two years newer than K1's x86 kernel while still being a supported LTS.
- **IEC 62443 and CRA evidence.** Both want the manufacturer to know and control its components. A kernel built from a pinned upstream tag plus versioned fragments is a precise SBOM entry with a clear upstream CVE feed. The kernel CNA assigns CVEs only for "currently being actively supported" versions and tells users "it is best to take all released kernel changes … not as individual cherry-picked changes" [C-STEEL-KRU-008]. K2 follows that advice literally. K1 does too on Debian until Dec 2028, but 6.12's upstream end (Dec 2028 [C-STEEL-KRU-009]) is 18 months before Debian 13 LTS ends (2030), after which K1's x86 kernel depends on Debian LTS backports or a series switch outside OneMind's control.

## 5. Longevity to 2036

- No route reaches 2036 on one series (`28-…` P0-4). Both routes hop. The difference is **who decides when**. Under K1, OneMind waits for Debian (a series switch inside LTS has happened once, C-W18-007) or rebases the whole OS to Debian 14. Under K2, the hop is a fragment-file exercise that HAOS did on 2026-04-20 (6.12 → 6.18, C-W18-010) and that OneMind can schedule against its own release train and each SKU's declared CRA support period.
- K2 also keeps **CIP SLTS (6.12-cip to mid-2035, C-W18-003) one config change away** for an Industrial SKU, because CIP is the same kind of build: an upstream-derived tree plus OneMind fragments. Under K1, moving one SKU to CIP means OneMind starts building kernels for the first time, under customer pressure.
- Pi 5 is produced to at least Jan 2036 [C-W18-017]. A Pi box sold in 2030 will need kernels after Raspberry Pi has moved branches several times. K2 has practised the hop on that board; K1 has not.

## 6. Robotics

- **Jetson: parity with K1, plus an option.** K2-hybrid ships NVIDIA's L4T kernel unmodified on Jetson, so it loses nothing to K1 on CUDA, Argus cameras or the DLA. What it adds is readiness for the BYOK path the run already listed as a watch item: Talos's PR siderolabs/pkgs#1518 (open, not merged, head `3dbeba8b`) builds NVIDIA's OE4T out-of-tree GPU stack against a 6.18 kernel, signs the modules with the kernel build's own key, and reports CUDA inference at ~60 tok/s in Kubernetes pods without `privileged: true` on Orin NX 16GB [C-STEEL-KRU-010]. NVIDIA's own BYOK page supports a non-NVIDIA kernel with its OOT modules (W7-FF-2 refuter). An OS that already builds and signs 6.18 in CI is the one that can take this path when NVIDIA's 6.8 kernel (not an LTS, C-W18-001) ages out; K1 would be starting from zero.
- **Non-Jetson robots** (x86 + USB cameras, RK3588 with an NPU, Pi 5 with a CAN HAT) get the same RT-capable kernel everywhere, which is what ros2_control-style controllers need for comparable latency numbers across boards (T-W18-7 can measure it once, not three times).

## 7. Security

- **Module signing without MOK.** Under Secure Boot, Debian's lockdown blocks "kernel modules that are not signed by a trusted key … including DKMS-managed drivers"; DKMS modules are signed with a machine owner key that "needs to be manually enrolled", and MOK changes "may only be confirmed directly from the console at boot time" [C-STEEL-KRU-013]. For OneMind's Pro/GPU tier (NVIDIA's x86 driver) and any OOT driver (ZFS, industrial cards), K1 + Secure Boot therefore means a console step per box, or Secure Boot off. Under K2, OneMind builds those modules in the same CI job as the kernel and signs them with the build's ephemeral key (the Talos PR does exactly this [C-STEEL-KRU-010]), so `module.sig_enforce` works with no user step. That is trigger 4 of `28-…` §6.3, and it fires the day W6 schedules Secure Boot.
- **Smaller attack surface.** A distro kernel is configured to boot any hardware Debian supports. A fragment-built kernel enables only what the contract lists (HAOS splits `device-support*.config` from `haos.config` for exactly this reason [C-STEEL-KRU-002]). Fewer built drivers means fewer of the ~8–9 kernel CVEs a day (W18-P0-1-cost refuter, SECONDARY counts) actually apply to OneMind images, which is the triage that CRA vulnerability handling makes OneMind do anyway.
- **Patch latency becomes OneMind's number, not Debian's.** `28-…` §4.3 itself says the image pipeline sets the floor in both routes. With a bot (Renovate already does 7 of HAOS's bumps [C-STEEL-KRU-003]) proposing each 6.18.y release, the CI building and boot-testing it, and the founder approving, the latency is the time to review a PR.

## 8. Solo-developer operability, and a fair re-score

**Cost, honestly stated.** About 50–60 mechanical bumps a year (HAOS), one LTS hop every ~2 years, a CI kernel build of 2–6 minutes per arch in the run's lab (C-W18-066) and ~20 minutes warm in Talos's ARM64 CI (C-STEEL-KRU-010), and a fragment file that the kernel contract needs anyway. AI agents draft these PRs well because each is a version string and a changelog read. Against that, K1 already obliges OneMind to build a Pi RT kernel (G4-M1) and to own the Jetson L4T risk; the marginal cost of K2 over K1 is smaller than the 66-vs-71 gap suggests.

**Re-score of K2-hybrid on the frozen weights.** `28-…` gave K2 a C2 of 3 because "custom configs on Jetson diverge from the vendor-tested build" [C-W18-020]. K2-hybrid does not touch the Jetson kernel, so it has the same official Jetson support that earned K1 its 4 under the C2 anchor ("official Jetson support"). Changing only that cell:

| Candidate | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Total |
|---|---|---|---|---|---|---|---|---|
| K1 (as scored) | 3 | 4 | 3 | 4 | 4 | 3 | 4 | **71.0** |
| K2 (as scored) | 3 | 3 | 3 | 5 | 3 | 3 | 3 | 66.0 |
| **K2-hybrid** | 3 | **4** | 3 | 5 | 3 | 3 | 3 | **70.0** |

K1 leads by **1.0 point, under the 3.0 tie threshold**. By the frozen protocol a tie is "settled by the decision-critical evidence and the refuter tables, never by adjusting scores". Those tables already contain: the W8 IIoT refuter (Debian's kernel cannot drive the Pi 5; Pi RT is OneMind-owned work), the W7 FF-2 refuter (an OneMind LTS + OOT route exists and should be evaluated), and the W18 cost refuter ("Linux" is really three vendor kernel lines). Each of those points reduces the number of kernel lines OneMind depends on if K2-hybrid is chosen, and none favours K1. **On the run's own rules, S5 should be recorded as a tie that the refuter evidence leans toward K2-hybrid for non-Jetson tiers.** If T-W18-4 measures the weekly bump under 1 hour, K2's C5 rises to 4 and K2-hybrid scores 72.0, ahead of K1.

## 9. Genuine weaknesses (stated as strongly as the evidence allows)

1. **HAOS does not use mainline on the Pi 5.** At `ab7d0f1a`, `rpi5_64` builds Raspberry Pi's fork [C-STEEL-KRU-002]. The mainline Pi 5 support in §3.3 is real for Ethernet/GPIO/USB, but display, CSI cameras, the RP1 audio/PWM blocks and HAT overlays were not checked, and the Pi 5 Ethernet series was still being revised in late 2025 (SECONDARY: mailing-list search results). On Pi 5, K2 realistically means "Raspberry Pi's tree with OneMind fragments", so it still has two kernel sources plus L4T. The "one kernel version" claim holds for the series (6.18), not the source tree.
2. **K2 turns a free service into a weekly job during the 180 days when the founder has least time.** Debian's security team already tracks 6.12 stable (trixie-security is at 6.12.116 [C-STEEL-KRU-007]), so K1's x86 latency is probably fine until 2028. The patch-latency argument in §7 is unmeasured for both routes (T-W18-3, T-W18-4).
3. **The C2 re-score is advocacy.** The rule says ties are settled by evidence, and the author could reasonably argue K2-hybrid still deserves C2 = 3 because its non-Jetson kernels are not vendor-certified for NVIDIA x86 drivers (C7 also stays at 3 for that reason).
4. **Secure Boot does not strictly require building the kernel.** A UKI wrapping Debian's signed `vmlinuz` can be signed with OneMind's keys without a compile; only OOT modules force the MOK-or-build choice. If the Pro tier ships NVIDIA's open modules through a signed package rather than DKMS, the module-signing advantage shrinks (not verified).
5. **Bus factor is the founder.** HAOS's kernel work is 71% one person [C-STEEL-KRU-003], inside a funded company. OneMind would be 100% one person until hiring.
6. **The Jetson BYOK option is not evidence yet.** PR #1518 is open and unmerged, was tested with the JetPack 6 CUDA runtime (12.6), not JetPack 7, and the W7 refuter found a ~7× regression on kernel 7.3 [C-STEEL-KRU-010; W7-FF-2]. K2's robotics advantage is optionality, not capability.
7. **Distro ecosystem fit.** NVIDIA lists Debian 13 for CUDA (C-W18-027) against Debian's kernel, and vendors certify distros, not custom configs. K2 gives up that "it's the Debian kernel" support answer on x86.

## 10. What evidence would make K2-hybrid the winner

- **T-W18-4:** a 4-week dry run of weekly 6.18.y bumps with boot tests costs **under 1 hour per bump** (lifts C5 to 4; K2-hybrid 72.0 vs 71.0, and with the tie rule plus refuter evidence, a clear K2 decision).
- **T-W18-3:** any "high" kernel CVE reaches Debian trixie-security more than 14 days after the upstream stable fix, twice in six months (§6.3 trigger 2).
- **W6 schedules Secure Boot with OneMind keys plus an OOT driver on any tier** (NVIDIA x86, ZFS) (trigger 4).
- **A boot test of mainline 6.18.y with OneMind fragments on a Pi 5** that passes Ethernet, USB, GPIO, NVMe and a k3s Ready check (removes the Pi fork from the non-camera Pi SKUs, and makes "one source tree" true too).
- **siderolabs/pkgs#1518 merges and holds across two 6.18.y bumps with no throughput regression on JetPack 7 CUDA** (turns the Jetson BYOK track from watch item into plan item).
- **Any RT-only regression on the Pi 5 that Raspberry Pi declines to fix** (shows that owning the RT build is unavoidable, which is K2's premise).

## Sources opened for this file

| ID | Source | Pinned |
|---|---|---|
| C-STEEL-KRU-001/002/003 | github.com/home-assistant/operating-system `buildroot-external/configs/*_defconfig` and commit history via `gh api` | `ab7d0f1a0174760353780a21be2befecbc80a672` |
| C-STEEL-KRU-004/005/006 | github.com/torvalds/linux `drivers/misc/rp1`, `drivers/pinctrl/pinctrl-rp1.c`, `drivers/clk/clk-rp1.c`, `arch/arm64/boot/dts/broadcom/bcm2712-rpi-5-b.dts`, `drivers/net/ethernet/cadence/macb_main.c` | tag `v6.18` |
| C-STEEL-KRU-007 | https://tracker.debian.org/pkg/linux | accessed 2026-11-10 |
| C-STEEL-KRU-008 | https://docs.kernel.org/process/cve.html | accessed 2026-11-10 |
| C-STEEL-KRU-009 | https://www.kernel.org/category/releases.html | accessed 2026-11-10 |
| C-STEEL-KRU-010 | https://github.com/siderolabs/pkgs/pull/1518 | head `3dbeba8b610387accc7d8e4d3bbf0d72bc7cac24` |
| C-STEEL-KRU-011 | github.com/raspberrypi/linux default branch | `rpi-6.18.y` |
| C-STEEL-KRU-012 | https://github.com/raspberrypi/linux/issues/7035 | comment 2025-09-05 |
| C-STEEL-KRU-013 | https://wiki.debian.org/SecureBoot | accessed 2026-11-10 |
| SECONDARY | Pi 5 RP1 Ethernet patch series v2 (patchew / linux-arm-kernel archive, Aug–Nov 2025), from search results, not opened | — |
