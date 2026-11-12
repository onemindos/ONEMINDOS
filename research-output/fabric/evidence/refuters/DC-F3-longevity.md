<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F3 refuter, longevity lens (FDO part)

**Claim given:** FDO (go-fdo) as the zero-touch front end. **Cited:** C-FB2-003, C-G4U-004…006, C-W8-042…044.

**Strongest counter-argument.** The FDO software base keeps shrinking: Fedora's Rust implementation was deprecated in 2026 (C-W8-043, mission 01) and Intel's C client SDK is archived (C-REF-W8-longevity-005); the remaining Go library has one dominant human contributor (18 of its last human commits; next 6) [C-FBREF-010] and no completed FIDO interop testing (C-G4U-006). This run also found that go-fdo-server v1.0.2 has no voucher delete API [C-LAB-fb2-fdo-enroll-010].

**New sources:** C-FBREF-010 (contributors API), C-LAB-fb2-fdo-enroll-010 (route list at the tag).

**Verdict: weakened.**

**What would flip it:** go-fdo going a year without a release, or Red Hat dropping its packaging (C-STEEL-IIOT-001/002/004) → keep only the ticket + pairing path, and use IDevID + a OneMind enrolment service for sold hardware.

**Response (author).** Accepted: FDO stays **optional** and behind an interface; the universal path does not depend on it; go-fdo-server shows healthier activity (34 commits in six months, Red Hat edge-team tickets) [C-FBREF-010]; revisit at the 12-month re-check.
