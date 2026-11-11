# DC-18 — Refuter report: adding the chain of trust later without a layout change, technical lens

- **Conclusion under test (07 P0-4 and §2 verdict):** Secure Boot, TPM-sealed disk keys and a verified root can be added later **without repartitioning or a reflash**, if the x86 layout is fixed now: a 1 GiB ESP with systemd-boot and signed UKIs per slot, A/B slots with room for dm-verity hashes, and LUKS2 on the data partition from first boot. Then "Secure Boot later means signing the UKI files only", "verity can be turned on later by an ordinary image update", and "turning on TPM later is just adding a key slot". Rugix has a systemd-boot flow and an (unstable) TPM2-sealed LUKS2 driver. Umbrel's GRUB layout is not the one to copy. Pi 5 and Jetson secure boot are compatible with A/B but irreversible. Lab test X-2 enrolls `--tpm2-public-key … --tpm2-public-key-pcrs=11 --tpm2-pcrs=7`.
- **Flip condition:** retrofitting a verified boot chain needs a reflash on the proposal's layout.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W6-044 to 061).
- **Date:** 2026-11-10

## Verdict: **weakened** (no reflash needed, so the decision holds, but three steps are not "just" image updates, and X-2 as written will fail in the field)

I found nothing that forces repartitioning, so the layout advice stands and is worth adopting now. But the retrofit is less free than stated:

1. **The proposed TPM policy binds PCR 7 literally.** That breaks unattended unlock on every Secure Boot db/dbx/KEK change. Those changes are not rare in 2026: the Microsoft 2011→2023 CA rollover (C-W6-044, C-W6-045) and routine dbx revocations both rewrite PCR 7. systemd's own tracker shows a KEK addition breaking a signed-PCR-11 UKI setup, because `--tpm2-pcrs` silently adds a literal PCR 7 policy (N1). fwupd now flags dbx updates as affecting full-disk encryption because they move PCR 7 (N2). On a headless appliance that means a recovery-key prompt after a firmware or dbx update, which is effectively a service call.
2. **"Signing the UKI files only" leaves out key enrollment.** A fielded x86 box trusts Microsoft's db. A OneMind-signed UKI boots only if (a) OneMind's key is enrolled in db, which needs setup mode or user/BIOS interaction per device, or (b) the boot goes through Microsoft-signed shim and a MOK, which in Debian trixie is an opt-in path for systemd-boot, and MOK enrollment needs physical presence (C-W6-046). NVIDIA DKMS modules also need MOK signing under lockdown (C-W6-046). Neither is a reflash, but neither is an OTA-only step for devices already in customers' hands.
3. **Rugix has no dm-verity support.** The repo has a systemd-boot flow and LUKS2/TPM tests, but no file mentions verity or UKI (N3). Turning on verity later means OneMind's own initramfs/UKI command line carrying the root hash, plus Rugix finding the active slot through a device-mapper node. That second step already failed once for dm-crypt roots (#117, fixed 2026-07-22). It is plausible, but it is OneMind's integration work on a project whose recent commits nearly all come from one person (see REF-W3 ledger C-REF-W3-longevity-002).

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| Signed PCR policy survives updates; literal `--tpm2-pcrs` breaks | C-W6-047 | Holds, and it **contradicts X-2's own `--tpm2-pcrs=7`**. PCR 7 changes with db/dbx/KEK (N1, N2), not only with kernel updates. |
| Rugix `luks2-tpm2` driver exists, marked `#[unstable]` | C-W6-048 | Holds. Its own warning about binding PCRs 0–9 bricking devices covers PCR 7. |
| Rugix systemd-boot flow + 512 MB ESP schema | C-W6-049 | Holds (verified in `systemd_boot.rs`: LoaderEntryDefault/OneShot via `bootctl`). The flow picks **entries**. Signing and per-slot UKI generation are left to the image build. |
| Rugix 1.4.0 keeps authenticated Pi boot images unchanged | C-W6-050 | Holds. |
| Umbrel uses GRUB + 256 MB ESP, no Secure Boot | C-W6-051 | Holds. |
| Microsoft CA expiry 2026 | C-W6-044, 045 | Holds, and it is the trigger for point 1 above. |
| Pi 5 OTP / Jetson fuses irreversible; tryboot works with secure boot | C-W6-056 to 059 | Holds. No layout conflict found. |
| Jetson LUKS via OP-TEE; fTPM needs offline EK provisioning | C-W6-060, 061 | Holds. The Jetson fTPM path needs **factory** provisioning, so for Jetson "add TPM later" is a manufacturing decision, not a field update. The conclusion should say so. |

## Strongest counter-argument

The layout is retrofittable, but the trust chain is not retrofittable **without touching each device**. Enrolling keys (db or MOK) needs physical presence or setup mode. Jetson fTPM needs factory EK provisioning. A PCR 7 binding turns every Secure Boot database update into a recovery event. So for units already shipped, "add later" means a field visit or a customer-run procedure. That is not a reflash, but for a consumer appliance its cost is close to one. The honest version of DC-18 is: *the layout must be chosen now, and the key-enrollment path (OneMind db key enrolled at the factory, in setup mode) must also be chosen before the first box ships, even if enforcement is switched on later.*

## New sources (searched for failures and regressions)

- **N1. systemd issue #32946, "[UKI] Cant unlock luks device after adding new certs to EFI"** — https://github.com/systemd/systemd/issues/32946 (opened). Ubuntu 24.04, systemd 255.4, signed UKI, `--tpm2-public-key`. Adding a KEK cert broke unlock. Maintainer: cryptenroll "includes both signed policy for `--tpm2-public-key-pcrs` and PCR policy for `--tpm2-pcrs`", and the latter defaults to PCR 7. It was closed 2024-05-23 via PR #32993. [C-REF-DC-technical-008]
- **N2. fwupd issue #7939, "Mark UEFI dbx updates as FWUPD_DEVICE_FLAG_AFFECTS_FDE"** — https://github.com/fwupd/fwupd/issues/7939 (opened). A dbx update changed PCR 7 and triggered BitLocker recovery. Contributors cite the TCG spec: all Secure Boot variables are measured into PCR 7. Fixed by PR #8033 and closed 2025-02-07. [C-REF-DC-technical-009]
- **N3. rugix/rugix tree and issue #117** — https://github.com/rugix/rugix/issues/117 (opened via `gh`). rugix-ctrl could not find the active slot when root was a dm-crypt mapper. Closed 2026-07-22 by commit c0de80c. A tree listing of the default branch (2026-11-10) shows systemd-boot and LUKS2/TPM tests but nothing for dm-verity or UKI. [C-REF-DC-technical-010]

## What would flip the decision

- **Flip (a reflash is needed):** X-2, or an extended X-2, shows that Rugix cannot switch between two **signed UKIs** as systemd-boot entries on the 1 GiB ESP layout, or cannot boot a dm-verity root from a slot without a different partition table (for example, needing a separate hash partition per slot rather than an appended tree), on hardware that ships with the proposed layout.
- **Flip for the TPM design (not the layout):** an X-2 run that applies a db or dbx update (or enrolls a test KEK) between A→B updates and gets a recovery prompt. Fix: drop `--tpm2-pcrs=7`, bind only to the signed PCR 11 policy (optionally with `systemd-pcrlock`), and re-run.
- **Upheld cleanly if:** X-2 passes A→B, B→A, **and** a dbx update without a prompt, and a factory key-enrollment procedure for OneMind's db key is written down before the first x86 box ships.
