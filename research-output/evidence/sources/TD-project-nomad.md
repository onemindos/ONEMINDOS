# Sources: TD-project-nomad (Project N.O.M.A.D. Tier B teardown)

**Accessed:** 2026-11-11 · **Claims:** `evidence/claims/TD-project-nomad.csv` (C-TD-project-nomad-001…046) · **Saved copies:** `evidence/sources/TD-project-nomad/` with `SHA256SUMS`. Wayback save requests are denied in this environment. Existing Wayback captures are listed below. The code is pinned to a git commit, which is a stronger archive than a page snapshot.

## Code (shallow clone in `<lab-dir>/src/project-nomad`, pinned)

| Repo | Commit | Tag / date | Type | Used for |
|---|---|---|---|---|
| github.com/Crosstalk-Solutions/project-nomad | `0dbbd21c2f470975e86131c497694c147ca8bc00` | v1.35.1 · 2026-10-05 | PRIMARY (code, Apache-2.0) | everything below |
| same repo, `main` | `c903da48c97bc02f5cdfeff2ebcde00a82dfec8e` | 2026-11-08 | PRIMARY (diff only) | confirms `main` differs from v1.35.1 only in `admin/docs/release-notes.md` and `collections/kiwix-categories.json` |

Files read at `0dbbd21`: `README.md`, `SECURITY.md`, `LICENSE`, `Dockerfile`, `.releaserc.json`, `.github/workflows/{build-primary-image,build-sidecar-updater,release}.yml`, `install/{install_nomad,update_nomad}.sh`, `install/management_compose.yaml`, `install/sidecar-updater/{Dockerfile,update-watcher.sh}`, `admin/start/{kernel,routes}.ts`, `admin/config/shield.ts`, `admin/app/models/service.ts`, `admin/database/seeders/service_seeder.ts`, `admin/app/services/{auto_update,system_update,docker_service,custom_app_guard,creator_pack,nomad_md,benchmark}_service*.ts` (relevant ranges), `collections/{creator-packs.json,creator-pack-license.md}`, `admin/docs/about.md`.

## GitHub API metadata (PRIMARY-METADATA)

| Endpoint | Used for | Claims |
|---|---|---|
| `repos/Crosstalk-Solutions/project-nomad` | licence, stars, forks, created, pushed | 003 |
| `repos/.../releases` and `git/refs/tags/v1.35.1` | release dates, tag SHA | 001 |
| `repos/.../contributors`, `search/commits` (12 months) | maintainer concentration | 004 |

## Issue tracker (PRIMARY; failure reports)

| Issue / PR | State | Claims |
|---|---|---|
| #949 app update leaves service down | closed 2026-06-24 (fixed v1.33.0) | 020 |
| #858 unchecked containerd growth | closed 2026-08-11 (v1.34.0) | 037 |
| #1468 sidecar image not rebuilt | open (2026-10-23) | 038 |
| #661 mysql:8.0 needs x86-64-v2 | closed 2026-04-06 | 039 |
| #400, #1007 UI system update fails | closed | 040 |
| PR #419 ARM64 images; #816 Pi support | closed, unmerged | 041 |
| #1238 admin-only access | closed not planned | 042 |
| #278 Dozzle shell on unauthenticated port | closed 2026-03-20 | 043 |
| #715 scheduled backups | closed to roadmap | 035 |

## Web pages (saved as text + sha256)

| URL | Saved file | sha256 | Wayback capture | Type | Claims |
|---|---|---|---|---|---|
| https://www.projectnomad.us/ | `projectnomad-home.txt` | `1bb4eb03…8836` (full in SHA256SUMS) | http://web.archive.org/web/20261105010723/https://www.projectnomad.us/ | PRIMARY (vendor site); competitor table SECONDARY | 046 |
| https://www.projectnomad.us/hardware | `projectnomad-hardware.txt` | `07af7f93…0076` | http://web.archive.org/web/20261104052914/https://www.projectnomad.us/hardware | PRIMARY | 013 |
| https://www.projectnomad.us/install | `projectnomad-install.txt` | `c3856777…eb92` | http://web.archive.org/web/20261103051833/https://www.projectnomad.us/install | PRIMARY | 012, 042 |
| https://www.projectnomad.us/support | `projectnomad-support.txt` | `80d7bdf5…ef02` | http://web.archive.org/web/20261013224855/https://www.projectnomad.us/support | PRIMARY | 031 |

## Earlier ledger rows reused

- C-TD-villageos-039 (NOMAD Apache-2.0, v1.35.1): consistent with C-TD-project-nomad-001/002.
- `research/competitors/landscape.md` §1.5: its summary is confirmed here at code level. It listed the business model as UNVERIFIED; that is now answered by C-TD-project-nomad-031.

## Hygiene notes

- The benchmark HMAC constant (`benchmark_service.ts#L47`) and the Creator Packs worker hostname are **not reproduced** in any output; they are cited by line range only.
- Release-bot email addresses in `release.yml` and the maintainer email in `SECURITY.md` are not reproduced.
