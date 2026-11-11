# W6 · P0-2 · Adversarial refutation, security lens

- **Claim:** P0-2 (CRA classification of OneMind OS and the FOSS self-assessment route)
- **Refuter lens:** security
- **Date:** 2026-11-10
- **Verdict:** **weakened**
- **Inputs:** the claim text and its four cited sources only (brief §2 rule 7), plus new sources found by searching for failures, delays, CVEs and gaps.

## 1. What holds up (checked against primary text)

| Sub-claim | Check | Result |
|---|---|---|
| Classification follows core functionality; integrating an Annex III product does not by itself reclassify the host | CRA Art. 7(1), verbatim: "The integration of a product with digital elements which has the core functionality of a product category set out in Annex III shall not in itself render the product in which it is integrated subject to…Article 32(2) and (3)." Implementing Reg. (EU) 2025/2392, recitals 2 to 5. Commission guidance C(2026) 5252, paras 139 to 145 | Holds |
| OneMind OS has the core functionality of an "operating system" (Class I, Annex I point 11 of 2025/2392) | 2025/2392 describes an OS as software that "provide[s] an abstract interface of the underlying hardware" and may provide resource management and scheduling, including "general-purpose and special-purpose operating systems". Guidance Example 57 matches a platform that "serve[s] as the central software environment on which applications can reliably run" | Holds for the **standalone OS image** |
| Class I without full harmonised standards means module B+C or H | Art. 32(2), verbatim | Holds, but the claim leaves out two alternatives that Art. 32(2) lists (see 2.2) |
| Art. 32(5) FOSS route to module A if the technical documentation is public | Art. 32(5), verbatim; guidance para 137 ("may follow the procedures of the default category") and para 148 | Holds. It also covers **Class II**, which the claim does not say |
| EN 304 626 V1.0.1 is an enquiry draft dated 2026-08-12 | The docbox PDF resolves (HTTP 200, 1.5 MB, filename matches). The ETSI press release of 13 Aug 2026 says the 17 vertical ENs are in public enquiry "until mid-September to mid-November 2026, depending on the vertical" and does not name a citation date | Holds. The release does not name EN 304 626 itself, so the exact closing date for this EN is unconfirmed |

## 2. Strongest counter-argument

**The conclusion "keeping the EU-sold base image fully FOSS is the only route to self-assessment without a cited standard" is overstated, and from a security standpoint "fully FOSS" cannot be built for two of the three target platforms.**

### 2.1 The boxes are probably not "operating systems" at all
Guidance Example 58 says a smartphone that integrates an OS "as a whole has a different core functionality… The mere integration of an operating system does not mean that the smartphone has the core functionality of an operating system." A OneMind Edge, Lite, Pro, Robotics or Omni **box** is hardware with embedded software. Its core functionality is a home or edge server, a robot controller or a NAS-like appliance, not "an abstract interface of the underlying hardware". It probably falls in the **default category**, where module A is available whatever the licence and whatever the standards status. Class I with the FOSS requirement then applies only where the **OS image is made available on its own** (download, paid licence, support subscription). Guidance para 145 also says that a module "offered for separate purchase, licensing or subscription" is a product in its own right. So the classification decision belongs to each SKU, not one decision for the whole company.

Caveat (cuts the other way): guidance para 143 forbids misrepresenting core functionality, and para 142 says classification follows "actual technical characteristics". A box marketed as "the operating system for sovereignty" invites the regulator to read its core functionality as an OS. The marketing copy then becomes a compliance artefact.

### 2.2 Art. 32(2) names two more ways to avoid a notified body
Art. 32(2) treats **common specifications** and **European cybersecurity certification schemes at assurance level "substantial"** the same way as harmonised standards. Art. 27(2) lets the Commission adopt common specifications by implementing act when standards are "not delivered within the deadline". Under M/606, vertical standards were due 31 Dec 2026, after a July 2026 amendment (getstandardos, §4). If ETSI slips again, the common-specification trigger becomes real before the 11 Dec 2027 application date. "Without a cited standard" is a condition in time, not a permanent fact. The obligation applies from 11 Dec 2027, and the vertical ENs are only 13 months from that date. Using EUCC also needs an Art. 27(9) act. I found none, so this is the weakest of the alternatives.

### 2.3 Security lens: a "fully FOSS" base image does not exist on Jetson, and is doubtful on Pi 5
- **Jetson.** The BSP (Jetson Linux / L4T), its initrd, the `nvluks` trusted application and CUDA are NVIDIA-licensed, not FOSS. ONEKEY's advisory (3 Sep 2026) shows why this matters. A command injection in NVIDIA's own `/init` script (an `eval` of an unsanitised field in `opt/nvidia/cryptluks`) gives a physical attacker a root shell before the LUKS key TA closes. "Secure Boot does not prevent this because the exploited code is NVIDIA's trusted code." It affects Xavier, Orin and **Thor**, CVSS 4.0 7.0, and the 38.x branch (T5000/T4000) was still unpatched at publication. NVIDIA refused to share its private advisory. The March 2026 Jetson/IGX bulletin (CVE-2026-24148, -24153, -24154) shows the same class of problem in the boot path. A OneMind Robotics/Jetson image therefore **cannot** be "fully FOSS". It still carries Annex I vulnerability-handling duties for closed code that OneMind cannot patch and on which it gets disclosures late.
- **Pi 5.** The EEPROM bootloader is proprietary, and so is the residual VideoCore firmware. Raspberry Pi's own firmware-update white paper says the bootloader lives in on-board EEPROM. The Wi-Fi/BT firmware that ships in the image is also a binary blob. Whether a product with these components still "qualif[ies] as free and open-source software" (Art. 3(48): source "openly shared" under a licence granting all freedoms) is **not addressed** by Art. 32(5), 2025/2392 or the guidance section on FOSS, which I searched. Guidance paras 44 and 46 make the FOSS test cumulative (licence and openly shared source) and apply it to "software". A strict market surveillance authority could find that an image bundling non-free firmware is not FOSS.
- **The security trade-off.** A strict "fully FOSS" rule pushes OneMind to strip vendor firmware and drivers: NVIDIA GPU userspace, Hailo/RK3588 NPU runtimes, Broadcom Wi-Fi. That buys a legal route at the cost of security-relevant hardware enablement: measured boot, OP-TEE/TA-based disk encryption and vendor CVE fixes. Shipping a weaker product to keep a conformity route is a bad security bargain.

### 2.4 Even the notified-body fallback is not ready
- getstandardos (snapshot 11–12 Sep 2026): **zero** CRA notified bodies with an active notification in NANDO. Zero harmonised standards in the OJ. 7 of 27 market surveillance authorities registered.
- CRA Decoded (19 Jul 2026): zero notified bodies. Art. 35(2) only says Member States "shall strive" to have enough by 11 Dec 2026. Consultancy estimates put module B at €20–60k and module H at €80–150k, with 12–18 months to accredit each body.

This cuts both ways. It **strengthens** the practical case for the FOSS route, because the alternatives are missing or expensive for a solo founder. It also shows the decision rests on a regulatory system still under construction, where interpretation (for example on binary blobs) could land against OneMind.

### 2.5 Class II exposure (narrows the attack, does not refute)
k3s/containerd "manage the execution and lifecycle of containers", which is the 2025/2392 Class II wording for container runtime systems. Art. 7(1) and guidance para 144 (one core functionality per product) protect the OS image as long as the docs and marketing lead with the OS. A "k3s app platform" SKU sold separately (for example a Cluster edition offered as installable software on an existing distro) could be classed **Class II**. There module A is **only** available through Art. 32(5). This **raises** the stakes of FOSS for that SKU.

## 3. New sources (opened; found by searching for failures, delays and CVEs)

1. Commission CRA guidance C(2026) 5252 final (27 Jul 2026), reproduced at https://cra.orcwg.org/official-guidance/. Paras 44, 46, 57, Example 17, 137 to 148, Examples 57 and 58. It says the base OS can be Class I while a box integrating it is not, and it is silent on binary blobs.
2. ONEKEY, "Security advisory: Secure Boot bypass on NVIDIA Jetson for Linux" (3 Sep 2026): https://onekey.com/resource/security-advisory-secure-boot-bypass-on-nvidia-jetson-for-linux. Closed vendor boot code with a CVSS 7.0 flaw, an unpatched 38.x branch and an advisory withheld from the researcher.
3. NVD CVE-2026-24148 (Jetson JetPack insecure-default initialisation, March 2026 bulletin): https://nvd.nist.gov/vuln/detail/CVE-2026-24148. Seen in search results, not opened in full.
4. getstandardos, "The EU's own CRA machinery, on the day the duty started: 0 notified bodies, 0 harmonised standards, 7 of 27 enforcers" (Sep 2026): https://getstandardos.com/articles/the-eu-s-own-cra-machinery-on-the-day-the-duty-started
5. CRA Decoded, "CRA Notified Body Capacity Crisis: How to Cope" (19 Jul 2026): https://cra-decoded.com/blog/posts/cra-notified-body-capacity-crisis/
6. Raspberry Pi white paper RP-003476 "Updating Pi firmware": https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-003476-WP-3-Updating%20Pi%20firmware.pdf. The Pi 5 bootloader is in EEPROM and closed. This was relayed through search; I did not open the PDF.

Sources 4 and 5 are secondary (consultancy and blog) snapshots. Re-check NANDO and the OJ harmonised-standards list before relying on them. **Re-check by: 2027-05-10** (6 months, regulatory state is moving fast).

## 4. Verdict: weakened

The legal mechanics (Art. 7, 32(2), 32(5), 2025/2392, the EN 304 626 draft status) are **correct**. The conclusion is not:
- "Only route" is wrong for **boxes**, which are likely default category with module A whatever the licence (Example 58). It is time-bound for the **image**, because harmonised standards or common specifications may be cited before 11 Dec 2027.
- "Fully FOSS" cannot be built for the **Jetson** flavour (closed L4T/BSP with live boot-path CVEs) and is **legally uncertain on Pi 5** (closed EEPROM bootloader and firmware blobs). The guidance does not say whether non-free firmware disqualifies a product.

**Suggested rewrite of the decision:** classify each SKU. (a) Boxes: default category, module A. Keep the marketing consistent so a regulator cannot recast the box as an OS. (b) Standalone x86/Pi OS image sold or supported commercially in the EU: Class I. Keep it FOSS-licensed with openly shared source and public technical documentation (Art. 32(5)), and list the firmware blobs in the SBOM with a written rationale. (c) Jetson image: assume Art. 32(5) is **not** reliably available. Ship it in the EU only inside a box (default category), or budget for module B+C. Pro modules sold separately are separate products (para 145) and do not taint the FOSS base.

## 5. What evidence would flip the decision

- **Toward refuted:** a Commission FAQ, AdCo/market surveillance position or ETSI EN text saying that bundled non-free firmware or BSP binaries **disqualify** a product from Art. 32(5). The FOSS route then disappears for every hardware target, and the decision has to move to boxes-only (default category) or notified-body budgeting.
- **Toward refuted:** EN 304 626 (or common specifications under Art. 27(2)) cited in the OJ before 11 Dec 2027. Module A then opens for a Class I OS **regardless of licence**, so FOSS is no longer the only route.
- **Toward upheld:** official guidance or a CRA FAQ confirming that FOSS status attaches to the software the manufacturer authors and licenses, with third-party redistributable firmware treated as an integrated component (as for Debian's non-free-firmware). The claim then stands for x86 and Pi 5.
- **Toward upheld for boxes too:** a regulator position that an appliance sold as "an operating system" has OS core functionality (para 142/143 applied to OneMind's own marketing). The boxes then become Class I, and FOSS really is the only cheap route.
- **Toward Class II:** a market surveillance authority classing a k3s-centric platform as a "container runtime system". FOSS then becomes mandatory for module A for that SKU, which strengthens the FOSS requirement.
