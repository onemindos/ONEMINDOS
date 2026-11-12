# Lab pre-registration register

Each row records when a spike's goal, hypotheses and pass/fail criteria were frozen, and the sha256 of its README at that moment (before any build or test ran). A later README differs from this hash only by the Results section appended below its "Results" line.

| Spike | Criteria written (UTC) | README sha256 at freeze |
|---|---|---|
| minimal-image-dc20 | 2026-11-11T07:12Z | `51c48b24d870a8afb1c7cf9ea6232727565ff8e20b53958ca7f5214cfa09cb35` |
| rauc-1152 | 2026-11-11T07:12:17Z | `495591aedaed233abcd0dae5b6cce890eb1997c0dff543a0aa2f08aecf1da828` |
| ubuntu-2604-leg | 2026-11-11T07:12Z | `1ada29b4e96d57d11e0f5553063c944fcc425d6be5cd6028f32fd307050f75f1` |
| mender | 2026-11-11T07:14Z | `f99e1011e32904bfa67fc493c861d4ba64dbbad9aaee6f5f1926508b7904ca8f` |
| aarch64-gate | 2026-11-11T12:12:00Z | `01923bee617a75f62023a8a978c267e655f4373f01d5412a6427843cd4cedfd4` |
| secureboot-1152 | 2026-11-11T12:11:49Z | `0e437bd424a122c5c891b7afba38cb84c7eab0f4931a9001da89476e7050ca28` |
| ubuntu-secureboot (U-SB, FIX5) | 2026-11-11T15:51:12Z | `c98a09d1d89f3b25184986b2711e9276aa548014246b9ede6c34c8e981e8f8db` |
| fb3-mesh-nat (fabric mission 02, lab test 1) | 2026-11-12T07:37:48Z | `52573fc062cbf02a06884a5235d46c2b5884a9be3e046185d05abb3626cff39b` |
| machines-spike (machines.md §4.1, F-56: KubeVirt vs own QEMU + noVNC) | 2026-11-12T11:23:12Z | `66dad152319a9587bf0916c910d42783cba9b394ca0d3cc8e3287d5d34aa8fca` |

**U-SB's frozen rule (SYNC5 note, 2026-11-11, critic P5-3).** The `ubuntu-secureboot` README §4 freezes the `01` §3.1.6 (h) map rows word for word, and `22` LT-VM-20 and `20` (G1, G6, §5.4) now quote the same rows: **PASS** = T0–T6 and T8 pass in **two** full runs with only the changes its §3 allows → "U-SB passes unchanged in two runs" (D stays; D·C3 loses `doc-only`). **FAIL** = any T1–T6 or T8 guest-side failure in any run, **or** a pass that needs a partition or bootloader change → D·C3 4 → 3 → **C (RHEL-family bootc)**. **BLOCKED** = not run, no map event. Its README was BLOCKED at 15:56Z; on 2026-11-11 SYNC5 edited only text **below** its `## Results` line (a corrected sentence and a timing section R.5). The first 65 lines (through `## Results`) still hash to `c98a09d1…f8db`, checked after the edit.

## Index of every spike (added 2026-11-11 by the HYG agent, critic pass-2 gap #17)

The table above covers only spikes frozen from 07:12Z on 2026-11-11 onward, and is maintained by those spikes' agents. This index covers **every** spike folder in `evidence/lab/`, including the earlier ones.

> **Honest note.** For all spikes before `rauc-1152`, the criteria were **committed together with their results**: the first-round labs (debian-rugix, fedora-bootc, k3s-footprint-restore, rauc, w2-fedora-bootc-greenboot, w4-k3s-footprint, w5-restore, w8-nats-leaf-buffer, w18-mac-toolchain) all landed in commit `414d60a` (2026-11-11T04:13:48Z) with their logs, and rauc-k3s-gate, secureboot-rauc and w19-sysext landed in `ee98bc7` (2026-11-11T07:08:00Z) with theirs. Git therefore cannot prove that any of their criteria were written before the run. The "written before running" lines in their READMEs, and the two run-time hash files noted below, are **self-attested** (local file times on the lab host, which the author controls). Treat their pass/fail verdicts as the author's honest record, not as audited pre-registration. Spikes from `rauc-1152` on record a README hash and UTC time before any build; a third party can check those by truncating the README at its Results heading.

"README sha256 now" is the hash of the README in the working tree on 2026-11-11 (after results were appended). It changes if anyone edits the README; `SHA256SUMS` in each folder records the other files.

| Spike | README sha256 now | First commit | Criteria location | Pre-run evidence | Verifiable? |
|---|---|---|---|---|---|
| debian-rugix | `5ab23c1402dc401da8306615f9cb5c8231d97095f4bf899c0a7e444f1072a52c` | `414d60a` | README §3–6; results §7 | none | No: committed with results |
| fedora-bootc | `62717f84cfd1752c3ce03b3546620fd8b912af6a8b8ab5b3c84397de7bbf26b7` (masked; was `5640675d…3edb`, see Masking log) | `414d60a` | README test table; results from "Results" on | none | No: committed with results |
| k3s-footprint-restore | `fd5a55ebe950c9306985d8e1ffd092ad9368bbdd497acbd10bfced77b9fc16ce` | `414d60a` | README H1–H4, R1–R3; results from "Results" on | "Written before running: 2026-11-10" (self-attested) | No |
| rauc | `7d4e3ab0ad4fac2bd2ee5ad55933c6059a351fb84f0475fa88700eb7bb18ef6b` (masked; was `c2cad45e…8a08`, see Masking log) | `414d60a` | README §3 "frozen before the run"; results §7 (run 4, so criteria survived three earlier runs) | none | No |
| w2-fedora-bootc-greenboot | `35020b361915b6eb70e9e7d46cd65f64f7efcc8972bbe59c9a4be9edcb9bc5a9` | `414d60a` | README "Pass / fail criteria (written before running)"; results in README "Result" and `RESULT.md` | none | No |
| w4-k3s-footprint | `f4022c4cf633d786f2d9596b6d3154c689f865d84144d61e9409201d223768f1` | `414d60a` | README (criteria only); results in `RESULT.md` | **Run-time `inputs.sha256` (file time 2026-11-11T01:13Z) holds exactly this README hash**, and the run log ends at 02:16Z | Partly: the README is unchanged since the pre-run hash, but the hash file's time is self-attested |
| w5-restore | `b9f663fd8a842ca68be1a0dd50ec60d60a3e9dc1c890041b2be45a62134afe52` | `414d60a` | README H1–H4 (criteria only); results in `logs/` | Run-time `SHA256SUMS` written **after** the drills (01:29Z) with the same README hash | No: it shows the README was not changed after the run, not that it came first |
| w8-nats-leaf-buffer | `a635ae72bfe0bb3b257a3d83d9eaa7bdaff76e23272f8c650a48e6564c21e7c2` | `414d60a` | README (criteria only); results in `results.md` | "Written before running: 2026-11-10" (self-attested) | No |
| w18-mac-toolchain | `b3a07a02adcb77a45c16ba5db27c2f5489ade9f8236b1114e1d09f0492ca2785` | `414d60a` | README H1–H5 **and** results in the same file | run-time `SHA256SUMS-lab` (01:20Z) written after the run | No: criteria and results share one file |
| rauc-k3s-gate | `4429d2230ab9d36a51931e5135c3fe8d9b984c58b9c2aff5f8f9c5efdb2d281e` (masked; was `74878b61…2689`, see Masking log) | `ee98bc7` | README §3 "frozen before the run"; results §7 | none | No: committed with results |
| secureboot-rauc | `ebe6adc1f322f692405cc2bbef133064e1c5f24f4a4daf16edb2f4ff1c5b21dc` (masked; was `8c0c3cf5…f2fe8`, see Masking log) | `ee98bc7` | README §4; results §7; exploratory E1 §9 is labelled "not pre-registered" | `PREREGISTRATION.sha256`: `f48e345f…bec7c` at 2026-11-11T04:22:39Z | **No match on 2026-11-11:** no byte prefix of the current README hashes to `f48e345f…`, because the header's Status line (line 3) was rewritten after the run. The criteria text may be unchanged, but that cannot be shown from the hash |
| w19-sysext | `2b4fd09df76da79c4fa0d1ba1d9b7120d2e75b67b1bf6a5c650d293cf969400d` | `ee98bc7` | README criteria; results "appended after the run, 2026-11-11T04:30Z" | "Written before running: 2026-11-11T04:27:31Z" (self-attested) | No |
| rauc-1152 | `495591aedaed233abcd0dae5b6cce890eb1997c0dff543a0aa2f08aecf1da828` | uncommitted | README §3 | registered above, 07:12:17Z | **Yes:** on 2026-11-11 the whole current README hashes to the frozen value (no results appended yet) |
| minimal-image-dc20 | `51c48b24d870a8afb1c7cf9ea6232727565ff8e20b53958ca7f5214cfa09cb35` | uncommitted | README §2–3 | registered above | Yes, while unchanged |
| fb3-mesh-nat | `e5407a971158329756ab60e9a1808b71b759145c522076309be2b68b536623d1` (results appended) | `70d3aa7` (criteria only, before the run) | README §3; results from "Results" on | registered above, 2026-11-12T07:37:48Z, and committed alone before any VM existed | **Yes:** the README truncated at `## Results`, with the Status line set back as `PREREGISTRATION.sha256` says, hashes to `52573fc0…f39b` (checked 2026-11-12 after the run) |
| ubuntu-2604-leg | `1ada29b4e96d57d11e0f5553063c944fcc425d6be5cd6028f32fd307050f75f1` | uncommitted | README §3 | registered above | Yes, while unchanged |
| mender | `f99e1011e32904bfa67fc493c861d4ba64dbbad9aaee6f5f1926508b7904ca8f` | uncommitted | README §3 (copy in `<lab-dir>/mender/README.prereg.md`) | registered above | Yes, while unchanged |
| aarch64-gate *(row added by SYNC5)* | `2e4284257f575924a19a9f3a13117543b082f0d940bee5f2d6debbb09098b8b9` | `b933b86` | README up to `## Results` | registered above, 12:12:00Z; `PREREGISTRATION.sha256` | **Yes**, by the recipe in its `PREREGISTRATION.sha256` (restore the Status line, truncate after `## Results`): gives `01923bee…fdd4`, checked 2026-11-11 |
| secureboot-1152 *(row added by SYNC5)* | `6e44e79076eee9dfe57cb2f12af7cf429d5fbf8b0bca3af3c04c265f9428e2c5` (masked; see Masking log) | `b933b86` | README §4 | registered above, 12:11:49Z | **Yes**: lines 1–59 hash to `0e437bd4…ca28`, checked 2026-11-11 |
| ubuntu-secureboot (U-SB) *(row added by SYNC5)* | `f8376ec4ee9832aa15d362d2ae0c3ecf14a9767468b99eaf4722172867353761` (after the SYNC5 R.5 edit) | `b933b86` (the frozen part and the BLOCKED result) | README §4 (the `01` §3.1.6 h wording) | registered above, 15:51:12Z | **Yes**: lines 1–65 hash to `c98a09d1…f8db`, checked 2026-11-11 after the SYNC5 edit. Verdict BLOCKED, so no criterion has yet been tested |

## Masking log (2026-11-11, critic pass-3 P3-10)

Eleven lab files named the lab host's folder layout (a home-relative path to the lab folder, with no account name). The path was replaced: in READMEs by `<lab-dir>/<spike>`, and in scripts by `LAB=${LAB:?"set LAB to <lab-dir>/<spike>"}`, so a script stops with an error instead of falling back to a host path. **Only that path changed; no criterion, result or log was touched, and nothing was re-run.**

**Why the pre-registration record still holds.** Every README edit is in a "How to re-run" block **below** the README's `## Results` heading, which is where this register allows later changes (header note above). The frozen part is unchanged: for `secureboot-1152`, the first 59 lines (through `## Results`) still hash to the frozen value `0e437bd4…ca28`, checked before and after the edit. The ten files already in git can be compared byte for byte with their unmasked originals in the commit named below (`git show <commit>:<path> | shasum -a 256` gives the "original" column). `secureboot-1152` is not yet committed, so its original exists only as the hash below.

| File (under `evidence/lab/`) | Original sha256 (unmasked) | Masked sha256 (now) | Original in commit | Hash also updated in |
|---|---|---|---|---|
| `fedora-bootc/README.md` (line 84) | `5640675d486ba249f83c67557195d3939775b9bb64cce52778d4225920533edb` | `62717f84cfd1752c3ce03b3546620fd8b912af6a8b8ab5b3c84397de7bbf26b7` | `414d60a` | `fedora-bootc/SHA256SUMS`, index above |
| `fedora-bootc/scripts/lab.sh` (line 3) | `98b21c4b1eda3e5ffc7b8b31a438a09ebc9ac05130f9b0240d157260cbba13df` | `1689ad7306c0e112b414077879fd8361794677fb05e14b50a0b729752046f520` | `414d60a` | `fedora-bootc/SHA256SUMS` |
| `fedora-bootc/scripts/run-vm.sh` (line 7) | `eb27c565f3b9f8899f49ea42ea73e92031a8f12490d95e8385019bf6328af4b1` | `ae4198b812e9a522766f8e58eb4c64a38f631f8e3d3b0a742072a963b0e48dd8` | `414d60a` | `fedora-bootc/SHA256SUMS` |
| `k3s-footprint-restore/scripts/host-fetch.sh` (line 4) | `9c11402de0cff6bc39c6e5c15a9f2709c41d159621848a2c7a71368e6830eca4` | `5ec17a38d34dda1248844bc40e2af54e6eba952f5400d8dfe1e8f8c4796de012` | `414d60a` | `k3s-footprint-restore/SHA256SUMS` |
| `k3s-footprint-restore/scripts/host-restore.sh` (line 6) | `ea63dd31938927c37798aca091efcfa5bcd3f9eaa982b0df6fd6974de42fe048` | `41dcc58976c858ffc1e2538c950cd989be572f59246059f615bf9c6ccac114ed` | `414d60a` | `k3s-footprint-restore/SHA256SUMS` |
| `k3s-footprint-restore/scripts/host-source.sh` (line 6) | `86b2bc64b2588ec93896be8a6d6542837418bbaea6bdfa735c7842bf5056db04` | `6849edd09a214d2b77a163aa5eda08d6bbc910d886a1fcf7b55c357336f97bb6` | `414d60a` | `k3s-footprint-restore/SHA256SUMS` |
| `k3s-footprint-restore/scripts/run-all.sh` (line 5) | `dc9076d1a843d1b23544c0edc83437af55939dcdb1e4cad504e0f7151359a495` | `4006df7e916aeb71433387dd9136bc5636fb87a8b01bc0b067184a56333c5bc7` | `414d60a` | `k3s-footprint-restore/SHA256SUMS` |
| `rauc/README.md` (line 170) | `c2cad45e1a407ff2b303174396097f0098dbb760d7a3267fbecdbd88e9d48a08` | `7d4e3ab0ad4fac2bd2ee5ad55933c6059a351fb84f0475fa88700eb7bb18ef6b` | `414d60a` | index above (no `SHA256SUMS` entry for the README) |
| `rauc-k3s-gate/README.md` (line 189) | `74878b6114e1346335b7c34de7d654302c3709ca2e52d423c8782059d0312689` | `4429d2230ab9d36a51931e5135c3fe8d9b984c58b9c2aff5f8f9c5efdb2d281e` | `ee98bc7` | index above (no `SHA256SUMS` entry for the README) |
| `secureboot-rauc/README.md` (line 173) | `8c0c3cf5b18fe9c8f86cc5560d634e685d473585bbe8dc8b812e443aa98f2fe8` | `ebe6adc1f322f692405cc2bbef133064e1c5f24f4a4daf16edb2f4ff1c5b21dc` | `ee98bc7` | index above. Its run-time `PREREGISTRATION.sha256` (`f48e345f…`) is left as written; it already did not match (index row) |
| `secureboot-1152/README.md` (line 127) | `62ad02aee6fda7ad08eafe37b1359a5cf2da6060a449821ab6db5e6fb8216f7d` | `6e44e79076eee9dfe57cb2f12af7cf429d5fbf8b0bca3af3c04c265f9428e2c5` | uncommitted | `secureboot-1152/SHA256SUMS`. Frozen prefix (lines 1–59) unchanged: `0e437bd4…ca28` before and after |

`shasum -a 256 -c SHA256SUMS` passes for every committed file in `fedora-bootc/`, `k3s-footprint-restore/` and `secureboot-1152/` after the update. (`secureboot-1152/SHA256SUMS` also lists run-time artifacts such as bundles and disk images that were never committed; those lines could not be checked before this edit either.)

**How to make future pre-registration provable:** commit (or at least push) the README with criteria **before** the first build, in its own commit, and append results only below the Results heading without touching anything above it. A commit on the public branch carries a server-side push time that the author does not control; a local file time does.
