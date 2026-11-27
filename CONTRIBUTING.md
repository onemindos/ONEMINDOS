<!-- SPDX-License-Identifier: Apache-2.0 -->
# Contributing to OneMind OS

Thank you for helping. This page is the short version for people; AI coding agents follow [AGENTS.md](AGENTS.md) and [docs/leap/AGENT-QUEUE.md](docs/leap/AGENT-QUEUE.md), which say the same things in more detail. Read [docs/leap/BUILDER-BRIEFING.md](docs/leap/BUILDER-BRIEFING.md) before an OS or gateway change.

## Before you start

- **Find or open an issue.** Every change belongs to one issue. Issues labelled `agent-ready` can be started now; `needs-founder`, `needs-hardware` and `parked` cannot.
- **The locked decisions are not up for change in a PR.** Debian 13 base, RAUC A/B with health-gated rollback, k3s, NATS, restic and the capability gateway are settled in [docs/DECISIONS.md](docs/DECISIONS.md). If you have evidence against one, open an issue with sources.
- **AI never actuates without human approval.** Do not add a path that lets an app or agent act on a device, file or account without the owner's approval.

## Making a change

1. Branch from a fresh `origin/release/next`: `feat/…`, `fix/…`, `docs/…` or `ci/…`. Open the PR against `release/next`; it lands on `main` through the merge queue. Use merge commits, and never rebase or force-push.
2. Keep it to one issue, under about 600 changed lines. Split bigger work into several PRs.
3. Add tests in the same PR. A new behaviour needs a test that fails without the change.
4. Make it reachable: a route, a dashboard screen or an `onemind` command. No mock or sample data on a screen a user can reach.
5. Add one change fragment, `changes/<branch-with-dashes>.md` ([format](changes/README.md)). Do not edit `CHANGELOG.md` or `docs/leap/STATUS.md`: a job fills them from the fragments.
6. Sign off every commit: `git commit -s` (the [DCO](https://developercertificate.org/) check fails without it).

## Checks to run before you push

Run the checks for the parts you touched (the table is in [AGENTS.md](AGENTS.md#engineering-where-code-lives-and-how-to-build-it)), then:

```sh
make lint
make test
python3 -I scripts/changes.py check
make hygiene
```

## Opening the pull request

Use the template (*Why / What / Tests / Not done*) and write `Refs #<issue>`, never `Closes` (issues are closed by hand once the work is truly done). CODEOWNERS requests the reviewer. A PR is merged only when every check is green and the review approves it.

## Treat every commit as public

Git history keeps everything and the code is published under Apache-2.0 (D-001), so assume everything you commit is public. The rules: never commit secrets, tokens, private IP addresses, host names, local file paths or personal data. `make hygiene` (gitleaks plus our own greps) catches most of it; you are still responsible for what you push.

## Licence

By contributing you agree that your work is licensed under [Apache-2.0](LICENSE). Do not paste code from projects whose licence is not Apache-compatible (for example umbrelOS, which is PolyForm Noncommercial, or Olares, which is AGPL); learning from their design is fine.

## Security problems

Report them to a maintainer directly, as described in [SECURITY.md](SECURITY.md), not in an issue thread.
