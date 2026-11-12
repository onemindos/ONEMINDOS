# Runner-up steelman: the CRA notified-body route from the start

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the runner-up. It is advocacy held to the evidence rules. Every fact is primary-sourced and was opened on 2026-11-11, or it is labelled SECONDARY, vendor-stated, interpretation or UNVERIFIED. §8 states the real weaknesses.
- **Date:** 2026-11-11 · **Re-check by:** 2027-05-11 for NANDO, standards and notified-body status (6 months, it is moving fast); 2027-11-11 for the guidance and legal text (12 months)
- **Verdict:** `steelman`
- **Decision under test:** `07-security-compliance.md` §8.1 and SEC-06, carried into `01-FOUNDATION-DECISION.md` §4.7 / §5.6 (D6) and `26-…` Z-05 option (a). The chosen route: keep OneMind-authored code in the base image Apache-2.0 and paid features out of it, rely on the Art. 32(5) free-and-open-source route (or a cited EN 304 626, or a "default category" box), get counsel's opinion, **decide the route by 2027-Q2**, and keep a notified body (module B+C) only as a **budgeted fallback**. `01-…` §"Adversarial shortfalls" records that this runner-up had no independent steelman. This file is it.
- **Serves requirements:** M-8, R-1, R-2, R-3, H-1, F-11, F-14, D-001, D-002
- **Ledger:** `evidence/claims/STEEL-cra-notified-body.csv` (C-STEEL-cra-nb-001 … 020). Archived excerpts: `evidence/sources/STEEL-cra-notified-body/` (with `SHA256SUMS`).
- **Not legal advice.** Classification and route readings are interpretations for counsel (Z-05).

> ### Explain it like I'm the founder
> To sell an operating system in the EU after **11 December 2027**, OneMind must show it meets the Cyber Resilience Act. There are three ways to show it. **(1) Mark your own homework** using an official EU standard, but the OS standard is still a draft. **(2) Mark your own homework because the product is fully free and open source**, which is today's plan. **(3) Have an EU-approved outside lab, a "notified body", check the product.**
> Today's plan picks (2), keeps (3) as a backup, and decides in mid-2027. This file argues the opposite: **book the outside lab from the start.** Route (3) is the only one that works for every OneMind product whatever the lawyers decide. It works with closed "pro" features, with NVIDIA and Raspberry Pi firmware, with the AI assistant and the mesh VPN in the box, and if a regulator calls the k3s platform a "container runtime". Labs are scarce: **none** is designated yet, so companies that queue early get slots. Robots and radios will need outside labs anyway.
> The catch, in §8, is real. It costs money every year, and every big change has to be shown to the lab. If the free-software route or the draft standard comes through in time, that money buys little.

---

## 1. The claim this steelman makes

> **OneMind should commit now to third-party conformity assessment (module B+C for the first box-and-image family, moving to module H as the release process matures), start a pre-assessment with a candidate notified body in 2027-Q1, and stop treating it as a fallback. It is the only route that survives every open legal question in Z-05: firmware blobs, paid editions, the box's own Annex III category, and a Class II reading of the k3s platform. It also leaves D-001's open-core boundary as a business decision, not a compliance constraint. And it lines up with what the robotics, radio and industrial tiers will need anyway.**

## 2. Why each "self-assessment" route has a hole for OneMind specifically

The chosen route is really three routes stacked, each with a condition. The table checks each condition against OneMind's own plans, using the Commission's guidance (C(2026) 5252, 27 July 2026), opened today.

| Route | Condition (primary) | Where OneMind fails or is exposed | Evidence |
|---|---|---|---|
| **Art. 32(5) FOSS** | The product must "qualify as" FOSS. The guidance says two cumulative conditions apply: a licence granting the full Art. 3(48) rights **and** source code that "is openly shared" (paras 44–46). | (a) Pi 5 EEPROM firmware and NVIDIA's BSP are not under such a licence. The W6 refuters already withdrew "fully FOSS" as impossible on those boards (`01-…` §5.6 P0-2 security). (b) D-001 plans **paid pro/enterprise features**. The guidance says a paid edition "is considered placed on the market … irrespective of whether functionally equivalent software is also available free of charge", and Example 17 is literally a FOSS operating system with a paid version (para 57). A paid edition that carries closed code cannot "qualify as FOSS". (c) A priced hardware box is very likely not "FOSS" as a product (`W6-P0-2-technical` refuter). | C-STEEL-cra-nb-003, -002; C-W6-013 |
| **Cited harmonised standard (module A for Class I)** | The guidance (para 149): "(i) **all** the applicable requirements of a relevant harmonised standard need to be applied; and (ii) the standard's scope needs to cover at least all the cybersecurity risks associated to that product's core functionality." | EN 304 626 is an enquiry draft with no Official Journal citation (re-fetched V1.0.1 today, byte-identical to the run's copy). Its own scope (§1.3) sends **"Hypervisors and container runtime systems"** and **"Boot managers"** to other standards. OneMind's core value is running containerised apps on k3s with a signed boot chain. If an authority reads that as Class II item 1, **Art. 32(3) has no standard-based escape at all**, and only FOSS or a notified body remain (`W6-P0-2-cost` refuter, §2). | C-STEEL-cra-nb-001, -007; C-W6-011, C-REF-W6-technical-007 |
| **Box in the "default category"** | Classification follows the product's single core functionality. Example 58: a smartphone that integrates an OS is not an "operating system". | This helps the box, but it also opens other Annex III Class I entries. OneMind's box ships an AI assistant that controls home devices (item 16, "smart home general purpose virtual assistants"), a mesh/overlay network (item 5 VPN, item 12 routers) and identity/SSO (item 1). Each has its **own** vertical standard to apply in full, all still drafts (ETSI's 17-standard enquiry). The more the box does (F-14, "no limitations"), the more likely one of them is its core function as marketed. | C-STEEL-cra-nb-004; C-W6-011, C-W6-018 |

**What this adds up to.** Each self-assessment path depends on an answer OneMind does not control: counsel on firmware, a standard's citation date, a regulator's reading of "core functionality". A notified body is the **one route whose availability does not depend on any of them** (Art. 32(2) and 32(3) both list module B+C and module H [C-W6-012]). For a ten-year product line (M-8), that robustness is worth paying for.

## 3. Scarcity is an argument for starting early, not for waiting

| Fact | Evidence |
|---|---|
| CRA Chapter IV (notified bodies) has applied since **11 June 2026**; Member States must "strive" to have enough bodies by 11 December 2026. | C-W6-001; C-STEEL-cra-nb-015 (SECONDARY restatement of Art. 35(2)) |
| No CRA notified body is designated. BSI Group itself says "no CRA Notified Bodies have been officially designated" (October 2026); a tracker found NANDO empty for the CRA on 2026-09-08. NANDO itself could not be opened (single-page app). | C-STEEL-cra-nb-013 (vendor-stated), -015 (SECONDARY), -017 (UNVERIFIED) |
| The pipeline is real and moving. Finland's Traficom route (17.8.2026): accreditation by FINAS, then notification, and EA recommends **ISO/IEC 17065 for module B+C and 17021-1 for module H**. DAkkS has accepted CRA accreditation applications since 28.7.2026. BSI Group reports RvA accreditation for modules B and H (dated 3.11.2026), with notification by the Dutch authority and a **pilot** assessment still to come. Applus+ says it is "progressing through" accreditation and sells a "Module B + C simulation" pre-assessment today. | C-STEEL-cra-nb-011, -012, -013, -014 |

**Why this favours starting now.** The chosen plan decides by 2027-Q2 and uses a notified body only if the other routes fail. If they fail, they will fail **together and late**: a slipped standard and a counsel opinion against blobs land on every Linux-on-ARM appliance maker at once, about six months before 11 December 2027. That is exactly when the first bodies' queues will be longest. A body still looking for **pilot** assessments (BSI's step 2) is a body that takes small manufacturers now. A pre-assessment in 2027-Q1 costs little and turns the fallback into a known quantity. *(Interpretation; the queue claim is not measured anywhere.)*

## 4. Strongest arguments by requirement

### 4.1 F-14 and D-001: one OS with "no limitations", and an open-core boundary chosen for business reasons

F-14 says "the user never switches products". The FOSS route forces a permanent **compliance seam** between the EU-sold base image and anything paid (SEC-06: "deliver paid features as separately installed Market apps"). For ten years every feature decision becomes a legal one: does putting this in the image break Art. 32(5)? Guidance para 57 / Example 17 show the risk is not theoretical, because a paid OS edition is squarely "placed on the market". The notified-body route **removes the seam**: a certified image can carry closed enterprise modules, OEM extensions (D-001 "Manufacture with OneMind") and signed driver packs, and D-001's still-open "pro vs open" ADR goes back to being a pricing decision. *(Interpretation for counsel; the guidance does not say what a paid edition with closed code needs, only that it is on the market.)*

### 4.2 D-002 and longevity to 2036: certify the pipeline, not each image

D-002 builds Edge, Lite, Pro, Robotics, Omni and Cluster from one pipeline. The guidance (§7.4, paras 174–177) allows **one risk assessment, one technical file, one conformity assessment and one EU declaration** for variants that "share the same architecture, security-relevant design and intended purpose", with only security-relevant differences ("software stacks, update mechanisms or remote connectivity") assessed separately [C-STEEL-cra-nb-005]. That is a natural fit for a type examination of the shared layers plus delta reviews per profile. **Module H** goes further. It assesses the manufacturer's quality system, which is the release pipeline itself, and is accredited under ISO/IEC 17021-1, a management-system standard [C-STEEL-cra-nb-011]. For a product line that will add SKUs and rebase Debian twice before 2036 (`07` DC-04), a certified process ages better than a self-declared one re-argued for each release. *(Annex VIII clause text could not be opened, see §7; how module H handles new SKUs is UNVERIFIED.)*

### 4.3 F-11 industrial IoT: buyers already expect third-party certificates

F-11 names IEC 62443, farms, water and energy, factories and public-safety infrastructure. OneMind's own IIoT work says the 62443 route is a **certified reference box** and that 4-1 process work should **start now** (W8-R5). The competitor evidence is all third-party: Moxa's Debian 13-based MIL4 carries a 62443-4-2 SL2 certification declaration [C-W8-033]; CIP announced 62443-4-1/4-2 compliance [C-W8-034]. The process a notified body examines under module H overlaps heavily with what a 62443-4-1 assessor examines: secure development, vulnerability handling, update integrity. CRA notified bodies are accredited under ISO/IEC 17065 / 17021-1, the same families used by industrial security certifiers. One outside relationship can serve both. *(Interpretation; whether any single body will offer both, and at what discount, is UNVERIFIED.)* For an industrial or public-safety buyer, "assessed by notified body NNNN" reads better than "self-declared under Art. 32(5)", even though both are legal.

### 4.4 Robotics: an outside lab is coming anyway

The Machinery Regulation applies from **14 January 2027** and requires **third-party conformity for ML-based safety components** and limits on self-evolving machines [C-W6-043, C-W7-045, C-W7-046]. Physical AI is where OneMind's Robotics and Omni tiers point. W7-R6 keeps hard safety on an MCU, but the AI supervisory layer on a Jetson that commands actuators will be argued over with a Machinery notified body at some point. The draft OS standard already carries a robotics-shaped requirement: **MI-RTDL**, "security mechanisms do not cause the product to exceed documented worst-case execution times for real-time tasks" [C-STEEL-cra-nb-010]. That is just the kind of claim (PREEMPT_RT, k3s load, security mitigations) a solo developer self-assesses least credibly. Starting the CRA relationship early means the robotics tier meets an outside lab with a CRA certificate in hand, not cold.

### 4.5 Radios: the RED bridge only works through a notified body

A OneMind box with Wi-Fi, Bluetooth, LoRa or mesh radios is already under the RED cybersecurity delegated act (since 2025-08-01) [C-W6-020]. The EN 18031 standards are cited **with restrictions** [C-W6-021]. The Commission guidance (paras 247–252, Art. 69(1)) says **EU type-examination certificates** issued under the RED delegated act stay valid for the CRA, for the risks they cover, until **11 June 2028**, "as well as where the manufacturer has voluntarily chosen" the notified-body procedure [C-STEEL-cra-nb-006]. RED notified bodies exist today, unlike CRA ones. A RED type examination of the first box, done now, buys the CRA a six-month bridge for its radio-related risks and starts the third-party file. Self-declared RED conformity buys no such carry-over. *(Interpretation: whether a OneMind box's RED file would need a notified body at all depends on the EN 18031 restrictions, which this agent did not open.)*

### 4.6 Security: the one honest outside reviewer a solo developer gets

The foundation's security story rests on labs run **in emulation only** (Secure Boot route, RAUC gate; `01-…` §5.10 shortfalls), a key ceremony still to be decided (Z-04), and a solo author. Self-assessment means the same person designs, implements, tests and declares. A notified body under module B examines the design and samples. Under module H it audits the process. Either way it is the only independent check the CRA puts in the loop. The guidance also expects the manufacturer to "demonstrate that all risks applicable" are addressed, including risks outside a standard's scope (paras 150–151). For a k3s platform with an AI agent and actuation, that is a long list to defend alone in front of a market-surveillance authority.

### 4.7 Solo-developer operability: fewer open legal questions to carry

Z-05 lists three counsel questions (box classification, firmware blobs, paid closed modules) that the FOSS route must keep answering **at every release**, because one closed blob or one paid module can change the answer. The notified-body route makes all three moot for conformity purposes. The CRA also tries to make third-party assessment bearable for very small firms. In the pre-final text, conformity-assessment fees must take micro and SME "interests and needs" into account and be "reduced proportionately", and notified bodies must accept a Commission-defined **simplified technical documentation** format for micro and small enterprises (Art. 33(5)) [C-STEEL-cra-nb-016, SECONDARY: numbering from a pre-final consolidated text, not checked against the Official Journal]. A solo founder trades a recurring fee for one fewer category of legal risk to manage.

## 5. Side-by-side (qualitative; no frozen scorecard exists for this decision)

| Lens | Chosen: FOSS / standard / default, NB as fallback, decide 2027-Q2 | Runner-up: notified body from the start |
|---|---|---|
| Works if counsel says firmware blobs disqualify Art. 32(5) | Pi 5 / Jetson images lose the route | Unaffected |
| Works if a paid edition carries closed code | No (para 57) | Yes |
| Works if k3s platform is read as Class II | Only through FOSS | Yes (Art. 32(3) lists B+C, H) |
| Works if EN 304 626 citation slips past 2027 | Only through FOSS or default box | Yes |
| Cost | Lowest (documentation only) | Highest: fees plus change reviews (§8) |
| Release agility | Highest | Lower: changes to the approved type go to the body |
| Robotics / Machinery Reg. fit | Separate track later | Same kind of relationship, started early |
| Industrial / public-safety buyer optics | "Self-declared" | "Assessed by notified body NNNN" |
| Availability today | Available (module A needs no body) | **No body designated yet**; pre-assessment only |

## 6. What competitors do (constraint-fit)

| Product | What it does about CRA conformity | Constraints | Constraint-fit for this decision |
|---|---|---|---|
| Home Assistant OS, umbrelOS, Olares | No public CRA route statement found in this pass (UNVERIFIED; not searched exhaustively) | Appliance OSes, small teams, x86/Pi, HA without Kubernetes | Low: nobody in this group has shown its hand |
| Moxa MIL4 | Third-party IEC 62443-4-2 SL2 declaration on named hardware [C-W8-033] | Industrial hardware vendor, Debian 13, 10-year support | **High on F-11**: the closest industrial pattern is third-party |
| CIP (Linux Foundation) | 62443-4-1/4-2 compliance announced; adopters keep product responsibility [C-W8-034] | Consortium, Debian-based | Medium: shows a shared base plus third-party evidence |
| BSI Group, Applus+ (bodies, not competitors) | Pilot assessments and "mock" B+C now | Assessors | Shows the route is open for early movers |

## 7. Sources that could not be opened

- **EUR-Lex** (CRA text, Annex VIII module B and H clauses) returned empty pages to every automated fetch today. Per §2 rule 5 this was not circumvented: `UNVERIFIED (blocked)`. Article-level facts reuse the run's earlier verified rows (C-W6-001, -011, -012, -013); the guidance restates Art. 32(2)/(5) and was opened. Module H surveillance, certificate validity and change-notification details are **UNVERIFIED**.
- **NANDO** is a single-page app and was not readable: the "zero designated" count rests on vendor-stated and SECONDARY sources.
- **Notified-body prices**: no body publishes a CRA price. The run's existing figures (module B about €20–60k, module H about €80–150k; `W6-P0-2-security`) are consultancy estimates, SECONDARY.

## 8. Genuine weaknesses (stated as strongly as the evidence allows)

1. **You cannot start what does not exist.** No CRA notified body is designated (§3). "From the start" today means a pre-assessment or a RED type examination, not a CRA certificate. If designations slip into late 2027, the route is unavailable exactly when needed, and the FOSS route is the only one that certainly works on 2027-12-11.
2. **The free routes may well open in time.** Draft EN 304 626 is more achievable than `07` assumed. Both security profiles accept **"(KEVD or KEVA)"**, so a documented update procedure satisfies the baseline where automatic-by-default updates are not chosen. Rollback after a failed update is exempt from authorisation (MI-SUAR), and MI-SUVI accepts signed packages or a verifying package manager [C-STEEL-cra-nb-008, -009]. RAUC's signed A/B design already fits. If it is cited in 2027, a Class I OS image self-assesses, and notified-body fees buy nothing legally. *(This also corrects `07`'s reading that the standard requires automatic updates by default. CRA Annex I itself still asks for automatic security updates by default "where applicable" [C-W6-008].)*
3. **The box probably needs no body at all.** Example 58 makes it likely a OneMind box is classified by its own core function [C-STEEL-cra-nb-004], often the default category (module A). Paying a body for a product that does not need one is pure cost.
4. **Change control drags on a solo cadence.** Third-party assessment ties the approved type or the quality system to an outside party. Changes that could become substantial modifications have to be notified to the body (Recital 41, pre-final text, SECONDARY [C-STEEL-cra-nb-016]). A ten-year continuous-delivery OS with many profiles produces many such changes. Module H avoids per-type re-examination, but it needs a documented quality system (ISO/IEC 17021-1 audited) that a solo founder does not have.
5. **Money.** €20–60k for module B and €80–150k for module H (SECONDARY), plus surveillance and change reviews, against a pre-revenue company. SME fee reductions are real in the text but unquantified.
6. **It does not remove manufacturer duties.** Vulnerability handling, Art. 14 reporting, support periods and SBOMs remain. The body checks them, it does not do them.
7. **It weakens D-001's trust story.** The FOSS route forces public technical documentation (Art. 32(5)), a strong sovereignty signal. A certified-but-closed path could drift away from that.
8. **Body lock-in and capacity risk.** One body's queue, prices or exit becomes a single point of failure for EU sales.

## 9. What evidence would make this route win

- **Counsel or the Commission** states that non-free firmware/BSP blobs, or a paid edition with closed modules, take a product out of Art. 32(5). Then the notified body becomes the base case for Pi 5 and Jetson images (the `W6-P0-2-security` flip condition).
- **EN 304 626 fails its vote** (closing mid-November 2026) or has no OJ citation by about 2027-09, or the citation comes with restrictions that OneMind's design cannot meet.
- **A Class II reading**: guidance or a market-surveillance position treats a k3s-hosting appliance OS as a "container runtime system".
- **The box's marketed core function** lands on an Annex III Class I vertical (I-16 assistant, I-5 VPN, I-12 router) whose ETSI standard is not cited in time.
- **A quote**: a notified body offers a micro-enterprise B+C (or H) assessment for a box-plus-image family under roughly the low end of the SECONDARY range, with a lead time of 3 months or less and change reviews priced per delta. Draft the outreach in `outreach-drafts.md`; Zeus sends it.
- **A buyer requirement**: one industrial, public-safety or OEM partner (D-001 OEM program) asks for a third-party CRA certificate as a purchasing condition.
- **Robotics tier timing**: the first Robotics SKU needs a Machinery Regulation notified body before 2028, making a shared assessor cheaper.

**Fair reading after arguing for it:** the evidence supports a smaller change than "notified body from the start". Move the notified body from a *decide-in-2027-Q2 fallback* to a **parallel track started in 2027-Q1**: a pre-assessment (or a RED type examination of the first radio box) plus a written quote. That costs little, removes the late-2027 queue risk, and keeps the FOSS route as the primary path if counsel and EN 304 626 come through.

## Glossary

- **Notified body:** an assessment organisation that a Member State has designated and notified to the Commission (listed in NANDO) to perform third-party conformity assessment.
- **Module A:** internal control; the manufacturer self-assesses.
- **Module B+C:** EU-type examination by a notified body (B), then conformity to type based on internal production control (C).
- **Module H:** full quality assurance; the notified body approves and audits the manufacturer's quality system.
- **Art. 32(5):** lets products that qualify as free and open-source software use any procedure, including module A, if the technical documentation is public.
- **Pre-assessment:** an informal mock assessment that a candidate body sells before it can issue certificates.
