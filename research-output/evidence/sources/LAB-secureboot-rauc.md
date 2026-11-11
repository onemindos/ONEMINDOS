# Sources: LAB-secureboot-rauc (spike X-2R: RAUC A/B under UEFI Secure Boot + TPM2)

All sources accessed 2026-11-11 (UTC). Code is cited at pinned commit SHAs; a commit permalink cannot change, so it is its own archive. Web pages are saved as text in [`LAB-secureboot-rauc/`](LAB-secureboot-rauc/) with hashes in [`LAB-secureboot-rauc/SHA256SUMS`](LAB-secureboot-rauc/SHA256SUMS). Wayback save requests are denied in this environment, so no new Wayback captures were made.

| # | Source | Type | Pinned at / archive | Supports |
|---|---|---|---|---|
| S1 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/src/bootloaders/efi.c#L378-L498 (`r_efi_set_state`, `r_efi_get_primary`, `r_efi_set_primary`, `r_efi_get_state`) and #L273-L376 (`efi_set_temp_primary`, `efi_modify_persistent_bootorder`) | PRIMARY (code) | commit 4fb7c79 (v1.15.2 tree, 2026-03-27) | C-LAB-secureboot-rauc-001 |
| S2 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/reference.rst#L155-L161 (`efi-use-bootnext`, default true) | PRIMARY (docs source) | commit 4fb7c79; rendered page saved as `rauc-reference-efi.txt` (https://rauc.readthedocs.io/en/v1.15.2/reference.html) | C-LAB-secureboot-rauc-001 |
| S3 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/integration.rst#L1226-L1300 (EFI integration: two EFI partitions + efibootmgr entries, slot groups) | PRIMARY (docs source) | commit 4fb7c79; `rauc-integration.txt` | C-LAB-secureboot-rauc-001 |
| S4 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/src/context.c#L69-L91 (booted slot from `rauc.slot=` on the kernel command line) | PRIMARY (code) | commit 4fb7c79 | C-LAB-secureboot-rauc-002 |
| S5 | https://github.com/tianocore/edk2/blob/fbe0805b2091393406952e84724188f8c1941837/MdeModulePkg/Universal/BdsDxe/BdsEntry.c#L1052-L1093 (BootNext deleted before control is transferred, then BootOrder is walked) | PRIMARY (code) | tag `edk2-stable202502` = commit fbe0805 (the edk2 release Debian's `ovmf 2025.02-8+deb13u1` is built from) | C-LAB-secureboot-rauc-003 |
| S6 | https://www.freedesktop.org/software/systemd/man/257/systemd-stub.html | PRIMARY (docs) | `systemd-stub.txt` | C-LAB-secureboot-rauc-004, -005 |
| S7 | https://www.freedesktop.org/software/systemd/man/257/systemd-cryptenroll.html | PRIMARY (docs) | `systemd-cryptenroll.txt` | C-LAB-secureboot-rauc-006, -007 |
| S8 | https://www.freedesktop.org/software/systemd/man/257/systemd-pcrphase.service.html | PRIMARY (docs) | `systemd-pcrphase.txt` | C-LAB-secureboot-rauc-008 |
| S9 | https://www.freedesktop.org/software/systemd/man/257/ukify.html and https://www.freedesktop.org/software/systemd/man/257/systemd-measure.html | PRIMARY (docs) | `ukify.txt`, `systemd-measure.txt` | C-LAB-secureboot-rauc-009 |
| S10 | Debian 13 archive metadata (`dpkg -l` in the lab VM, `dpkg-query` in the image) from http://deb.debian.org/debian trixie + trixie-security | PRIMARY-METADATA | `../lab/secureboot-rauc/logs/versions.txt`, `../lab/secureboot-rauc/image-packages.txt` | C-LAB-secureboot-rauc-010 |
| S11 | This lab: `research-output/evidence/lab/secureboot-rauc/` (scripts, SHA256SUMS, trimmed logs) | PRIMARY (own experiment) | files in this repo | C-LAB-secureboot-rauc-011 onward |
| S12 | https://uefi.org/specs/UEFI/2.10/03_Boot_Manager.html (UEFI 2.10 §3.1, BootNext semantics) | **UNVERIFIED (blocked)**: HTTP 403 to automated clients on 2026-11-11; not read. Not cited for any claim; S5 (edk2 code) is used instead | n/a | none |
