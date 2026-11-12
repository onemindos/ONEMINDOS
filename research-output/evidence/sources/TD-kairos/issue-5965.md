# kairos-io/kairos#5965: Trusted Boot docs say automatic fallback is not implemented, but systemd-bless-boot assessment is implemented and tested
state: open created: 2026-11-05T10:00:39Z closed: null

## What the docs say

`docs/upgrade/boot_assessment.md` (kairos-docs), section "Booting to fallback":

> "Trusted boot" installations: While a similar solution exists in systemd to automatically reboot to a fallback entry, it's not yet implemented in Kairos. You can monitor the tracking issue for updates. (links to #2864)

and, under "What counts as a successful boot": "Automatic rollback is a GRUB-only feature."

## What the code and tests show

- #2864 ("Implement systemd-boot boot assessment") is closed (2024-11-27). The last comment says everything was merged.
- `kairos-init/pkg/bundled/cloudconfigs/08_efi_assessment.yaml` enables `systemd-bless-boot` in UKI boot mode (remounts `/efi` read-write around it).
- `agent/pkg/action/bootentries.go` handles the `+N` assessment suffix on loader entries.
- `tests/uki_test.go`, "Uki boot assessment tests": a broken active entry ends up as `active+0-3.conf` and the node boots `passive.conf`. The `boot-assessment` test runs in the `master.yaml` matrix on `hadron-trusted`, under QEMU.
- `docs/examples/boot_assessment_trusted_boot.md` already describes this as working (3 retries, then passive, then recovery, then autorecovery).

So the two pages disagree, and the code and test side with the example page.

## Suggested change

Update `docs/upgrade/boot_assessment.md` so the Trusted Boot paragraph describes the systemd-boot mechanism and links the example page, and remove the link to #2864 as an open tracking issue. The GRUB sentinel text is about GRUB and can stay as it is.

Checked against kairos `master` (dc32ce45) and kairos-docs `main` (35c2125). I did not test this on real hardware.

