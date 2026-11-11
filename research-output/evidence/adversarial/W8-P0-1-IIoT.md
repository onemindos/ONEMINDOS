# Refuter report: P0-1 (DC-02, gate G4), IIoT and industrial-fit lens

- **Refuter lens:** IIoT and industrial fit (factories, water and energy, farms; OPC UA, Modbus, MQTT, real time, IEC 62443, zero-touch onboarding, fleets of about 10k devices)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (kernel, BSP and package-security facts: 6 months)
- **Verdict:** **weakened.** The conclusion survives: no G4 sub-check is a clean FAIL for Debian + Rugix while it PASSes for an alternative, so DC-02's flip condition is not met. But three of the claim's premises are overstated, and "CONDITIONAL" hides at least four pieces of work that OneMind would have to own.

## Claim under test

> Gate G4 (no blocking IoT/IIoT limitation) is CONDITIONAL, not FAIL, for Debian 13 + Rugix + k3s: industrial protocols are packaged or containerisable (open62541, libmodbus, Mosquitto MQTT 5, SocketCAN); Debian ships PREEMPT_RT kernels for amd64/arm64 but the Pi 5 has no 2712 RT build; a Debian-based OS holds IEC 62443-4-2 SL2; FDO is available as distro-agnostic Go code (unpackaged); Rugix integrates with existing fleet managers and k3s scales by site clusters. DC-02's flip condition is therefore not met.

DC-02 flip condition (`evidence/decision-critical.md`): *"any G4 sub-check FAILs for Debian + Rugix and PASSes for an alternative."*

## What the cited sources confirm (re-opened 2026-11-10)

| Item | Source | Status |
|---|---|---|
| Debian builds an `rt` (PREEMPT_RT) featureset for arm64 | `debian/config/arm64/defines.toml` and `debian/config/defines.toml` in linux 6.12.107-1 (fetched) | Confirmed. The cited `config` file alone does **not** show this: it has `CONFIG_PREEMPT_VOLUNTARY=y`. RT is a featureset defined in `defines.toml`. Cite that file instead. |
| The Raspberry Pi tree at e045ff67 has no `bcm2712_rt_defconfig` | `arch/arm64/configs` listing: `bcm2711_defconfig`, `bcm2711_rt_defconfig`, `bcm2712_defconfig`, `defconfig`, … | Confirmed |
| A Debian-based OS holds IEC 62443-4-2 SL2 | Moxa MIL product page (live, 2026-11-10) | Confirmed and stronger than claimed: "IEC 62443-4-2 Security Level 2 Certification for UC-1200A, UC-2200A, UC-3400A, UC-4400A, UC-8600A Series with MIL4". The page lists MIL 4 as Debian 13, supported until Aug 2035 (MIL 3 is Debian 11, until Dec 2031). |
| Rugix integrates with existing fleet managers | rugix-docs 1.4 fleet-management page | Confirmed: "ready-made integrations with Nexigon, thin-edge.io, Memfault, and Mender" |
| open62541 1.4 is packaged in trixie | packages.debian.org | Confirmed (1.4.11.1-1), but see counter-argument 2 |
| go-fdo is distro-agnostic Go code | go-fdo README | Confirmed. The repo is active (last push 2026-11-02) and not archived. |

## Strongest counter-argument

1. **The Debian RT kernel cannot drive a Pi 5 at all, so "Debian ships PREEMPT_RT for arm64" says nothing about the Pi tier.**
   - The trixie arm64 config (linux 6.12.107-1, `debian/config/arm64/config`) has `CONFIG_ARCH_BCM2835=y` (Pi 3/4) but no `CONFIG_MISC_RP1` and nothing for BCM2712.
   - The RP1 I/O-chip driver (Ethernet, GPIO, USB on the Pi 5) entered mainline only in **Linux 6.17** (Broadcom drivers pull for 6.17; LKDDB lists `CONFIG_MISC_RP1` "since 6.17").
   - So on a Pi 5, OneMind runs the Raspberry Pi vendor kernel in either case, RT or not. That kernel's maintainers say plainly: *"The RT kernel is something we consider experimental, and has no pi-specific component, so support is limited"* (popcornmix, raspberrypi/linux #7035, 5 Sep 2025).
   - That issue was an **RT-only regression on a Pi 5** (`6.12.44+rpt-rpi-2712 PREEMPT_RT`). A v3d GPU driver lock became a sleeping lock under RT and crashed the system. The fix needed upstream DRM work and took weeks.
   - Result: on OneMind's flagship small tier, real time means a kernel OneMind builds and supports itself. It is not a distro deliverable. The claim treats this as a footnote. For F-11 ("real-time", Pi-to-cluster with "no limitations") it is owned work and a risk.

2. **"Packaged" is not "security-maintained" for the main OPC UA stack.**
   - The Debian security tracker (fetched 2026-11-10) lists **23 open CVEs** against open62541. All are marked **trixie: "vulnerable (no DSA)"**, and forky/sid (1.4.18-1) are also "vulnerable".
   - The example CVE-2026-67855 is a remote heap use-after-free (denial of service) in GDS PushManagement. Its trixie note reads `<no-dsa> (Minor issue)`.
   - Many of the CVEs are filed against upstream 1.5.x. Whether 1.4.11 is really affected has not been proven, but Debian's official position is "vulnerable, no advisory".
   - Fedora 43 ships open62541 **1.5.8** and rawhide ships **1.5.10**, which is past the "before 1.5.7" fix line of CVE-2026-116014.
   - So on the sub-question "is the OPC UA stack kept patched by the distro?", the Fedora lineage does better than Debian stable today. For a network-facing OPC UA server on a plant floor this matters. The "containerisable" escape hatch makes OneMind the CVE owner for open62541. That ownership must be costed, not assumed away.

3. **The IEC 62443-4-2 precedent does not transfer.** Moxa's SL2 certificates are for named Moxa UC hardware series running Moxa's hardened MIL build, made by a vendor with its own IEC 62443-4-1 development process.
   - The certification literature agrees that a 4-2 assessment applies to "a specific product at a specific version" and normally assumes a 4-1 process (Acronis and BeaconSecurity guides, secondary; see the ISASecure guide for the primary rules).
   - The precedent proves Debian 13 is not disqualifying. It does not give OneMind a path. A solo founder still needs a 4-1 secure development lifecycle, a component scope, and a paid assessment.
   - The same is true for the RHEL/MicroShift precedents, so this point is neutral between the bases. It is not a pass for Debian.

4. **The FDO ecosystem is contracting, and Debian packages none of it.**
   - **fido-device-onboard-rs** (the Rust FDO stack Fedora IoT originally shipped) was marked **deprecated on 2026-02-09** (README commit cb51c041: *"This project is deprecated and is no longer actively maintained … security patches will be provided on a case by case basis"*).
   - Intel's **client-sdk-fidoiot** (the C device client) is **archived** (*"Intel will not provide or guarantee development of or support for this project"*).
   - What remains is essentially **go-fdo / go-fdo-server / go-fdo-client**. go-fdo's commit history is dominated by dependabot (106 commits) against 18 from the lead human contributor. That is a thin bus factor for a zero-touch onboarding root of trust meant to last 10 years.
   - Fedora packages `go-fdo-server`, `go-fdo-client` and `fido-device-onboard` (src.fedoraproject.org, created about Oct 2025). Debian packages nothing (sources.debian.org returns 404).
   - Not a FAIL, since a static Go binary is easy to ship. But it is a second sub-check where the Fedora lineage is ahead, and the whole FDO bet now rests on one small project.

5. **The update agent and the Modbus library each have a bus factor of 1.**
   - Rugix: `koehlma` made 1161 of about 1170 commits (GitHub contributors API). Rugix integrates with fleet managers, but its own longevity rests on one maintainer at one small company. RAUC (Pengutronix, multi-maintainer) is the hedge, and the claim should name it.
   - libmodbus: `stephane` made 834 commits, against 16 for the next contributor; 208 issues are open. Debian handles its CVEs through DLAs, which is good, but upstream is a single person.

6. **"k3s scales by site clusters" glosses over the 10k-device case.**
   - Fleet (Rancher), the obvious multi-cluster manager for k3s, gives its scaling limit as *"the total number of BundleDeployments"* (clusters x bundles). It says not to exceed *"100,000 BundleDeployments (e.g., deploying 150 bundles to 2,000 clusters)"*. It also warns that at *"5,000 - 10,000 clusters, this multiplier creates hundreds of thousands of resources"* that can *"overwhelm a single monolithic controller"*, and it requires sharding.
   - If every Pi is its own single-node k3s cluster, 10k devices with even 10 marketplace apps each is 100k BundleDeployments, which is at the published ceiling.
   - The claim must say how devices map to clusters: per device, or per site with many devices. It must also say which layer (Rugix plus an OS fleet manager, or Fleet/Argo) owns the 10k count. As written, "scales by site clusters" is an assertion, not evidence.

## Why this is "weakened", not "refuted"

The flip needs a sub-check that FAILs for Debian + Rugix **and** PASSes for an alternative. None does:
- Pi 5 RT: no distro gives a supported Pi 5 RT kernel. Fedora IoT does not officially support the Pi 5 either. That is not re-verified in this report, so treat it as a prior and re-check it. The doctrine "supervise, not control" (hard real time on PLCs or MCUs) also limits the stake.
- open62541 and FDO: Debian is behind but workable through containers or OneMind's own packages. That is CONDITIONAL, not FAIL.
- IEC 62443: a Debian 13 product holds SL2 today (MIL4), so the base is not a blocker.
- Fleet scale: limits exist at the Kubernetes fleet layer, independent of the base OS.

## New sources (all opened 2026-11-10; found by searching for deprecation, archival, CVEs, regressions and scale failure)

1. Debian security tracker, open62541 (23 open CVEs, trixie "vulnerable (no DSA)"): https://security-tracker.debian.org/tracker/source-package/open62541 and https://security-tracker.debian.org/tracker/CVE-2026-67855
2. fido-device-onboard-rs deprecation notice (README, commit cb51c041, 2026-02-09): https://github.com/fdo-rs/fido-device-onboard-rs
3. Intel client-sdk-fidoiot, archived: https://github.com/fido-device-onboard/client-sdk-fidoiot
4. raspberrypi/linux #7035, an RT-only crash on the Pi 5 with the maintainer statement "experimental … support is limited": https://github.com/raspberrypi/linux/issues/7035
5. Fleet best practices (100k BundleDeployments ceiling; warning at 5k to 10k clusters): https://fleet.rancher.io/tutorials/best-practices
6. Debian linux 6.12.107-1 arm64 config and defines (no RP1/BCM2712; `rt` featureset): https://sources.debian.org/data/main/l/linux/6.12.107-1/debian/config/arm64/config and https://sources.debian.org/data/main/l/linux/6.12.107-1/debian/config/arm64/defines.toml
7. Fedora package metadata: open62541 1.5.8 (f43) and 1.5.10 (rawhide): https://mdapi.fedoraproject.org/f43/srcpkg/open62541 ; the go-fdo-server package: https://src.fedoraproject.org/rpms/go-fdo-server
8. Moxa MIL product page (live; MIL4 = Debian 13 with SL2 for UC-xxxxA series): https://www.moxa.com/en/products/industrial-computing/system-software/moxa-industrial-linux
9. Supporting (search results, not opened): RP1 in mainline since 6.17 (LKDDB `MISC_RP1`, https://cateee.net/lkddb/web-lkddb/MISC_RP1.html); GitHub API contributor counts for rugix/rugix, stephane/libmodbus and fido-device-onboard/go-fdo (queried with `gh api`).

## Corrected claim (proposed)

> G4 is CONDITIONAL for Debian 13 + Rugix + k3s, with four owned work items:
> 1. **Pi 5 real time:** Debian's arm64 RT kernel has no RP1/BCM2712 support (RP1 is mainline only from 6.17). The Pi 5 needs a OneMind-built RT kernel from the Raspberry Pi tree, which its maintainers call experimental. Hard real time stays on PLCs or MCUs.
> 2. **OPC UA security:** trixie's open62541 1.4.11 carries 23 "no-DSA" CVEs. OneMind ships and patches its own open62541 (a container or backport) and tracks upstream 1.5.x.
> 3. **FDO:** go-fdo is the only living implementation (fdo-rs deprecated; Intel's C SDK archived). OneMind packages it for Debian.
> 4. **Fleet:** devices map to clusters as a declared ratio, and the 10k figure is checked against Fleet's 100k-BundleDeployment ceiling.
>
> Debian is no blocker for IEC 62443-4-2 (Moxa MIL4 on Debian 13, SL2), but no certificate transfers: OneMind needs its own 4-1 process. Rugix's bus factor is 1, and RAUC is the named fallback. DC-02's flip condition is not met.

## What would flip the decision

- **Toward refuted** (G4 FAIL for Debian, triggering DC-02):
  - Fedora IoT/bootc or CIP Core ships a **supported** Pi 5 PREEMPT_RT image, while the Raspberry Pi RT kernel stays "experimental".
  - Debian marks open62541 (or another core industrial stack) `<ignored>`/unsupported for trixie, or removes it, while Fedora or RHEL keeps it patched.
  - go-fdo is archived or deprecated, while Red Hat ships a supported FDO stack only inside RHEL for Edge or Device Edge.
  - An ISASecure or IECEE scheme rule excludes community-distro-based components from SL2 assessment unless a vendor support contract exists. Debian has none; RHEL does.
- **Toward upheld** (the claim stands as written):
  - Debian trixie gets an open62541 point-release update or DSA that closes the CVE list.
  - The trixie backports kernel (6.17+) boots a Pi 5 with RP1, plus an `rt` flavour.
  - Debian packages go-fdo.
  - A published Fleet benchmark shows more than 10k single-node k3s clusters running under sharding.
  - A second active Rugix maintainer appears.
