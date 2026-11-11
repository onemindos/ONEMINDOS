# Sources: LEDGER (claims-ledger audit, 2026-11-11)

The audit added no new claim IDs. It re-opened sources for existing rows and archived them. All accessed on 2026-11-11 unless a row says otherwise. Wayback "save" requests are denied in this environment, so each page was saved as text with a sha256. Existing Wayback captures are cited where the owning sources file already lists one.

## 1. Pages re-opened for fetch-summary claims (saved in `W3/`)

Before this audit, these claims rested on a fetch tool's summary. Each page has now been read in full. The `text sha256` values are listed in `W3/SHA256SUMS`.

| Claim | Source | Type | Saved copy | raw sha256 (as downloaded) | Result |
|---|---|---|---|---|---|
| C-W3-042 | https://umbrel.com/downloads | PRIMARY | `W3/umbrel-com-downloads.txt` (2 e-mail addresses masked) | 8b620e02296e2250e0b3908b3206b397458ac58b29ef49d44b22df5333bd4167 | confirmed; the page now also offers umbrelOS 2.1 Beta 1 |
| C-W3-049 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/RootFileSystem.html (last updated Jun 02, 2026) | PRIMARY | `W3/nvidia-jetson-r39.2-RootFileSystem.txt` | 15c229de73f2ba77b3d663400f99315c49dfd7fe3810373a4b0138628f1c956f | confirmed (L240-L293) |
| C-W3-050 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | PRIMARY | `W3/nvidia-jetson-r39.2-SoftwarePackagesAndTheUpdateMechanism.txt` | 78e39c105276e29600601841277ca6a111ff632835fed19e787b35ffa68bae8b | confirmed (L372, L901-L926); an older sentence on the page (L900) still says "35.5.0 to 36.4.x" |
| C-W3-051 | https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html (last updated Dec 16, 2024) | PRIMARY | `W3/nvidia-jetson-r36.4-SoftwarePackagesAndTheUpdateMechanism.txt` | 0c3534ca37b25242686a6f82ab4f959c62588a9022c9f64c0fb56220078ee70f | confirmed (L808, L822-L837) |
| C-W3-057 | `cip-project/cip-core/isar-cip-core@e957cf930cef8c7cf8a55817f624bcf10bd81789:doc/README.swupdate.md` (GitLab API raw file) | PRIMARY | `W3/isar-cip-core-e957cf93-README.swupdate.md` | ff73751b0f43fa5f8f192dd501aa3adb2f04ffdaec66e2cf640218ac94ff975d | confirmed, and now pinned to a SHA |
| C-W3-066 | `raspberrypi/documentation@21d772e7ee022e36a8f43c3ee75e20ca359fb832:documentation/asciidoc/computers/config_txt/{autoboot,conditional}.adoc` | PRIMARY | `W3/rpi-documentation-21d772e7-config_txt-autoboot.adoc`, `…-conditional.adoc` | same as text | confirmed. raspberrypi.com served a Cloudflare challenge to the archiver, which was not bypassed, so the published docs' source repo was read instead |
| C-W3-027 | https://www.home-assistant.io/installation/generic-x86-64 | PRIMARY | `W3/home-assistant-io-installation-generic-x86-64.txt` | f6018cb6622c4c95dd150a51bc8d5cb0da04baaf27943e88022d2dfe6ab16bb1 | confirmed (L47-L78). This seventh fetch-summary row was found during status normalisation |

## 2. GitHub pins resolved for code and licence claims

Each SHA was resolved with `gh api` in one of two ways: (a) the commit a release tag points to, when the claim names a version, or (b) the head of the default branch as of the row's `accessed_date` (`commits?sha=<branch>&until=<date>T23:59:59Z`). Each licence was then read at that SHA through `repos/{repo}/license?ref=<sha>`, or through the contents API where GitHub's detection says NOASSERTION. All 72 new SHA permalinks were re-fetched and resolve. The per-row SHAs are in each row's `commit_or_tag`. The rows are C-W2-049, C-W2-051, C-W3-062, C-W4-033, C-W4-060, C-W4-061, C-W4-066, C-W4-068, C-W4-075, C-W6-074, C-W7-018, C-W7-050…053, C-W7-059, C-W9-027, C-TD-olares-033, C-TD-olares-054, C-TD-flagged-034, C-TD-villageos-037…039, C-STEEL-jb-007 and C-STEEL-KRU-011.

Linux tags resolved to commits: v6.18 = `7d0a66e4bb9081d75c82ec4957c50034cb0ea449`, v6.17 = `e5f0a698b34ed76002dc5cff3804a61c80233a7a`, v6.12 = `adc218676eef25575469234709c2d87185ca223a`, v6.11 = `98f7e32f20d28ec452afb208f9cffc08448a2652`. These are used in C-STEEL-KRU-004…006 and C-W7-012, -020, -023 and -049.

## 3. Source copies moved in from the lab workspace

Text copies were made from `work/.lab/` (outside the public repo). Each folder has an `INDEX.md` that maps every file to its original URL, Wayback capture (where one exists), lab path, raw sha256 (which matches the prefixes quoted in the owning sources file) and text sha256, plus a `SHA256SUMS`. HTML was converted to text. Discourse forum JSON was reduced to post text and dates. E-mail addresses, private IP addresses, tailnet host names and forum user names were masked. Every file is under 1 MB, and gitleaks found nothing.

| Folder | Files | From |
|---|---|---|
| `W4/` | 23 | `.lab/w4-sources/` (01–23, with its URL/Wayback index) |
| `W5/` | 8 | `.lab/w5-restore/web-archive/` (src1–src8). Not `shared/`, which holds k3s state |
| `W6/` | 18 | `.lab/w6/*.txt`. `cjis61.txt` (1.18 MB) was skipped; `W6-archive/` holds its excerpt |
| `W18/` | 37 | `.lab/w18-mac-toolchain/sources/` |
| `TD-villageos/` | 3 | `.lab/villageos-web/` |
| `TD-truenas-scale/from-lab/` | 5 | `.lab/truenas-web/` (a subfolder, so the teardown's own `SHA256SUMS` is untouched) |
