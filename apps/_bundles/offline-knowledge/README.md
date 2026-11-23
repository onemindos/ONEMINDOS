<!-- SPDX-License-Identifier: Apache-2.0 -->
# Offline Knowledge

**Offline Wikipedia and other books, courses, maps of your region, and a local AI that answers from your library. Everything works with no internet once it has been downloaded.**

This bundle is OneMind's answer to the demand that Project N.O.M.A.D. proved (about 43,000 GitHub stars in 16 months for "offline knowledge plus local AI that just works"; [teardown](../../../research-output/02-competitors/project-nomad.md) §18, REC-NOMAD-01). OneMind adds what N.O.M.A.D. skips:
- every install is approved by the owner;
- every image is pinned and scanned (the app gate);
- backups (the small, valuable parts; the big content is downloaded again);
- A/B OS updates with rollback;
- Raspberry Pi as well as x86.

Pattern credit: Project N.O.M.A.D. (Crosstalk Solutions, Apache-2.0) for the idea of a content bundle with a library chat. No N.O.M.A.D. code or content is used, and its Creator Pack videos (a separate non-commercial licence) are never bundled.

> **Explain it like I'm the founder.** Think of it as a small public library in a box. **Kiwix** is the bookshelf: Wikipedia and other reference books, each stored as one big file. **Kolibri** is the classroom: courses with videos and exercises. **Offline Maps** is the map drawer: street maps of your area. **Library Chat** is the librarian. You ask a question, and it finds the right articles on the shelf, reads them and gives you a short answer with the page numbers. The librarian can only read. It cannot buy, throw away or change anything.

## What is in it

| App | What it does | Tier today | Notes |
|---|---|---|---|
| [Kiwix](../../kiwix/README.md) | The library: Wikipedia and other books (ZIM files), with a library manager that downloads, checks (SHA-256) and serves the books you list | **verified** (CI gate pass, smoke pass) | GPL-3.0, its own container |
| [Offline Maps](../../offline-maps/README.md) | Vector street maps of your region from one PMTiles file | **verified** (CI gate pass, smoke pass) | BSD-3-Clause + OneMind viewer; map data ODbL |
| [Kolibri](../../kolibri/README.md) | Courses, lessons, exercises and classes | **blocked** (upstream image has fixable CRITICAL CVEs) | optional in the bundle; installs once upstream ships a fixed image |
| [Ollama](../../ollama/README.md) | Runs the local AI model | community | already in the Market |
| [Library Chat](../../library-chat/README.md) | Ask the library; answers cite the articles | **verified** (CI gate pass, smoke pass) | OneMind's own, read-only; see "Known gap" below |

The CI app gate decided each tier (contract §9.4; ci-apps run 43591778335 on PR #124), and the gateway refuses to install an app whose scan did not pass (§10.3).

## Profiles

| Profile | Fits | Downloads | Books | Model |
|---|---|---|---|---|
| `starter` | any box with 4 GB RAM | about 1.2 GB | Wikipedia: climate change (text) | `qwen3:0.6b` |
| `greenhouse-offgrid` | Raspberry Pi 5 8 GB, or any x86 box, with a 128 GB+ SSD | about 21 GB | Wikipedia "mini" (every article's introduction), medicine, chemistry and climate change (full text), all English Wikibooks (how-to books, including gardening) and Wikivoyage | `qwen3:1.7b` |

Profiles are in [`bundle.json`](bundle.json). Every book in them is from Wikipedia, Wikibooks or Wikivoyage (CC BY-SA 4.0), so they are fine on a box that is sold or shared. Map data is cut for your own area, because a planet map is about 130 GB.

**Why these choices for a greenhouse or off-grid site:**
- The "mini" Wikipedia answers most "what is" questions in a fifth of the space of full text.
- Medicine (full text) covers first aid when help is far away.
- Wikibooks covers practical how-to, and chemistry covers nutrients and soil.
- `qwen3:1.7b` is the largest model that answers comfortably on a Pi 5 with 8 GB alongside the rest.

## Install

**One command** (the gateway still asks you to approve each app; nothing is approved for you):

```sh
export ONEMIND_TOKEN=…   # your owner token; never put it on the command line
python3 -I apps/_bundles/offline-knowledge/install.py --gateway https://<your box>:8443 --profile greenhouse-offgrid
```

Before requesting anything, it checks the gateway catalogue for missing apps, blocked tiers, failed or stale scans and incompatible app states. Optional unavailable apps are skipped with a reason; any required problem stops the bundle before installation begins. Already installed apps are configured without reinstalling. The gateway rechecks safety at approval. Redirects are refused so the owner token stays with the supplied gateway. It requests each app install, then a separate configuration action for the selected profile. Settings use the manifest field names and declared types; the gateway turns them into environment variables. Each action requires owner approval. If an optional app fails, it reports the failure and continues; any required failure stops the bundle. A timeout leaves the action pending on the gateway: check Approvals before retrying. It requests the apps one by one in a safe order. Library Chat needs Kiwix and Ollama installed first. It waits until you approve each request on the dashboard or phone. `--dry-run` shows what it would request, and `--skip kolibri` leaves an app out.

Then finish two things by hand (each app's README has the exact command):
1. **Pull the model:** `kubectl -n app-ollama exec deploy/ollama -- ollama pull qwen3:1.7b`.
2. **Cut a map of your area** in Offline Maps ("Add a map"): about 50 km around the site at zoom 15 is a few hundred MiB.

Kiwix downloads its books by itself, checking each one. Follow it with `kubectl -n app-kiwix logs deploy/kiwix -c library-sync -f`.

## Library Chat network access

The gateway opens only the Service ports declared by approved dependencies: Library Chat
can reach Kiwix and Ollama after they are installed. All other app-to-app traffic remains
behind the default-deny policy (`core/onemind_core/appstore/deps.py` and
`core/tests/test_dependency_paths.py`). Pull the selected model before going offline.

## Market installation status

This bundle currently installs through the command above. A one-click Market bundle
entry still needs coordinated gateway/dashboard work; the existing Market requests
individual app installs. The command does not auto-approve installs or settings changes.

## Licences in short

- **Software:** Kiwix GPL-3.0 (separate program), Kolibri MIT, go-pmtiles, MapLibre GL JS, PMTiles JS and the Protomaps style BSD-3-Clause, fonts SIL OFL 1.1, icons MIT, OneMind's code Apache-2.0.
- **Content:** Wikipedia, Wikibooks and Wikivoyage are CC BY-SA 4.0. Map data is from OpenStreetMap under ODbL, and the map always shows "© OpenStreetMap contributors". Kolibri channels are licensed per resource, and some are non-commercial.
- **Model:** Qwen3 is Apache-2.0.

All of these are rows in [`research-output/evidence/license-matrix.csv`](../../../research-output/evidence/license-matrix.csv) (addendum 2026-11-14 in `license-matrix.md`). **Rule for sold boxes:** only content whose licence allows commercial redistribution is ever preloaded. Everything else is the owner's own choice and download.

## Requirements served

U-2, A-1, A-7, M-1, F-13, N-6, AI-8 (REC-NOMAD-01). Related: REC-NOMAD-07 (backups skip re-downloadable content) and REC-NOMAD-04 (content kept for offline use).
