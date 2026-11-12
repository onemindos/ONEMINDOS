# DC-21: refuter report on the kernel route (technical lens, round 4)

- **Conclusion under test (decision-critical DC-21 Result, rev. 3; 01 §3.5):** K1 (board maintainer's kernel) at launch, with a CI kernel contract. **K2-hybrid** (OneMind-built kernel.org LTS with OneMind's module key built in) for the first release that enforces Secure Boot with out-of-tree modules, "because a db key cannot sign modules for a stock kernel" [C-DEC-008…010], unless T-W19-03 finds a console-free route.
- **Flip condition:** stock Debian kernels can't cover the declared support period for the target boards, but a CIP or OneMind-configured LTS can at solo-developer cost.
- **Lens:** technical. I read only the conclusion, 01 §3.5 and claims C-DEC-008, -009, -010. I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened** (K1 at launch upheld; the K2-hybrid trigger is likely not met, because a console-free route to trusting OneMind's module key on the **stock** Debian kernel exists in the source)

C-DEC-008…010 are correct: a key **only** in UEFI db lands in the platform keyring and cannot verify modules. But that is not the only console-free way to get a key into a trusted keyring. **shim's own built-in vendor certificate does it with no MOK enrolment:**

1. shim mirrors its compiled-in `vendor_cert`/`vendor_db` (`vendor_authorized`) into the runtime variable **MokListRT**, and when the user has not set `MokListTrusted`, it sets **MokListTrustedRT = 1 by default** [C-REF4-DC-technical-011].
2. Linux v6.12 loads X.509 entries from MokListRT into the **.machine** keyring when `CONFIG_INTEGRITY_MACHINE_KEYRING` is set and MokListTrustedRT is present [C-REF4-DC-technical-012]. Per C-DEC-010, .machine is trusted for module signatures.
3. Debian trixie's 6.12 kernel is built with `INTEGRITY_MACHINE_KEYRING=y`, `SECONDARY_TRUSTED_KEYRING=y` and without `INTEGRITY_CA_MACHINE_KEYRING`, so non-CA keys are accepted [C-REF4-DC-technical-013].

So: OneMind builds shim with its own module-signing certificate as `vendor_cert`, signs that shim with the OneMind db key it already enrols (X-2R), and chains the stock Debian kernel (re-signed with OneMind's key, or with Debian's CA in `vendor_db`). OneMind-signed `nvidia-open` and DC-16 driver-pack modules then load on the unmodified Debian kernel binary, with no console step and no Microsoft review, because OneMind owns db. That is the "console-free route" T-W19-03 is looking for, read from the source. It is **not yet run on hardware**.

A second point weakens K2's longevity case: kernel.org now projects **6.18 and 6.12 both to Dec 2028**, and a new LTS "usually starts with only a 2-year projected EOL" [C-REF4-DC-technical-010]. K2-hybrid on 6.18 buys no support-window advantage over Debian's 6.12. It adds a weekly OneMind kernel build and the private-key custody of a key that every module trusts.

## Strongest counter-argument

The rev. 3 plan moves a solo developer onto a self-built kernel (K2-hybrid) for the Secure Boot release, on a premise that holds only if the db-key route is the only console-free one. The shim vendor-certificate route keeps the stock, Debian-patched kernel with Debian's security cadence, which DC-20 found is the main CVE lever. It adds only a small, rarely changing shim build. K2-hybrid then has no remaining trigger and no lifecycle advantage, so for the Secure Boot release as well as launch, the decision should default to K1 + OneMind shim.

Residual risks of the shim route, stated fairly: OneMind must maintain and re-sign a shim fork (SBAT generations, shim CVEs); a leaked vendor key is trusted by every box until a dbx/SBAT revocation ships; and `efi_mokvar_entry_find` needs shim's MOKvar config table, so the shim version matters.

## New sources (searched for lifecycle cuts and Secure Boot failure modes; each opened or read from source at a pinned commit)

- **N1.** kernel.org, *Releases* (longterm projected EOLs). [C-REF4-DC-technical-010]
- **N2.** rhboot/shim `mok.c` at e794a714 (vendor cert mirrored to MokListRT; MokListTrustedRT inverse default). [C-REF4-DC-technical-011]
- **N3.** torvalds/linux v6.12 `keyring_handler.c` and `machine_keyring.c` (MokListRT → .machine). [C-REF4-DC-technical-012]
- **N4.** Debian kernel-team `debian/config/config`, branch debian/6.12/trixie at 7ce8fe4c. [C-REF4-DC-technical-013]

## What would flip this verdict

- **To upheld (K2-hybrid needed):** T-W19-03 boots a OneMind-built shim with a OneMind `vendor_cert` under OneMind-owned db on Secure-Boot hardware and the stock Debian kernel **refuses** a module signed by that cert (`/proc/keys` shows no .machine entry, or lockdown blocks it).
- **To refuted (K2-hybrid dropped):** the same test loads the module, and the shim re-sign/SBAT upkeep measures under the T-W18-4 one-hour weekly budget.

## Recommended change (for the owner, not applied)

Make the shim vendor-certificate route the **first arm** of T-W19-03 (one evening on an x86 box: build shim with `VENDOR_CERT_FILE`, sign with the db key, check `/proc/keys` for `.machine`, `modprobe` a OneMind-signed module under `lockdown=integrity`). Keep K2-hybrid as the fallback only if it fails.
