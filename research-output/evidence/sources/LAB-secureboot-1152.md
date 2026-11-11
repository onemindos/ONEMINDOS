# Sources: LAB-secureboot-1152

Spike: `evidence/lab/secureboot-1152/`. Claims: `evidence/claims/LAB-secureboot-1152.csv`. Accessed 2026-11-11. Every code source was read from a shallow clone in `<lab-dir>/src/` at the pinned commit; load-bearing excerpts are saved in `LAB-secureboot-1152/` with sha256 in `LAB-secureboot-1152/SHA256SUMS`.

| # | Source | Type | Pin | Saved excerpt | Used for |
|---|---|---|---|---|---|
| S1 | RAUC `CHANGES` (1.15.2, 1.15.1, 1.15, 1.14): https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/CHANGES | PRIMARY | rauc/rauc@`4fb7c798` (tag v1.15.2, tag object `f1ceebd6`) | `rauc-1.15.2-CHANGES-excerpt.txt` | What changed between 1.13 and 1.15.2: BootCurrent detection (PR 1696), backend-before-`root=` (PR 1712), `prevent-late-fallback` (1.14), CVE-2026-34155 fix (1.15.2) |
| S2 | RAUC 1.15.2 `src/context.c#L69-L176` (`get_cmdline_bootname_explicit`, `get_bootname`), `src/bootloaders/efi.c#L500-L526` (`r_efi_get_current_bootname`), `src/bundle.c#L2262-L2292` (bundle-format check) | PRIMARY | rauc/rauc@`4fb7c798d6ae412344fb8f8d310d773046af3441` | `rauc-1.15.2-slot-detection-and-format.txt` | H3/H4 order of booted-slot detection; T8 error text |
| S3 | RAUC 1.13 `src/context.c#L61-L141` (`get_cmdline_bootname`) and `#L417-L423` | PRIMARY | rauc/rauc@`1183a396a2e10e92e428c396a510113edcd9037b` (tag v1.13) | `rauc-1.13-slot-detection.txt` | Baseline: 1.13 reads only the kernel command line (`rauc.slot=`, then `root=`) |
| S4 | RAUC 1.15.2 `src/mark.c#L235-L243`, `docs/reference.rst#L255-L261` (`prevent-late-fallback`) | PRIMARY | rauc/rauc@`4fb7c798` | `rauc-1.15.2-prevent-late-fallback.txt` | Recommendation SB-8 (candidate, not tested) |
| S5 | Prior spikes reused: `evidence/lab/secureboot-rauc/` (1.13 baseline, scripts, E1), `evidence/lab/rauc-1152/` (RAUC build method, Debian backport status [C-LAB-rauc-1152-004]) | Lab (this repo) | files in this branch | n/a | Baseline outcomes; build script |
| S6 | This spike's logs: `evidence/lab/secureboot-1152/logs/` | Lab | `SHA256SUMS` in the spike folder | n/a | All LAB claims |
