# Sources: TD-villageos (Tier A teardown of VillageOS.ai)

All sources opened on 2026-11-10 (UTC evening; some HTTP dates read 2026-11-11 UTC). Claim IDs are in `../claims/TD-villageos.csv`.

## Archiving note

The automated Wayback "save" request was blocked in this environment (outbound upload refused by policy), so load-bearing web pages use the brief's fallback: **saved text plus sha256**. The saved copies sit outside the public repo, in the run's lab folder (`.lab/villageos-web/`), so this file records only their hashes. Code sources need no archive because every code citation is a permalink pinned to a commit SHA. **Action for the integrator:** submit the three web URLs below to the Wayback Machine from a browser and add the snapshot links here.

| # | Source | Type | Accessed | Archive / integrity | Claims |
|---|---|---|---|---|---|
| S1 | https://www.villageos.ai/ (HTML; HTTP `last-modified: Tue, 17 Feb 2026 22:51:31 GMT`) | PRIMARY | 2026-11-10 | No Wayback snapshot existed (availability API returned none). Saved HTML sha256 `15fd034d0f1f756c73d4f523a754a2a73dad03e338c42409162013c3084313cf`; extracted text sha256 `c8308258f0605f289a0c2d5a67a6ce0546e65c903316583de7463cf06f4d0d0f` | 001, 002, 003 |
| S2 | https://github.com/ReGen-Villages/VillageOS-API at `0082f5bb6763aca379cb24588b8d7153558a08d9` (shallow clone, blob-filtered) | PRIMARY | 2026-11-10 | Pinned SHA (content-addressed) | 006–025, 033–036 |
| S3 | GitHub REST API: `repos/ReGen-Villages/VillageOS-API`, `/releases`, `/tags`, `/branches`, `/issues?state=all`, `orgs/ReGen-Villages/repos`, `/commits/0082f5bb…` | PRIMARY-METADATA | 2026-11-10 | API responses are point-in-time; re-query by 2027-05-10 | 004, 005, 032 |
| S4 | PR #12 https://github.com/ReGen-Villages/VillageOS-API/pull/12 (merge `7733e3b0`) | PRIMARY | 2026-11-10 | Merge commit SHA | 027 |
| S5 | PR #121 https://github.com/ReGen-Villages/VillageOS-API/pull/121 (merge `622cb652`) | PRIMARY | 2026-11-10 | Merge commit SHA | 028 |
| S6 | PR #111 https://github.com/ReGen-Villages/VillageOS-API/pull/111 (merge `edb25d5c`) | PRIMARY | 2026-11-10 | Merge commit SHA | 029 |
| S7 | PR #140 https://github.com/ReGen-Villages/VillageOS-API/pull/140 (merge `23aa673b`) | PRIMARY | 2026-11-10 | Merge commit SHA | 030 |
| S8 | PR #28 https://github.com/ReGen-Villages/VillageOS-API/pull/28 (merge `21644f9d`) | PRIMARY | 2026-11-10 | Merge commit SHA | 031 |
| S9 | EDGE AI POD, "Village OS: AI For Sustainable Living", 2026-06-11, https://edgeaipod.buzzsprout.com/2363070/episodes/18240345-village-os-ai-for-sustainable-living (show notes plus auto transcript; quote at 33:53) | SECONDARY | 2026-11-10 | No Wayback snapshot. Saved HTML sha256 `df4bc18726f77ee7aa2fa3c762d6cdb867cebddc8598c19dbb6230ff7e81cc0f` | 026 |
| S10 | Singularity Hub, "Inside VillageOS: a SimCity-like tool…", 2024-12-29 | SECONDARY | carried from `research/competitors/villageos.md` (S2 there) | Wayback: http://web.archive.org/web/20260413083803/https://singularityhub.com/2024/12/29/inside-villageos-a-simcity-like-tool-for-regenerative-living-spaces/ | background only, no claim ID |
| S11 | https://github.com/farmOS/farmOS (API metadata: license, latest release) | PRIMARY-METADATA | 2026-11-10 | Release tag 3.5.9 | 037 |
| S12 | https://github.com/OpenEMS/openems README "License" section (via API) and latest release | PRIMARY | 2026-11-10 | Release tag 2026.11.0 | 038 |
| S13 | https://github.com/Crosstalk-Solutions/project-nomad (API metadata) | PRIMARY-METADATA | 2026-11-10 | Release tag v1.35.1 | 039 |
| S14 | https://www.home-assistant.io/docs/energy/ | PRIMARY | 2026-11-10 | Not archived (not load-bearing; vendor doc) | 040 |

## Carried forward (prior-verified, not re-opened in this pass)

These come from the phase-1 report `research/competitors/villageos.md` §11 and are used only as background, never as the sole support for a recommendation: Lifeboat bio of James Ehrlich (S3 there), ReGen Villages site title/meta (S7 there), Khorium.ai (S8), Earth Rover Program and earthrover.farm (S9–S11), nurturerobotics.com (S12), 2016 Almere press via search summaries (S5).

## Searches run

- GitHub org listing `ReGen-Villages` (one public repo).
- Repo-wide grep at the pinned SHA for `mqtt|modbus|opc|lora|sensor|telemetry|iot`, `backup|restore|rollback|upgrade|retention`, `health`, `manifest` (results in the teardown, §4 and §6).
- Wayback availability API for villageos.ai, the GitHub repo, the podcast page and the Singularity Hub article.
