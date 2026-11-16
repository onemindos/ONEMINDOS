# Founder decision briefs: week of 2026-11-16

**For:** Zeus · **Written:** 2026-11-14 · **Why this exists:** six open decisions block code or dates. Each brief below gives the question in plain words, why it matters now, the options, a recommendation, and what your answer unblocks. Answer with one letter per brief (in chat or on the issue). Each answer becomes a dated entry in [`docs/DECISIONS.md`](../../DECISIONS.md) (D-009 onward), and the issues that wait on it lose `needs-founder`.

None of these reopen D-001 to D-007. Where the research was written before D-007 (Debian 13), the brief says what changed.

## Quick answer sheet

| # | Decision | Due | Recommended answer | Unblocks |
|---|---|---|---|---|
| 1 | **Z-41**: run the Ubuntu Secure Boot test? | Mon 2026-11-16 | **(d) Drop it**; it can't change the base under D-007 | Nothing waits on it; clears a day-1 task |
| 2 | **Z-04 / F-27**: signing keys and the offline ceremony | This week | **(a′)** 2-of-3 offline root keys on encrypted USB sticks now, moved to hardware keys later by a root rotation | Signed releases, the downloads page, the try-it demo, #153, #185, #243 |
| 3 | **#214 / F-25**: order the hardware | This week | **(a)** Two Pi 5s + NVMe now; Jetson after the NVIDIA Inception answer; radios later | The Pi soak (must start by 2026-12-11), the bootc Pi test, every metal gate |
| 4 | **Z-40**: write down four scoring rules | Before G1 (2026-12-13) | **(a)** Adopt the readings the research used | A clean reading of the bootc Pi test |
| 5 | **Z-10 / W2-HW-3**: approve the bootc test on a real Pi 5 | Before G1 | **(a)** Yes, as D-007's reopen check | Keeps D-007's own reopen condition honest |
| 6 | **#253**: VMs, a web terminal, Tor | No hard date | VMs **later**, web terminal **yes (owner-only, rescue console)**, Tor **later**. **Your answer (D-014): build all three now**, Tor as an optional app | #281 (VMs), #273 (terminal), #284 (Tor) |

---

## 1. Z-41: run the Ubuntu Secure Boot test (LT-VM-20)?

**In plain words.** The research left one virtual-machine test unrun: does OneMind's Secure Boot setup work the same on Ubuntu 26.04 as it does on Debian? (Secure Boot means the PC only starts software signed by a key it trusts.) The research computer couldn't reach Ubuntu's servers, so it asked you to run it on your Mac.

**What changed.** The test mattered because, before D-007, Ubuntu was the base the scoring picked, and a fail would have moved the base to bootc (`research-output/26-…` Z-41; `01` §3.1.6 h). On 2026-11-11 you chose Debian 13 (D-007). D-007 reopens only if **bootc passes on a real Pi 5** or **Canonical offers a written, non-revocable, affordable agreement**. A Ubuntu Secure Boot result is neither, so **no outcome of this test can change the base.** Founder note 04 §8 already said "you may drop it".

**Options.**
- **(a)** Run it on your Mac on Monday (about 1.5–2 hours unattended, twice), as the research asked.
- **(b)** Approve an Ubuntu mirror so a future research pass can run it.
- **(c)** Leave it for gate G1.
- **(d) Drop it as superseded by D-007.** Record "U-SB not run; not needed under D-007". If the Ubuntu CI hedge ever needs Secure Boot, the Claude builder can add the kit to that CI leg later (it overlaps with #226's Ubuntu-hedge fix).

**Recommendation: (d).** It costs you two hours and can't move a decision. Your hours go further on #2 and #3.

**Unblocks:** nothing waits on it. It removes a stale day-1 item from `20-PLAN-180-DAYS.md`.

---

## 2. Z-04 / F-27: signing keys and the offline ceremony (REL-01, #153)

**In plain words.** Every update OneMind ships must be signed, so a box only installs updates that really came from you. The signing uses TUF (The Update Framework), which has a **root key** that vouches for all the other keys. If the root key is stolen, an attacker can ship "updates" to every box; if it's lost, you can't change the other keys. So the root key is made on a machine with no network (a "ceremony") and never goes online. **Until this happens, nothing can be published as signed**: no signed release, no downloads page with signatures, no upgrade test (`docs/leap/ALPHA-CHECKLIST.md`).

**What the research recommends (Z-04 a):** an offline root on hardware keys you hold; **2-of-3** (any two of three keys must agree to sign, so losing one isn't fatal and stealing one isn't enough); a written succession plan (who can act if you can't); and a key-rotation drill before the first box ships. Home Assistant, by contrast, keeps its release key in CI secrets (option c), which is simpler but riskier.

**A fact the research didn't have.** The repo's tooling can't sign with a hardware key yet. `os/update/README.md` says root keys on hardware tokens "need a token-backed signer, which is not built yet": `scripts/tuf-bootstrap-root.sh` signs with key files. So "hardware keys today" means waiting for code first.

**Options.**
- **(a) Wait for the hardware-key signer**, then run the ceremony on hardware keys. This is the most secure, but signed releases slip by the build time plus buying the keys.
- **(a′) Ceremony now with key files, hardware keys later.** Make three root keys as files, each on its own encrypted USB stick, with a 2-of-3 threshold, on an offline machine. Keep them in three places: home, off-site, and a trusted person for succession. Later, a TUF **root rotation** moves the root onto hardware keys. That rotation is the same drill the research wants before the first box ships, so it does double duty.
- **(b)** A cloud key service (KMS). It goes against "sovereign" and needs the cloud for every root change.
- **(c)** A single key in CI. Simplest, but one leaked CI secret owns every box.

**Recommendation: (a′).** It unblocks signed releases this week and keeps the 2-of-3 and offline rules. The weak point (key files rather than hardware) is temporary and gets fixed by the drill you need anyway. Steps:
1. **Rehearse:** run `scripts/tuf-bootstrap-root.sh rehearse <dir>` in a VM with networking off. It makes throwaway keys, so you can learn the steps safely.
2. **Real run:** use an offline machine. The Beelink booted from a Debian live USB with the network unplugged fits, since the script warns if it sees a network route. Run `create … security 2 <3 root keys> -- <targets.pub> <snapshot.pub> <timestamp.pub>`.
3. **Publish the public part:** commit `root.json` (public), and add the three online keys as GitHub environment secrets. The Claude builder can open the PR; only you touch private keys.
4. **Write the succession note:** where each stick is, and who may use one if you can't. Keep it in a sealed envelope, never in the repo.

**Also to decide (small):** "sovereign mode", meaning owners may replace their own box's Secure Boot keys. **Recommendation:** yes in principle, designed under Z-19 (#148), not built now.

**Unblocks:** #153, the first signed release and the downloads page (#66's page), the signed-upgrade test, the try-it demo (#243), plugin signing (#185). If you pick (a′), a new `owner:claude` issue follows for the hardware-key signer and the rotation drill.

---

## 3. #214 / F-25: order the hardware (LAB-01)

**In plain words.** Every real-metal gate waits on hardware. One date is fixed: the Pi soak test must start by **2026-12-11**. A soak test means running a box for weeks to catch slow failures such as memory leaks or a worn-out SD card. Shipping takes days to weeks, so ordering this week is the safe move.

**What's on the list** (`docs/HARDWARE.md` §2; prices as of Nov 2026, so check again at purchase):
- **Raspberry Pi 5 16 GB** + NVMe HAT + official 27 W power supply + case. The board was $305 per the Pi store. This is the Edge tier, the weakest point in the research. The bootc test (#5) runs on it too, on a **separate** SSD or card.
- **Raspberry Pi 5 4 GB** + NVMe for the soak, to test the small-box floor (Z-07).
- **Jetson Orin Nano Super** dev kit, $399 (secondary source). This is edge AI, not robotics, but **no gate before G1 needs it**, and D-006's tip is to apply to NVIDIA Inception first in case of discounts.
- **Meshtastic / LoRa radios** and a Zigbee/Thread dongle. These test the field mesh, which mostly serves TAK work, and TAK is parked with robotics. Not needed now.

**Options.**
- **(a) Order both Pi 5s + NVMe + a spare SSD now. Order the Jetson when Inception answers or by G2. Order the radios when TAK is unparked.**
- **(b)** Order everything now. More spend up front; the Jetson and radios would sit idle.
- **(c)** Wait. That risks missing the 2026-12-11 soak start.

**Recommendation: (a).** It's the smallest order that meets the fixed date and the bootc test. When the boxes arrive, record serials in the inventory (LT-X86-00 / PLAN-E1). Don't put serials in the public repo.

**Unblocks:** #215 (G1 on metal), #216, #217, #218 on metal, #150, #151, #244, the bootc test (#5), and the Pi soak.

---

## 4. Z-40: write down four scoring rules before the next test

**In plain words.** When the research scored base OSes, four choices were never written down, and each one alone could flip a close result. If you write them down **after** seeing a test result, it looks like bending the rules to fit the answer, which is the trap the research's rules exist to stop.

**What changed.** Under D-007 the base is Debian, so these rules no longer pick the base. They still decide how one result gets read: **if bootc passes on a real Pi 5, D-007 reopens**, and these rules then settle the bootc vs Debian comparison. The test plan says to log them **before** that test runs (`22-…` LT-PI5-02 prerequisite).

**The four rules** (`26-…` Z-40):
1. **Tie-break:** count rows across the full table, and a draw comes back to you.
2. **"Experimental" vendor support** scores 3 (`doc-only`) until the Pi test measures it.
3. **"Proven in production"** is scored on the base layer, not the whole stack.
4. **No third candidate** may enter a tie after scores are known.

**Options:** **(a)** adopt those four readings; **(b)** choose different readings, on the same timing; **(c)** leave them unwritten, in which case every close result comes back to you anyway.

**Recommendation: (a)**, logged in `research-output/evidence/scorecard-weights.md` §8 and as a D-entry before the Pi test. In practice, under D-007, (a) and (c) end the same way: a draw comes to you. (a) just makes that fair and on the record.

**Unblocks:** a clean reading of #5.

---

## 5. Z-10 / W2-HW-3: approve the bootc test on a real Pi 5

**In plain words.** bootc is Red Hat's way of shipping the whole OS as a container image. It's your year-2 Industrial profile (D-007). Its Pi 5 support is one person's experimental repo. **D-007's first reopen condition is "bootc passes on a real Pi 5"**, so this test is how you'd ever know whether that condition has happened. It must run before anything ships, because a box shipped on Debian + RAUC can't move to bootc without a full reinstall.

**Options:**
- **(a) Approve it**, run before G1 (2026-12-13) on the 16 GB Pi using its own SSD or card, after #4 is logged.
- **(b) Don't run it**, and accept that D-007's bootc reopen condition is never tested.
- **(c) Run it in year 2**, with the Industrial profile.

**Recommendation: (a).** It's about a day of bench time on hardware you're buying anyway (#3), and it either confirms D-007 or gives you a real reason to reopen it. Most likely it confirms Debian: if it fails, the research's own map gives Debian too.

**Unblocks:** the Industrial profile's evidence, and closes the open half of Z-10.

---

## 6. #253: virtual machines, a web terminal and Tor

**In plain words.** Competitors offer three things OneMind doesn't. Each touches a locked rule, so none gets built without your call.
- **Virtual machines** (Proxmox, Unraid, TrueNAS): run a whole other computer inside the box. The machines spike (`research-output/evidence/lab/machines-spike/RECOMMENDATION.md`) leans to KubeVirt as an optional extension, but **couldn't measure anything**: no virtualization in its sandbox. The deciding number, idle RAM on a Pi 5, is still unknown. VMs are heavy, and most boxes are 4–16 GB.
- **A web terminal** (Proxmox, CasaOS): a command line in the browser. Useful for rescue, but a terminal is the most powerful thing on the box, and **AI never actuates without human approval**, so agents must never reach it.
- **Tor** (StartOS, FreedomBox): an optional `.onion` address, so you can reach your box without opening ports or trusting a relay. It conflicts with default-deny egress (the box only talks out where it's allowed to) unless it's opt-in.

**Options per item:** yes / later / no.

**Recommendation:**
- **VMs: later.** Study only, x86 hubs with ≥ 16 GB, after metal measures the RAM cost (needs #3). Not on Pi.
- **Web terminal: yes, narrowly.** Owner-only, behind passkey login, inside the rescue console, every session audited, never exposed to agents or the API's AI tools.
- **Tor: later, opt-in.** Revisit after the mesh and relay work (#139, #236). Default off; it adds an egress exception.

**Your answer (2026-11-15, D-014): build all three now, with the guardrails.**
- **VMs (#281):** measured on real KVM hardware first (LT-MACH-2 on the Beelink); x86 hubs with ≥ 16 GB only, never on a Pi; owner approval for every machine action.
- **Web terminal (#273):** as above. It stays disabled until passkey sign-in exists (#236).
- **Tor (#284):** an optional Market app, never in the core OS. It gives the dashboard an onion address, needs per-device client keys, and is never an outbound proxy for apps or AI.

**Unblocks:** three roadmap rows. Codex gets a clear "don't build" on VMs and Tor, and the web terminal becomes an `owner:claude` issue (security-sensitive).

---

## How your answers get recorded

1. You reply, for example: "Z-41 d, Z-04 a′, #214 a, Z-40 a, Z-10 a, #253 as recommended."
2. A docs PR adds D-009 onward to `docs/DECISIONS.md`, with your words quoted and the date.
3. The waiting issues lose `needs-founder`, and any new issues (hardware-key signer, web terminal) get `owner:` and `wave:` labels so the agents pick them up.

**Sources:** `research-output/26-OPEN-QUESTIONS-FOR-ZEUS.md` (Z-04, Z-10, Z-40, Z-41, §H, §I), `research-output/22-HARDWARE-LAB-TEST-PLAN.md` (LT-PI5-02, LT-VM-20), `docs/DECISIONS.md` (D-004, D-006, D-007), `docs/HARDWARE.md` §2, `os/update/README.md`, `scripts/tuf-bootstrap-root.sh`, `docs/leap/ALPHA-CHECKLIST.md`, issues #153, #214, #253.
