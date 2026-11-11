# Sources: LAB-rauc (RAUC A/B lab spike)

All sources accessed 2026-11-10/11 (UTC). Code is cited at pinned commit SHAs, which serve as the archive: a permalink to a commit cannot change. The one non-code source (Debian archive metadata) was read from the Debian mirror by `apt-cache` inside the lab VM; the exact output is saved in `../lab/rauc/logs/versions.txt`.

| # | Source | Type | Pinned at / archive | Supports |
|---|---|---|---|---|
| S1 | https://github.com/rauc/rauc/releases (GitHub API `releases/latest`: tag v1.15.2, published 2026-03-27T10:47:01Z) | PRIMARY-METADATA | API response recorded in this file | C-LAB-rauc-001 |
| S2 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/install.c#L1466 and #L1513 | PRIMARY (code) | commit 2d17b27 (2026-11-10, `master`) | C-LAB-rauc-003 |
| S3 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/bootloaders/grub.c#L190-L213 and #L293-L314 | PRIMARY (code) | commit 2d17b27 | C-LAB-rauc-004, -005 |
| S4 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/contrib/grub.conf#L11-L41 | PRIMARY (code) | commit 2d17b27 | C-LAB-rauc-006; basis of the lab `grub.cfg` |
| S5 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/docs/integration.rst#L1207-L1226 and #L1475-L1491 | PRIMARY (docs source) | commit 2d17b27 | C-LAB-rauc-007, -008 |
| S6 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/docs/reference.rst#L359-L373 and docs/advanced.rst#L91-L132 | PRIMARY (docs source) | commit 2d17b27 | C-LAB-rauc-009 |
| S7 | https://github.com/home-assistant/operating-system/blob/ab7d0f1a0174760353780a21be2befecbc80a672/buildroot-external/board/pc/grub.cfg#L10-L61 | PRIMARY (code) | commit ab7d0f1 (2026-11-10) | C-LAB-rauc-010 |
| S8 | https://github.com/home-assistant/supervisor/blob/040f14cd8aa2902401d30aaeb0cb71215854c78c/supervisor/os/manager.py#L467-L478 | PRIMARY (code) | commit 040f14c | C-LAB-rauc-011 |
| S9 | Debian 13 archive metadata (`apt-cache show rauc rauc-service`, `dpkg-query` in the lab VM and image) from http://deb.debian.org/debian trixie + trixie-security | PRIMARY-METADATA | output saved in `../lab/rauc/logs/versions.txt` and `../lab/rauc/image-packages.txt` | C-LAB-rauc-002, -012 |
| S10 | This lab: `research-output/evidence/lab/rauc/` (scripts, SHA256SUMS, logs) | PRIMARY (own experiment) | files in this repo; artefact hashes in `../lab/rauc/SHA256SUMS` | C-LAB-rauc-013 … |
