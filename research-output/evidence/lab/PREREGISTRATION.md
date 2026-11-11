# Lab pre-registration register

Each row records when a spike's goal, hypotheses and pass/fail criteria were frozen, and the sha256 of its README at that moment (before any build or test ran). A later README differs from this hash only by the Results section appended below its "Results" line.

| Spike | Criteria written (UTC) | README sha256 at freeze |
|---|---|---|
| minimal-image-dc20 | 2026-11-11T07:12Z | `51c48b24d870a8afb1c7cf9ea6232727565ff8e20b53958ca7f5214cfa09cb35` |
| rauc-1152 | 2026-11-11T07:12:17Z | `495591aedaed233abcd0dae5b6cce890eb1997c0dff543a0aa2f08aecf1da828` |
| ubuntu-2604-leg | 2026-11-11T07:12Z | `1ada29b4e96d57d11e0f5553063c944fcc425d6be5cd6028f32fd307050f75f1` |
| mender | 2026-11-11T07:14Z | `f99e1011e32904bfa67fc493c861d4ba64dbbad9aaee6f5f1926508b7904ca8f` |

## Index of every spike (added 2026-11-11 by the HYG agent, critic pass-2 gap #17)

The table above covers only spikes frozen from 07:12Z on 2026-11-11 onward, and is maintained by those spikes' agents. This index covers **every** spike folder in `evidence/lab/`, including the earlier ones.

> **Honest note.** For all spikes before `rauc-1152`, the criteria were **committed together with their results**: the first-round labs (debian-rugix, fedora-bootc, k3s-footprint-restore, rauc, w2-fedora-bootc-greenboot, w4-k3s-footprint, w5-restore, w8-nats-leaf-buffer, w18-mac-toolchain) all landed in commit `414d60a` (2026-11-11T04:13:48Z) with their logs, and rauc-k3s-gate, secureboot-rauc and w19-sysext landed in `ee98bc7` (2026-11-11T07:08:00Z) with theirs. Git therefore cannot prove that any of their criteria were written before the run. The "written before running" lines in their READMEs, and the two run-time hash files noted below, are **self-attested** (local file times on the lab host, which the author controls). Treat their pass/fail verdicts as the author's honest record, not as audited pre-registration. Spikes from `rauc-1152` on record a README hash and UTC time before any build; a third party can check those by truncating the README at its Results heading.

"README sha256 now" is the hash of the README in the working tree on 2026-11-11 (after results were appended). It changes if anyone edits the README; `SHA256SUMS` in each folder records the other files.

| Spike | README sha256 now | First commit | Criteria location | Pre-run evidence | Verifiable? |
|---|---|---|---|---|---|
| debian-rugix | `5ab23c1402dc401da8306615f9cb5c8231d97095f4bf899c0a7e444f1072a52c` | `414d60a` | README §3–6; results §7 | none | No: committed with results |
| fedora-bootc | `5640675d486ba249f83c67557195d3939775b9bb64cce52778d4225920533edb` | `414d60a` | README test table; results from "Results" on | none | No: committed with results |
| k3s-footprint-restore | `fd5a55ebe950c9306985d8e1ffd092ad9368bbdd497acbd10bfced77b9fc16ce` | `414d60a` | README H1–H4, R1–R3; results from "Results" on | "Written before running: 2026-11-10" (self-attested) | No |
| rauc | `c2cad45e1a407ff2b303174396097f0098dbb760d7a3267fbecdbd88e9d48a08` | `414d60a` | README §3 "frozen before the run"; results §7 (run 4, so criteria survived three earlier runs) | none | No |
| w2-fedora-bootc-greenboot | `35020b361915b6eb70e9e7d46cd65f64f7efcc8972bbe59c9a4be9edcb9bc5a9` | `414d60a` | README "Pass / fail criteria (written before running)"; results in README "Result" and `RESULT.md` | none | No |
| w4-k3s-footprint | `f4022c4cf633d786f2d9596b6d3154c689f865d84144d61e9409201d223768f1` | `414d60a` | README (criteria only); results in `RESULT.md` | **Run-time `inputs.sha256` (file time 2026-11-11T01:13Z) holds exactly this README hash**, and the run log ends at 02:16Z | Partly: the README is unchanged since the pre-run hash, but the hash file's time is self-attested |
| w5-restore | `b9f663fd8a842ca68be1a0dd50ec60d60a3e9dc1c890041b2be45a62134afe52` | `414d60a` | README H1–H4 (criteria only); results in `logs/` | Run-time `SHA256SUMS` written **after** the drills (01:29Z) with the same README hash | No: it shows the README was not changed after the run, not that it came first |
| w8-nats-leaf-buffer | `a635ae72bfe0bb3b257a3d83d9eaa7bdaff76e23272f8c650a48e6564c21e7c2` | `414d60a` | README (criteria only); results in `results.md` | "Written before running: 2026-11-10" (self-attested) | No |
| w18-mac-toolchain | `b3a07a02adcb77a45c16ba5db27c2f5489ade9f8236b1114e1d09f0492ca2785` | `414d60a` | README H1–H5 **and** results in the same file | run-time `SHA256SUMS-lab` (01:20Z) written after the run | No: criteria and results share one file |
| rauc-k3s-gate | `74878b6114e1346335b7c34de7d654302c3709ca2e52d423c8782059d0312689` | `ee98bc7` | README §3 "frozen before the run"; results §7 | none | No: committed with results |
| secureboot-rauc | `8c0c3cf5b18fe9c8f86cc5560d634e685d473585bbe8dc8b812e443aa98f2fe8` | `ee98bc7` | README §4; results §7; exploratory E1 §9 is labelled "not pre-registered" | `PREREGISTRATION.sha256`: `f48e345f…bec7c` at 2026-11-11T04:22:39Z | **No match on 2026-11-11:** no byte prefix of the current README hashes to `f48e345f…`, because the header's Status line (line 3) was rewritten after the run. The criteria text may be unchanged, but that cannot be shown from the hash |
| w19-sysext | `2b4fd09df76da79c4fa0d1ba1d9b7120d2e75b67b1bf6a5c650d293cf969400d` | `ee98bc7` | README criteria; results "appended after the run, 2026-11-11T04:30Z" | "Written before running: 2026-11-11T04:27:31Z" (self-attested) | No |
| rauc-1152 | `495591aedaed233abcd0dae5b6cce890eb1997c0dff543a0aa2f08aecf1da828` | uncommitted | README §3 | registered above, 07:12:17Z | **Yes:** on 2026-11-11 the whole current README hashes to the frozen value (no results appended yet) |
| minimal-image-dc20 | `51c48b24d870a8afb1c7cf9ea6232727565ff8e20b53958ca7f5214cfa09cb35` | uncommitted | README §2–3 | registered above | Yes, while unchanged |
| ubuntu-2604-leg | `1ada29b4e96d57d11e0f5553063c944fcc425d6be5cd6028f32fd307050f75f1` | uncommitted | README §3 | registered above | Yes, while unchanged |
| mender | `f99e1011e32904bfa67fc493c861d4ba64dbbad9aaee6f5f1926508b7904ca8f` | uncommitted | README §3 (copy in `<lab-dir>/mender/README.prereg.md`) | registered above | Yes, while unchanged |

**How to make future pre-registration provable:** commit (or at least push) the README with criteria **before** the first build, in its own commit, and append results only below the Results heading without touching anything above it. A commit on the public branch carries a server-side push time that the author does not control; a local file time does.
