# Refuter (security lens): C-W19-049, ADR-001 effect (flip not met; reserve four items)

**Refuter:** independent, security lens · **Date:** 2026-11-11 · **Read:** the conclusion, C-W19-001..009, C-LAB-debian-rugix-012 and C-TD-umbrelos-053.

## Target

The ADR-001 D1/D3 flip condition is not met, and the decision is confirmed. The release-1 image must reserve four items:

1. SYSEXT_LEVEL in os-release.
2. `/var/lib/extensions` and `/var/lib/confexts` on the data partition, merged before k3s starts.
3. A OneMind module-signing key.
4. dm-verity signing of extensions with the release chain.

The flip conditions given are T-W19-01 re-merge, Secure Boot + RAUC verity verification, and an out-of-tree module that cannot be redistributed.

## Strongest counter-argument

The reservation list has the right items but leaves out what *enforces* them, and the flip conditions only cover functional failure. Reserving "dm-verity signing" while systemd's default policy still accepts `unprotected` images and plain directories (C-REF-W19-security-004) means the signatures are produced and never required.

Item 2 places the merge source on the one partition that RAUC does *not* reset. Rugix's model, by contrast, discards everything except declared persist paths (C-LAB-debian-rugix-012). The umbrelOS #2124 complaint shows how users react when non-image changes disappear (C-TD-umbrelos-053). That is the functional mirror of this concern: whatever survives on the data partition is exactly what an attacker wants to survive.

Enforcement has also proved fragile in comparable systems:

- systemd only merged the fixes for signature-policy bypasses on 2026-10-26 (C-REF-W19-security-006).
- Kairos shipped a boot path that merged unchecked sysexts (C-REF-W19-security-005).

Item 3 creates a persistent key with no revocation mechanism in the kernel (C-REF-W19-security-007).

None of this makes ADR-001 D1/D3 wrong. A read-only A/B image with extensions is still better than a mutable root. It does mean that "confirmed" is premature until enforcement is in the reservation list.

## New sources

| ID | Source | Opened |
|---|---|---|
| C-REF-W19-security-004 | systemd-sysext default image policy, https://www.freedesktop.org/software/systemd/man/latest/systemd-sysext.html | yes |
| C-REF-W19-security-005 | kairos-io/kairos#4988, https://github.com/kairos-io/kairos/issues/4988 | yes |
| C-REF-W19-security-006 | systemd/systemd#44234, https://github.com/systemd/systemd/pull/44234 | yes |
| C-REF-W19-security-007 | kernel module-signing docs, https://docs.kernel.org/admin-guide/module-signing.html | yes |

## Verdict: **WEAKENED**

D1/D3 stand. Add these reservations to release 1:

5. A signed-only `ImagePolicy` for sysext and confext shipped in `/usr` (drop-ins in `/usr/lib`, not `/etc`), with directory-based extensions refused.
6. Verity verification keys in the read-only image or the kernel keyring, never on the data partition.
7. A systemd carrying the #44234 fixes (or backports), with per-image skip on failure.
8. `module.sig_enforce=1` on all tiers, the module key in an HSM, and a written key-rotation path.

## What would flip it

Add one security flip condition alongside the three functional ones: a T-W19-01 variant in which an attacker with root on the data partition can make an unsigned extension or directory merge after reboot or a RAUC slot switch.

- If that cannot be prevented by the image's policy, ADR-001 D3 must change. Host extensions would ship only inside the signed slot (the Flatcar OEM model, C-W19-005), and third-party host extensions would be dropped.
- If it is prevented, upgrade this verdict to **upheld**.
