<!-- SPDX-License-Identifier: Apache-2.0 -->
# How the gate lands PRs in the leap run

The Opus gate (Claude) is the only one who merges. This page is the gate's checklist, plus each trap from 2026-11-18 (26 PRs merged in one day) and how it is handled now.

## The flow for one PR

1. A builder marks the PR ready and labels it `needs-review`.
2. The gate reviews it:
   - the diff against the issue's "Done when" items;
   - the definition of done in [AGENT-QUEUE.md](../AGENT-QUEUE.md) §4;
   - security-relevant code (auth, approvals, caches of security data, keys, TLS, the rescue console) also gets an **independent Opus review**;
   - the gate re-runs the PR's tests itself.
3. Result: `review:approved` plus an evidence comment, or `review:changes` with exact fixes.
4. When approved, the gate arms auto-merge (`gh pr merge N`). The PR enters the merge queue when its required checks are green.
5. The merge queue re-tests the PR combined with main and merges it.
6. After merging: the gate checks whether the issue's "Done when" items are all on main. Issues are closed only with evidence and the founder's OK; PRs say "Refs", never "Closes".

## Traps from 2026-11-18 and how each is handled

| Trap | What happened | Handling now |
|---|---|---|
| CI capacity | GitHub Free runs about 13 hosted jobs; up to 166 jobs waited. 9 of 13 runners were merge-gates that only poll. | CI-13 (#360) runs merge-gates and light jobs on the Mac. #359 makes draft gates pass at once. Drafts run only cheap checks. At most one ready PR per lane. |
| Generated SDK conflicts | Almost every PR touched sdk/ generated files, so each merge made the next PR conflict. | Day 1 fix: generate in CI instead of committing. Until then, conflicts are resolved by taking main's version and running `make -C sdk gen`. |
| Visual baseline snowball | Four dashboard PRs carried the same screenshot PNGs and broke each other on every merge. | Land dashboard PRs one at a time (the "visual lane" script). Day 1 fix: refresh baselines automatically. |
| Bot commits start no CI | ui-quality `update_baseline` commits with GITHUB_TOKEN, and GitHub starts no workflows for that. | After a baseline commit, push a real commit (merge main, or an empty commit). |
| Merge queue drops | `checks_timed_out` removed PRs whose checks waited for runners. | The founder may raise the queue's status check timeout. The gate requeues dropped PRs. |
| Flaky checks | Cloud boot timeouts, a 502 on a tool download, GitHub API outages, a Gradle plugin download. | The gate reads the log first. A flake gets a re-run of the failed jobs only; a real failure gets a fix. |
| Expired app scans | Installs refuse scans older than 7 days. The daily rescan could not open its PR (repo setting), so ntfy's scan expired and every e2e install failed. | Fixed: the founder enabled "Allow GitHub Actions to create and approve pull requests" on 2026-11-19. The rescan PR (#365) carries the fresh scans. |
| New rule on main breaks old PRs | #323 (route scopes at module level) made open PRs fail after a refresh. | A refresh runs the full core tests, not only the PR's own tests. |
| Lost scripts | A session restart wiped the scratch folder with the watcher scripts. | Long-running gate scripts live in ~/ONEMINDOS-worktrees/_ledger/scripts and run detached, with logs in _ledger/. GitHub auto-merge is preferred over watcher scripts. |

## Order of landing when several PRs are ready

1. Pipeline and CI fixes (they speed up everything else).
2. Lane 1 (M-LIVE) PRs.
3. One PR per Codex lane, round-robin, so no lane starves.
4. Dashboard PRs strictly one at a time (shared screenshots).
