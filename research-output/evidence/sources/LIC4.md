# Sources · LIC4 (licence matrix revision 3, critic gap P3-6)

**Accessed:** 2026-11-11 (UTC) · **Owner:** LIC4 · **Claims:** [`../claims/LIC4.csv`](../claims/LIC4.csv) (C-LIC4-001…018) · **Archive:** [`LIC4/`](LIC4/) with `SHA256SUMS` (saved files) and `ORIGINAL-HASHES.txt` (before e-mail masking). E-mail addresses in saved texts are masked as `<email-masked>`, so five saved hashes differ from the originals.

## 1. Archived (load-bearing)

| # | Source | How obtained | Archive | Claims |
|---|---|---|---|---|
| 1 | https://www.postgresql.org/about/licence/ | HTML to text | [`LIC4/01-…`](LIC4/01-postgresql-licence-page.txt) | C-LIC4-001 |
| 2 | https://www.postgresql.org/support/versioning/ (banner: "October 15, 2026: PostgreSQL 19 RC 1 Released!") | HTML to text | [`LIC4/02-…`](LIC4/02-postgresql-versioning-page.txt) | C-LIC4-002 |
| 3 | `postgres/postgres@724edf9bde9d…:COPYRIGHT` (REL_18_6) | raw at the pinned SHA | [`LIC4/03-…`](LIC4/03-postgresql-COPYRIGHT-REL_18_6.txt) | C-LIC4-001 |
| 4 | `jejb/sbsigntools@9cfca9fe7aa7…:COPYING` lines 1-35 (v0.9.5) | shallow clone at the tag | [`LIC4/04-…`](LIC4/04-sbsigntools-COPYING-head.txt) | C-LIC4-004 |
| 5 | `jejb/efitools@392836a46ce3…:COPYING` lines 1-16 (v1.9.2) | shallow clone at the tag | [`LIC4/05-…`](LIC4/05-efitools-COPYING-head.txt) | C-LIC4-005 |
| 6 | `xiang/erofs-utils@f36cadb5c563…:COPYING` (v1.9.4) | shallow clone at the tag | [`LIC4/06-…`](LIC4/06-erofs-utils-COPYING.txt) | C-LIC4-007 |
| 7 | `tytso/e2fsprogs@7ee1d505ef3b…:NOTICE` lines 1-22 (v1.47.4) | raw at the pinned SHA | [`LIC4/07-…`](LIC4/07-e2fsprogs-NOTICE-head.txt) | C-LIC4-013 |
| 8 | `stefanberger/libtpms@03ff2481e133…:LICENSE` (v0.10.2; TCG TPM 2 terms) | raw at the pinned SHA | [`LIC4/08-…`](LIC4/08-libtpms-LICENSE.txt) | C-LIC4-016 |
| 9 | `tpm2-software/tpm2-tools@bc25f7149372…:docs/LICENSE` (5.8) | raw at the pinned SHA | [`LIC4/09-…`](LIC4/09-tpm2-tools-docs-LICENSE.txt) | C-LIC4-006 |
| 10 | Codeberg `UnifiedPush/android-connector@04820c8cfe11…` README head + `connector/build.gradle` Tink line; `UnifiedPush/specifications@0c5301f5d20b…` README and spec list | shallow clones | [`LIC4/10-…`](LIC4/10-unifiedpush-connector-and-spec.txt) | C-LIC4-008 |
| 11 | `josch/mmdebstrap@a6fcdbc4dde9…:mmdebstrap` lines 1-22 (1.7.0; MIT header, no separate licence file) | shallow clone at the tag | [`LIC4/11-…`](LIC4/11-mmdebstrap-script-header.txt) | C-LIC4-013 |
| 12 | `nodejs/node@18b32a3b1552…:LICENSE` (v26.13.0) index of bundled components and the ICU Autoconf exception; the matrix row pins the LTS line v24.22.2 (`f7f273a9bb64…`), whose LICENSE was link-checked but not archived | raw at the pinned SHA | [`LIC4/12-…`](LIC4/12-nodejs-LICENSE-index.txt) | C-LIC4-012 |

## 2. Read at pinned SHAs (the permalink is the archive)

Every row added in revision 3 links `blob/<sha>/<file>` (GitHub), `tree/<file>?id=<sha>` (git.kernel.org), `-/blob/<sha>/<file>` (GitLab, Salsa) or `src/commit/<sha>/<file>` (Codeberg, the mmdebstrap Forgejo). **All 46 new permalinks returned HTTP 200 on 2026-11-11.** Tags were resolved to commits with `gh api repos/<o>/<r>/releases/latest` and `git ls-remote` (peeled `^{}` for annotated tags); licence paths came from the GitHub licence API at the tag, and SPDX from the file text (the detector said `NOASSERTION` or 404 for syft, grype, tpm2-tools, sigstore-go, Node.js, EDK II, swtpm, libtpms, labgrid, golang/vuln, uv, axe-core, efibootmgr, PostgreSQL, CPython and e2fsprogs).

| Group | Repositories and commits | Claims |
|---|---|---|
| SBOM/CVE | anchore/syft `a0c0d3890a9d`, anchore/grype `cd1f23eb50df` | C-LIC4-003 |
| TPM | tpm2-software/tpm2-tss `624f6ab3b4f2` | C-LIC4-006 |
| UnifiedPush | codeberg UnifiedPush/unifiedpush-rs `bc4963f20adc` (`libunifiedpush/Cargo.toml` license field); tink-crypto/tink-java `1bedd75ae716` (v1.23.0) | C-LIC4-008 |
| Sandboxes | google/gvisor `7a675ac66a1e`, kubernetes-sigs/agent-sandbox `0d94fc0bd96c`, kata-containers/kata-containers `03cf2ec06a5d` | C-LIC4-009 |
| Core and dashboard | sigstore/sigstore-go `be417d95ee77`; fastapi/fastapi `e10178c18d8d`; modelcontextprotocol/python-sdk `2118f14f8a19`; python/cpython `0d4bd512fc42` (v3.13.18); facebook/react `61aa00df822d`; vitejs/vite `b39e6e63dcbf`; microsoft/TypeScript `1e4744d68260` | C-LIC4-010…012 |
| Image build | salsa debian/gdisk `36fb9d366f94` (gdisk.cc L8); dosfstools `697f7692c951` (src/mkfs.fat.c header); plougher/squashfs-tools `708c59ae8085` (mksquashfs.c header); docker/buildx `3c4cbd35852f` | C-LIC4-013 |
| Boot runtime | rauc/rauc `4fb7c798d6ae` `src/bootloaders/efi.c#L6-L49` (runs `efibootmgr`); rhboot/efibootmgr `c3f9f0534e32`; rhboot/efivar `c47820c37ac2` | C-LIC4-014 |
| Time | gitlab chrony/chrony `8df4f1263e20` (COPYING, main.c header) | C-LIC4-015 |
| CI firmware and rigs | tianocore/edk2 `2970e5699ba6`; stefanberger/swtpm `32b5a0575991`; labgrid-project/labgrid `c5a5fc4ec7f4` | C-LIC4-016 |
| Lab tools | kernel.org rt-tests `62da2befac98` (SPDX header tally in src/); ColinIanKing/stress-ng `e1a93515da37`; fwupd/fwupd `27be80ac7885` | C-LIC4-017 |
| CI scanners and linters | google/osv-scanner `02f96a40691c`; golang/vuln `d1f380186385`; gitleaks/gitleaks `83d9cd684c87`; astral-sh/ruff `05cdc36a45a2`; eslint/eslint `12cbff4125db`; astral-sh/uv `316c827e058c`; dequelabs/axe-core `e797173108ea` | C-LIC4-018 |

## 3. Not read (gaps carried to license-matrix.md §9)

- The terms of the vulnerability database grype downloads at run time (and Trivy's, already in the matrix).
- The licences of FastAPI's own dependencies (Starlette, Pydantic, uvicorn) and of the dashboard's npm dependency tree: to be generated from lock files at B0 (LIC-R2), not by hand.
- LVFS firmware payload terms (vendor by vendor).
- The PostgreSQL container image OneMind will pin (official Docker image or another) is not chosen yet (BD-04 says "pinned at B0").

Code was cloned shallowly into `<lab-dir>/src/lic4/` and only read; nothing was built or run.
