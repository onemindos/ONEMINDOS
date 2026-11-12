# Sources · FIX5 (critic pass-5 gap P5-1)

**Agent:** FIX5 · **Accessed:** 2026-11-11 · **Claims:** [`../claims/FIX5.csv`](../claims/FIX5.csv) (C-FIX5-001…004)

**Access note.** As FIX4 recorded, `ubuntu.com`, `canonical.com`, `archive.ubuntu.com` and `security.ubuntu.com` do not resolve from this session, on the host or in the lab VM. Every other name tried does (`logs/env-probe.log`). The U-SB spike needs the Ubuntu 26.04 archive, so it was recorded **BLOCKED** under its pre-registered rule. No alternative resolver, hosts entry or third-party mirror was used for the build. One diagnostic read of the 26.04 `Release` file was made by IP before the pattern was recognised; it is disclosed in the spike's §R.2 and not cited.

No web page is load-bearing for this fix, so nothing was archived under `sources/FIX5/`. All sources are this repo's own files.

| # | Source | Type | Claims |
|---|---|---|---|
| 1 | `evidence/lab/ubuntu-secureboot/logs/env-probe.log` (DNS probe on the host and in the Debian 13 Lima VM; host paths masked) | PRIMARY (own lab) | C-FIX5-001 |
| 2 | `evidence/lab/ubuntu-secureboot/README.md` + `PREREGISTRATION.sha256` + `../PREREGISTRATION.md` row | PRIMARY (own lab) | C-FIX5-002 |
| 3 | `evidence/lab/ubuntu-secureboot/scripts/` compared with `evidence/lab/secureboot-1152/scripts/` (`cmp`, `diff`) | PRIMARY (own lab) | C-FIX5-003 |
| 4 | `evidence/sources/FIX4.md`, "Access note" | PRIMARY (this repo) | C-FIX5-004 |
