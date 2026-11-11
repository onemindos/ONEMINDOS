# DC-11 · Backup and restore coverage incl. single-node SQLite — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-11 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
Single-box datastore = online SQLite `.backup` + token inside **restic**; full restore onto a fresh VM verified [C-LAB-k3s-footprint-restore-011, C-W5-009]; etcd clusters use `etcd-snapshot`, restic-wrapped [C-W5-001]; hub/Pro/Omni move to embedded etcd if T-W5-03 passes.

## Strongest counter-argument
The backup engine fails the same maintainer test that removed Rugix (DC-06), and the single-box datastore it protects is the least-maintained path in k3s.

1. **restic is now essentially one active maintainer.** In the last 12 months 475 of 653 restic commits (about 80% of non-bot commits) are by one person; the founder made 10 [C-REF4-DC-longevity-017]. Backups must be restorable for the whole support period *and after it*; a stalled restic means OneMind owns a crypto-bearing repository format.
2. **SQLite/kine is the edge case of the edge product.** kine — the SQLite shim being backed up — is about 70% one SUSE engineer by human commits [C-REF4-DC-longevity-016], and its maintainer reproduced "database is locked" with failing compaction after ten minutes of load on a 1-server/2-agent SQLite cluster (fixed Dec 2024) [C-REF4-DC-longevity-018]. A `.backup` of a database whose compaction is failing captures a growing, unhealthy file; the lab restore used a quiet box.

## Why it does not flip
The flip condition was "no supported SQLite backup/restore and no in-place migration to etcd". The lab disproved the first half. restic's single-maintainer share is real, but unlike Rugix it has a large independent user base, a documented repository format and an independent reimplementation (rustic), plus the steelmanned Kopia as an alternative, so the exit is cheap. The kine bug was fixed upstream.

## Verdict: **weakened**
- Required change: apply the DC-06 rule evenly — record restic's concentration in the risk register with the exit (format spec + rustic/Kopia read test in CI).
- Required change: the verified-restore job should also assert kine compaction health (revision lag) before taking the `.backup`, and T-W5-03 should run under write load, not idle.

## What would flip this verdict
- **To upheld:** a second restic maintainer with sustained commits, or a CI job that restores a restic repository with an independent implementation.
- **To refuted:** restic going a year without a release while a format change is pending, or a SQLite `.backup` restore failing under load in T-W5-03.

## Sources opened (new)
- GitHub API, restic/restic commits since 2025-11-11 at c734245f [C-REF4-DC-longevity-017]
- https://github.com/k3s-io/k3s/issues/11269 [C-REF4-DC-longevity-018]
- GitHub API, k3s-io/kine commits since 2025-11-11 at f82bd251 [C-REF4-DC-longevity-016]
