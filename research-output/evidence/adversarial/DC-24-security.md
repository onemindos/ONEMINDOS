# DC-24 · FIPS 140-3 for the public-safety tier — security refuter

**Lens:** security · **Refuter:** REF3 (independent; did not read other adversarial files) · **Date:** 2026-11-11
**Target conclusion** (`07-security-compliance.md` §8.6, `qbank/W6.md` Q215): validated FIPS 140-3 modules (Go #5247, OpenSSL FIPS Provider 3.1.2 #4985) can run on a Debian base, and CJIS v6.1 accepts AES-256 (FIPS 197) as an alternative, so the public-safety tier does not force Ubuntu Pro, RHEL or SLE. Day 1: LUKS2 AES-XTS-256 and TLS AES-256-GCM; Go components rebuilt with `GOFIPS140=v1.0.0` when FIPS mode is sold.

## Strongest counter-argument

The conclusion proves that **modules exist**, not that **the OneMind stack can be FIPS-operated on Debian**. Three gaps:

1. **The Kubernetes layer has no FIPS story.** OneMind's runtime is k3s. A vendor that builds regulated edge products on Kubernetes states plainly: "K3s is not available as a FIPS-certified distribution", and designates only RKE2 [C-REF3-DC-security-006]. "Rebuild with `GOFIPS140`" is the project's own workaround, not something upstream k3s supports or tests. Until it does, the hardened tier really runs on RKE2, and RKE2's documented FIPS path is still BoringCrypto (C-W6-025, C-W6-027). Go says it plans to remove BoringCrypto and that it can't be used with the native module (C-W6-028).
2. **The day-1 "AES-256 instead of FIPS" route is weaker than stated.** A CJIS v6.1 guide words the alternative as "a FIPS-validated symmetric algorithm under FIPS 197 (AES)" [C-REF3-DC-security-008]. "Validated" points to a CAVP algorithm certificate for the implementation in use. Debian's kernel crypto (dm-crypt/LUKS2) and Debian's OpenSSL default provider have no CAVP certificate for the Debian build. An auditor can therefore reject "we use AES-256" just as they can reject an untested operating environment. If so, the day-1 answer is not a day-1 answer, and a Debian base gives you no certificate to point to for disk encryption at all.
3. **A frozen validated module is a moving compliance target.** In September 2025 NIST changed its Implementation Guidance (10.3.A). The already-validated Go v1.0.0 module had to be amended with "a lot of backporting and some re-testing", and shipped as a new zip in Go minor releases [C-REF3-DC-security-007]. Go also drops an older module once a newer one is certified (C-W6-028, from go.dev). A small team rebuilding k3s plus its own Go services against a pinned module has to track every one of these changes per release. That upkeep is what Ubuntu Pro FIPS or RHEL sell.

Security effect: if a buyer actually needs FIPS mode and OneMind has to bolt it on, the likely failure is a half-FIPS node. Some binaries use the validated module, while the kernel disk crypto, containerd and k3s use non-validated code. That fails an audit and also gives a false sense of assurance.

## What holds

- Validated 140-3 modules exist and can run on Debian (C-W6-028..031), and the ADR's "FIPS 140-2" wording is stale (C-W6-026).
- The flip condition is narrow: "no validated module can run on a Debian base **and** the tier stays in scope". Nothing found here shows that no module can run. It shows that the system-level claim isn't supported.

## Verdict: **weakened**

The narrow flip is not met, but two claims are overstated: that the tier "does not force" a vendor base, and that AES-256 is a "day-1 answer". Both rest on an unconfirmed reading of CJIS and on a k3s FIPS build that does not exist upstream. Practical reading: a FIPS-sold tier means **RKE2 on a vendor-FIPS base (Ubuntu Pro or RHEL)** unless k3s gains upstream FIPS support. Keep public safety out of the first 180 days, and don't market CJIS readiness on the AES-256 route until the primary SC-13 wording is checked.

## What would flip it

- **To upheld:** the primary CJIS v6.1 SC-13 text (C-W6-033) shows that the AES-256 path needs no CAVP or CMVP certificate; or k3s ships an upstream-supported FIPS build on the Go native module (for example, with k3s #13651 closed); or a CJIS auditor accepts a Debian-based, `GOFIPS140`-built node.
- **To refuted:** a named public-safety buyer requires CMVP-validated disk and TLS crypto on the exact OS image (only vendor kernels and OpenSSL builds have that), or SC-13 is confirmed to require a CAVP certificate for the AES implementation.

## Sources opened (new)
- C-REF3-DC-security-006 · https://version-4-2.legacy.docs.spectrocloud.com/vertex/fips
- C-REF3-DC-security-007 · https://buttondown.com/geomys-fips140/archive/go-and-fips-140-september-update/
- C-REF3-DC-security-008 · https://compyl.com/guides/cjis-compliance-guide/
- (re-opened, already cited by the owner) https://go.dev/doc/security/fips140
