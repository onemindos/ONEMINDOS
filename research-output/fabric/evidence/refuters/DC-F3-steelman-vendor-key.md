<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F3 steelman of the runner-up: zero-touch for every machine (FDO or a provisioning key)

**Argued for it, as instructed.** "Plug in → it appears" (the north star) is literally zero-touch. FDO's late binding lets a machine be built without knowing its owner [C-FB2-003]; the lab showed an approved device finishing with **no** keyboard in 18 s [C-LAB-fb2-fdo-enroll-004]; Matter shows consumers accept scan-and-go with device attestation [C-FB2-004]; a provisioning key per fleet is how balena reaches its scale.

**Why it does not replace the ticket path.** BYO hardware (P-7) has no factory credential, no voucher and often no TPM; FDO needs a manufacturer step OneMind only controls for its own hardware; a shared provisioning key is a standing secret (contrary to FABRIC F-R1). So zero-touch is the *front end* for OneMind-built boxes, and the ticket + approval stays the universal path.

**What would make it win:** OneMind hardware becoming most of the installed base, with IDevID in every unit.
