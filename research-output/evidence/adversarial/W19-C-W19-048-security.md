# Refuter (security lens): C-W19-048, kernel drivers as OneMind-signed per-kernel packs

**Refuter:** independent, security lens · **Date:** 2026-11-11 · **Read:** the conclusion, C-W19-005, C-W19-008, C-W19-009, C-STEEL-KRU-013, the saved Flatcar page L437-L441, and the Lab W19-1 log lines 48-49.

## Target

Kernel drivers are the one plugin type a third party cannot install at runtime. Driver plugins must therefore be per-kernel, OneMind-signed packs built by the release pipeline, with one sysext owning the module indexes per kernel.

## Strongest counter-argument

1. **"Cannot" is overstated.** The lab shows an *unsigned* out-of-tree module loading with `modprobe`. The kernel only tainted itself (log L48-L49). The kernel docs confirm that without `CONFIG_MODULE_SIG_FORCE`, unsigned modules load with a taint (C-REF-W19-security-007). Without Secure Boot lockdown or sig-force, a third party *can* install a driver at runtime with nothing more than the right `modules.dep`. The constraint is a policy OneMind must turn on, not a property of the platform. Many target boards (Pi-class) have no UEFI Secure Boot, so on those devices the constraint exists only if the image enables `module.sig_enforce=1`.
2. **The prescribed fix creates a high-value persistent key.** Per-kernel signing of third-party drivers needs a long-lived OneMind module key whose public half is built into every kernel. The kernel docs say the private key "must be either destroyed or moved to a secure location" because "malware could use the private key to sign modules" (C-REF-W19-security-007). Mainline kernels avoid this risk by generating a throwaway key per build. That option disappears once out-of-tree packs must be signed after the kernel is built.
3. **No revocation.** The same page describes no module revocation mechanism. A signed but vulnerable driver pack therefore stays loadable on every device running that kernel until the kernel is replaced. This is the Linux analogue of Windows "bring your own vulnerable driver". **UNVERIFIED:** I found no documented Linux BYOVD campaign. The search for one returned only lockdown documentation.
4. **OneMind becomes the signer of third-party kernel code.** The release pipeline's signature becomes the only gate on ring-0 code from outside parties. That raises the bar for review and build provenance well above that of E1 apps.

None of this argues for *letting* third parties load drivers. It strengthens the conclusion's prescription while correcting its framing.

## New sources

| ID | Source | Opened |
|---|---|---|
| C-REF-W19-security-007 | Linux kernel module-signing docs, https://docs.kernel.org/admin-guide/module-signing.html | yes |
| C-REF-W19-security-006 | systemd#44234 (verity signature bypasses fixed 2026-10-26): driver packs delivered as sysexts inherit these weaknesses, https://github.com/systemd/systemd/pull/44234 | yes |
| C-REF-W19-security-005 | Kairos#4988 (unchecked sysexts on one boot path), https://github.com/kairos-io/kairos/issues/4988 | yes |

## Verdict: **UPHELD (prescription), with a wording correction**

From a security standpoint, OneMind-built, per-kernel, signed driver packs is the right rule. Change "cannot install" to "**must not be allowed to install**". The image must enforce this with `module.sig_enforce=1` (or lockdown) on *every* tier, including boards without Secure Boot. Add three items:

- **Module key custody:** an HSM or an offline key, with signing done only in CI with provenance.
- **Revocation path:** per-pack revocation through E9 (refusal to merge the pack sysext). For key compromise, a key rotation through a kernel update.
- **Review standard:** a written review bar for third-party driver source before OneMind signs it.

## What would flip it

- **To weakened:** OneMind decides not to enforce sig-force on non-Secure-Boot tiers. The "constraint" then exists only on paper.
- **To refuted:** a required day-one device class needs a vendor binary module that OneMind cannot rebuild and sign. Third-party driver install at runtime would then be the only option.
