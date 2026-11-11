# W19 · E9 trust root: refuter, longevity and vendor-risk lens

**Target conclusion** (`29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` §1 E9, §8.2–8.4; `01-FOUNDATION-DECISION.md` §4.8 E9 row): frozen-v1 trust root of publisher signing, OneMind countersignature, exact-digest pinning, a signed revocation ("kill") list fetched like HACS every 6 h, and plugin API levels. Rev. 2 adds TUF-style expiry, so an offline box past expiry refuses new host grants, and OCI-native signatures under the same root as RAUC.

**Verdict: WEAKENED.** The design is right for year one. It has no plan for the trust root's own lifetime, or for OneMind as a vendor disappearing.

## Strongest counter-argument
A trust root on fielded appliances is a 10–15-year liability, and it fails in slow, predictable ways:
1. **Roots expire on fielded hardware.** Microsoft's 2011 Secure Boot CAs (KEK on 2026-06-24, UEFI CA on 2026-06-27, Windows PCA on 2026-10-19) expired in the field this year. Devices without the 2023 certificates keep booting, but "can no longer receive new security protections for the early boot process," including revocation-list (DBX) updates [C-REF-W19-longevity-009]. E9 puts plugin signing "under the same root as RAUC." That couples a plugin-key rotation to the OS-update root, and the OS-update root to every box that missed an update window. Neither E9 nor §8.2 says when OneMind's root expires or how an offline box rotates it.
2. **Format and spec upgrades strand old verifiers.** Sigstore's 2024 TUF root update had "no functional changes." Even so, Cosign before v2.2.0, all of Cosign v1.x and sigstore-rust could not load it [C-REF-W19-longevity-008]. Choosing "Sigstore/cosign or Notation" does not fix this. A box whose verifier is older than the store's metadata format stops accepting plugins. That is likely on the offline, rarely updated boxes OneMind targets (USB-bundle updates).
3. **An expiring revocation list hands control to OneMind's survival.** With TUF expiry, a box that can't get a fresh list "refuses new host grants." If OneMind is acquired, shuts down or loses its signing HSM, every box in the field loses the ability to add drivers, profiles and robot grants once the last list expires. Users can't fix that without the very owner override §8.4 grants only for "self-built/private plugins." This is the vendor-lock risk MISSION's sovereignty goal forbids. No continuity mechanism is named: no key escrow, no published sunset key, no owner re-rooting.
4. **Kill lists are rarely used, so their failure modes are untested.** E9's precedent is HACS's 6-hourly list [C-W19-015]. That list has held only a `test/test` entry since 2019-11-01 [C-REF-W19-longevity-001]. E9 would be the first production use of this mechanism on hardware that moves.
5. **Signing provenance ages.** Trusted publishing and provenance, the publisher half of E9, were used as the attack vector in 2026 [C-REF-W19-longevity-006]. A frozen-v1 publisher-identity contract needs a way to add new attestation requirements without breaking published plugins.

## New sources
C-REF-W19-longevity-001, 006, 008, 009 in `evidence/claims/REF3-W19-longevity.csv`. All were opened. 008 and 009 are new to W19.

## What would flip it
- **To upheld:** E9 gains (a) a written root lifetime and offline rotation path, rehearsed on a box that skipped N updates; (b) verifier compatibility: the box's verifier is pinned in the RAUC image, and the store keeps the old format for the full support window; (c) a vendor-exit clause: escrowed or published re-rooting key, or owner re-rooting under physical presence, so boxes outlive OneMind.
- **To refuted:** a lab where a box that missed one root rotation can't be recovered without reflashing, or a design that keeps the expiry-locks-grants rule with no exit path.

**Recommendation to the author (not applied):** add an "E9 lifetime" sub-row: root validity and rotation cadence, verifier-format compatibility window, owner re-rooting under physical presence, and a public "if OneMind stops" plan (escrow or a key-release trigger). Make "list expired" degrade to *no new third-party host grants* while existing ones and owner-signed private ones keep working. 01 already implies this. Write it as a contract.
