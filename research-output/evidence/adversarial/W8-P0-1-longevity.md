# W8 P0-1 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | P0-1 (`09-iot-mesh-offgrid-tak.md` §0): gate G4 is not failed by Debian 13 + Rugix + k3s. The result is CONDITIONAL, with four mitigations: a Pi 5 PREEMPT_RT kernel, a packaged FDO client, an MQTT 5 broker app and a 10k-device fleet test. DC-02's flip condition is not met, so ADR-001 D2/D3 stand on IoT/IIoT grounds. |
| Lens | Longevity and vendor risk: who maintains each part over a 10-year industrial lifecycle, and what happens if they stop. |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter read only the P0 row, its "what would flip" line and the cited claim rows (C-W8-001…006, 033, 037, 038, 044, 046, 049, 050). It did not read the author's §1 reasoning or the other adversarial files before forming this view. |
| Date | 2026-11-11. Re-check contributor counts and ELTS architecture coverage by 2027-05-11. |
| Verdict | **weakened** |
| New ledger rows | `evidence/claims/REF-W8-longevity.csv` (C-REF-W8-longevity-001…005) |

## 1. The cited sources, read through this lens

| Cited claim | What it shows | Longevity gap |
|---|---|---|
| C-W8-001…006 (Debian trixie kernel and packages) | The protocols, RT, mesh, DPP and TSN pieces are in Debian today. | They prove the parts exist in 2026. They say nothing about who patches them after Debian LTS ends on 2030-06-30, or on arm64. |
| C-W8-044 (go-fdo) | A maintained Go FDO library exists. Its README says it has not finished FIDO interop testing. | The maintainer base is small (see §2 C). |
| C-W8-046 (Rugix fleet integrations) | Rugix Ctrl stays independent of the fleet backend and integrates with Nexigon, thin-edge.io, Memfault and Mender. | Backend independence is good. The update engine itself has one maintainer (see §2 A). |
| C-W8-049 (k3s sizing), C-W8-050 (NATS leaf lab) | These are sizing and behaviour facts. | NATS had a governance shock in 2025 (see §2 D). |
| C-W8-033, 037, 038 (Moxa, Siemens) | Industrial vendors ship Debian. | Both vendors sell their own paid long-term support on top of Debian. OneMind would have to supply the same (see §2 B). |

## 2. Strongest counter-argument

G4 is scored as a snapshot: "does a sub-check FAIL today?" For a product that tells factories and public-safety users it will "never hit a wall", the real IIoT blocker is often the **maintenance horizon**, not a missing protocol. On that axis, the chosen stack has three single points of failure that none of the four mitigations addresses.

**A. Rugix is in practice a one-person project.** The GitHub contributors API for `rugix/rugix` (queried 2026-11-11) gives `koehlma` 1,161 commits. The next six contributors have 4, 2, 1, 1, 1 and 1. That is about 99% of commits from one person [C-REF-W8-longevity-001]. Rugix's own "About" page says it is "created and maintained by Silitics, an independent company owned and led by its founder Maximilian Köhl". It is funded by "engineering services, support, and Nexigon, its commercial fleet management platform" [C-REF-W8-longevity-002]. Rugix is Apache-2.0, so it can be forked. But the A/B update engine is the most safety-critical code in the field fleet. If its maintainer leaves, OneMind becomes the maintainer. The G4 sub-checks never test this.

**B. Debian 13 support past 2030 is paid, and arm64 coverage is not confirmed.** Freexian's Trixie page gives three dates. Security support passes to Debian LTS on 2028-08-10. Debian support ends 2030-06-30. Freexian's Extended LTS runs to 2035-06-30. Its quotes are specific: "the support for amd64 during the whole Extended LTS period of Trixie is confirmed". The other architectures depend "on the request of our customers". Base-system packages are covered only "as long as we have customers paying for Debian 13 support" [C-REF-W8-longevity-003]. The Pi 5 and Jetson boards in P-8 are **arm64**. A device sold in 2027 has about 3.5 years of free Debian security support. After that, OneMind must pay for ELTS (and request arm64) or rebase the fleet onto Debian 14 through Rugix. Moxa's MIL4 support runs to Aug 2035 [C-W8-033], close to the ELTS end date. That suggests Moxa buys or does this work itself. It does not suggest the work is free.

**C. The FDO mitigation rests on a thin, shrinking codebase.** In the `fido-device-onboard` GitHub org, the C device SDK `client-sdk-fidoiot` is now a **public archive** [C-REF-W8-longevity-005]. Among go-fdo's top ten contributors, dependabot has 106 commits. The ten human contributors have about 33 together, and the largest has 18 [C-REF-W8-longevity-005]. Combined with the interop warning in C-W8-044, "package an FDO client" is closer to adopting a young library than to packaging a finished one.

**D. The bus has already had one relicensing scare.** In 2025, Synadia proposed withdrawing NATS from the CNCF. Its proposal said: "Upon leaving CNCF, Synadia will adopt the [BUSL] for the NATS.io server." On 2025-05-01 the CNCF and Synadia announced an agreement that keeps NATS in the CNCF [C-REF-W8-longevity-004]. This was resolved, and the risk is lower now that the trademark has gone to the Linux Foundation. Still, the stack's backbone has a primary commercial steward that once tried to move to a source-available license.

**Why this is "weakened" and not "refuted".** None of these is a blocker today, and the alternatives carry the same kinds of risk: RHEL/bootc has subscription lock-in, and CIP Core needs CIP membership or its own Isar build work. DC-02's flip condition needs a FAIL for Debian + Rugix **and** a PASS for an alternative. On longevity, no alternative clearly passes either. But P0-1 says "ADR-001 D2/D3 stand" without a fifth condition: a funded 10-year maintenance plan. Its four mitigations are all engineering tasks, and none is a support-horizon task.

## 3. Required changes for the author

1. Add a fifth G4 condition, "(f) maintenance horizon". It needs a written exit plan for Rugix (fork-and-maintain cost, or a switch to RAUC or SWUpdate), and an ELTS arm64 quote from Freexian or a Debian 14 rebase plan before 2030-06.
2. Change the FDO mitigation from "package a client" to "adopt go-fdo and fund interop testing". Note that the C SDK is archived.
3. Downgrade the confidence for (a)–(d) from High to Medium-High on the longevity axis.

## 4. What would flip the decision

- **Towards refuted:** Freexian declines arm64 ELTS for trixie, Rugix has no release or commit for 6+ months, or Silitics is acquired or wound down. Any of these would leave Debian + Rugix without a 10-year path on the Pi 5 and Jetson. Separately, an alternative (for example, CIP Core on SLTS kernels with SWUpdate) would have to show a confirmed arm64 support horizon to 2036 or later.
- **Towards upheld:** a second independent maintainer or company takes on Rugix (two or more people with more than 10% of commits each over 12 months). Freexian confirms arm64 ELTS for trixie. go-fdo passes FIDO interop testing.

## 5. Sources opened by this refuter (new)

- `https://api.github.com/repos/rugix/rugix/contributors`, queried with `gh api` on 2026-11-11
- https://rugix.org/docs/the-rugix-project/
- https://www.freexian.com/lts/extended/docs/debian-13-support/
- https://www.cncf.io/blog/2025/05/01/protecting-nats-and-the-integrity-of-open-source-cncfs-commitment-to-the-community/
- https://github.com/fido-device-onboard and `https://api.github.com/repos/fido-device-onboard/go-fdo/contributors`

Not archived by this refuter. The author must archive these under rule 1.
