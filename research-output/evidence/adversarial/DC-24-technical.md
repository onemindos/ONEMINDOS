# DC-24: refuter report on FIPS 140-3 for the public-safety tier (technical lens)

- **Conclusion under test (07 §8.6 and P0-5, qbank W6 Q215/Q183, 01 §4.7):** validated FIPS 140-3 modules run on a Debian base: the Go Cryptographic Module #5247 and the OpenSSL FIPS Provider 3.1.2 #4985. CJIS v6.1 also accepts AES-256 under FIPS 197. So the public-safety tier does not force Ubuntu Pro, RHEL or SLE, and D2 holds. Weakness: Debian 13 is not a tested OE. Day-1 answer: LUKS2 AES-XTS-256 plus TLS AES-256-GCM. The hardened tier is x86 first.
- **Flip condition:** no validated module can run on a Debian base, and the public-safety tier stays in scope.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W6-024…034). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **upheld** on the base question; the **day-1 answer is weakened** by the network layer

**The base question is stronger than the conclusion says.** The conclusion lists "Debian is not a tested OE" as Debian's weakness. But the Go module's validation also lists generic **Vendor Affirmed** operating environments, including "Linux 3.10+ on x86-64 and ARMv7/8/9" [C-REF3-DC-technical-011]. So for Go components, Debian 13 on amd64 **and arm64** is inside the certificate's vendor-affirmed scope. The "x86 first" restriction is needed only for the OpenSSL provider. The flip condition is further from being met than recorded.

**Two gaps the conclusion misses. Neither is about the base OS.**

1. **The overlay network cannot meet either CJIS route.** OneMind's fleet and remote access use Tailscale/Headscale (WireGuard). Tailscale states its implementations "are not FIPS compliant", and that Curve25519, ChaCha20-Poly1305 and the WireGuard/Noise protocols "cannot be made compliant under current FIPS standards" [C-REF3-DC-technical-013]. The cipher is ChaCha20, not AES, so the FIPS 197 AES-256 route doesn't apply either. 07 §5 flagged this as UNVERIFIED; it is now verified. CJI crossing the mesh must ride an inner TLS session with AES-256-GCM from a FIPS module end to end, or the public-safety tier needs a different transport (for example IPsec/IKEv2 with a validated module). "LUKS2 + TLS" is the right day-1 answer only if **every** CJI path is TLS inside the tunnel. That includes NATS leaf traffic, TAK streams and the k3s flannel/WireGuard backend if it is enabled.
2. **The #5247 certificate has an entropy caveat.** Its certificate says "No assurance of the minimum strength of generated SSPs (e.g., keys)" [C-REF3-DC-technical-012]. The Go module treats kernel randomness as uncredited [C-REF3-DC-technical-011]. Keys that k3s and OneMind generate on the device (cluster CA, TLS keys) carry that caveat until a module with a validated entropy source is certified. This holds on every OS, so it does not favour RHEL or Ubuntu Pro for Go programs. A strict assessor may still write it up, and the answer is a module version with an ESV-certified entropy source, not a base change.

## Strongest counter-argument

"FIPS is possible on Debian" is true and beside the point. A public-safety buyer audits the **data path**, not the base image. The proposed stack's data path runs over WireGuard, which no FIPS module can cover, and on k3s, which can't run in Go's FIPS-only mode today (already on record). Its Go keys also carry a "no assurance of key strength" caveat. A vendor base wouldn't fix any of these three gaps, but the day-1 claim that CJIS is covered by LUKS2 and TLS does not hold until the transport is designed for it.

## New sources (searched for non-compliance, caveats and lifecycle limits)

- **N1.** Go blog, "The FIPS 140-3 Go Cryptographic Module" (2025-07-15). Opened. It covers the vendor-affirmed Linux OEs and the uncredited kernel entropy. [C-REF3-DC-technical-011]
- **N2.** NIST CMVP certificate #5247 page. Opened. It gives the caveat text and the 2026-07-07 update. [C-REF3-DC-technical-012]
- **N3.** Tailscale docs, "Tailscale encryption". Opened. It covers non-compliance and the primitives that can't be made compliant. [C-REF3-DC-technical-013]

## What would flip it

- **Towards a vendor base (the formal flip):** a named buyer or assessor rejecting vendor-affirmed OEs and requiring a module **lab-tested on the exact OS**, with the tier kept in the first 180 days.
- **Towards "day-1 answer refuted":** a data-flow review showing CJI on a path that is only WireGuard-encrypted (no inner AES-256 TLS), with no plan to replace the transport for that tier.
- **Towards fully upheld:** a public-safety profile that disables the Tailscale/WireGuard transport for CJI or wraps all CJI in module-backed TLS, plus a Go module version with an ESV-certified entropy source (the Go docs name ESV #E318 for v1.26.0, pending validation) in the shipped toolchain.
