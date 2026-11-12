# Refuter (security lens): DC-16 host extension mechanism (C-W19-001..009)

**Refuter:** independent, security lens · **Date:** 2026-11-11 · **Read:** the conclusion, C-W19-001..009, the saved man page `evidence/sources/W19/systemd-sysext.txt`, and Lab W19-1 (`evidence/lab/w19-sysext/README.md`, `logs/run-1.log`, `logs/run-2-h4-reason.log`). No conclusion-level claim ID exists for this target, so the file is named after its lead source claim, C-W19-001.

## Target

The target states that sysext and confext merge read-only images over `/usr`, `/opt` and `/etc`, that `/var/lib/extensions` is the primary location, and that ID and SYSEXT_LEVEL matching gates a merge. Lab W19-1 shows a clean add and remove, and refusal at level 2.0.

## Strongest counter-argument

The facts are correct. The lab, however, tested **function**, not **integrity**. Its limits section says "no verity-signed images; no Secure Boot". On the security question, the evidence points the other way.

1. **Unsigned extensions are accepted by default.** The default `--image-policy` for sysexts is `root=verity+signed+encrypted+unprotected+absent:usr=...`. `unprotected` admits images with no verity and no signature. Only `/.extra/sysext/` in the initrd defaults to signed-only (C-REF-W19-security-004).
2. **Plain directories bypass image policy entirely.** Any directory in `/var/lib/extensions` is merged as a "directory-based extension image" (C-REF-W19-security-004; saved man page L65-L66). Verity cannot apply to a directory.
3. **The location is the writable data partition.** Together, points 1 to 3 let anyone who gains root once drop a directory into `/var/lib/extensions`. That puts persistent binaries, udev rules or (through confext) `/etc` drop-ins such as sshd or sudoers fragments over the read-only image on every boot. This defeats the main security property of RAUC A/B, which is that a slot switch or reboot returns the host to a known image. The lab itself injected an sshd `Environment=` through confext (C-W19-007).
4. **Signed-policy enforcement is new and has been buggy in practice.**
   - systemd PR #44234 was merged to `main` only on 2026-10-26. It closes two signature-policy bypasses: reuse of a shared verity device set up without a validated signature, and a direct partition mount when no root hash is known (C-REF-W19-security-006). Debian 13 ships 257.13 (C-W19-004). Whether 257 is exposed to these bypasses is **UNVERIFIED**, but the fix is not in that release line.
   - Kairos, an immutable OS that relies on signed sysexts, validated images on its UKI path but linked every `.raw` unchecked on its GRUB path. Its first fix then fell back to "enabling everything unvalidated" when `systemd-dissect` was missing from the initramfs (C-REF-W19-security-005).
5. **Merge is all-or-nothing.** Once signed-only is enforced, one bad image blocks **every** extension from merging (C-REF-W19-security-005). A single malicious or corrupt plugin image becomes a denial of service against all host extensions, including OneMind's own driver packs.

## New sources (failure, regressions)

| ID | Source | Opened |
|---|---|---|
| C-REF-W19-security-004 | systemd-sysext man page, default image policy, https://www.freedesktop.org/software/systemd/man/latest/systemd-sysext.html | yes |
| C-REF-W19-security-005 | kairos-io/kairos#4988, https://github.com/kairos-io/kairos/issues/4988 | yes |
| C-REF-W19-security-006 | systemd/systemd#44234, https://github.com/systemd/systemd/pull/44234 | yes |

## Verdict: **WEAKENED**

The mechanism and the lab facts are upheld. The implied claim that sysext is a *safe* host extension point for a read-only image is not demonstrated, and it is false under default settings. It holds only if the image enforces all of the following:

- a signed-only `ImagePolicy` for sysext and confext;
- no directory-based extensions (or a refusal to merge them);
- verity keys in the read-only `/usr` or the kernel keyring, never in `/etc` or the data partition;
- a systemd that carries the #44234 fixes (or a backport);
- per-image skip, not all-or-nothing, when one image fails.

## What would flip it

- **To upheld:** a T-W19-01 run on the real RAUC image showing four things:
  - An unsigned `.raw` is refused.
  - A plain directory in `/var/lib/extensions` is refused or ignored.
  - A tampered verity image is refused.
  - One refused image does not block the others.
- **To refuted:** a demonstration that Debian 13's systemd 257 cannot enforce signed-only for both sysext and confext without the post-257 fixes, and that OneMind cannot backport them. Host extensions would then have to ship only inside the signed slot, as Flatcar does with its OEM sysexts.
