<!-- SPDX-License-Identifier: Apache-2.0 -->
# Security policy

## Reporting a vulnerability

This repository is private, so only members of the `onemindos` organisation can read it. Even so, **do not put the details of a vulnerability in an issue, pull request, commit message or CI log**: every member can read those, they stay in history, and the repository may be made public later.

Instead:
1. **Tell a maintainer directly**, in a private message. The maintainers are listed in [.github/CODEOWNERS](.github/CODEOWNERS).
2. If you need something to track, open an issue titled only `Security report` with **no details**. The maintainer adds the details once the fix is out.
3. If the problem is a leaked secret (a token, key or password in the code or history), say so first: the secret is rotated before anything else, because removing it from the code does not remove it from git history.

Please include:
- what is affected (component, file or route, and the commit or version),
- how to reproduce it, step by step,
- what an attacker gains (for example: read another person's files, run a command without approval, bypass the update signature check).

We aim to acknowledge a report within 7 days.

## What is in scope

Everything in this repository: the OS image and update path (`os/`, RAUC bundles, TUF metadata), the gateway (`core/`), the node daemon and CLI (`cmd/`, `internal/`), the dashboard and clients, the install scripts (`deploy/`) and the Market app manifests (`apps/`).

Problems we especially want to hear about:
- anything that lets an app or an AI agent act **without the owner's approval** (the capability gateway is the core promise of OneMind OS),
- update or image signature bypasses, and rollback that does not happen when it should,
- secrets, tokens or personal data leaking into logs, the audit chain or this repository.

Third-party apps packaged in `apps/` are in scope for how we package and isolate them; bugs in the upstream app itself belong with its own project.

## Supported versions

OneMind OS is **pre-alpha** and has no signed release yet. Fixes land on `main` only. This section will list supported releases from `v0.1.0-alpha` on.

## If the repository becomes public

Replace the reporting steps above with GitHub private vulnerability reporting (repository *Settings*, then *Code security*, then *Private vulnerability reporting*), which works only on public repositories.

## How we work

The threat model and the hardening backlog are in [docs/security/THREAT-MODEL.md](docs/security/THREAT-MODEL.md) and [docs/security/HARDENING-BACKLOG.md](docs/security/HARDENING-BACKLOG.md). CI runs gitleaks and hygiene checks on every PR, and a nightly security suite.
