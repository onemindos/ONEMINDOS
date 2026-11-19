<!-- SPDX-License-Identifier: Apache-2.0 -->
# Security policy

## Reporting a vulnerability

**Please do not open a public issue, pull request or discussion for a security problem.**

Report it privately through GitHub: [Report a vulnerability](https://github.com/onemindos/ONEMINDOS/security/advisories/new) (the repository's *Security* tab, then *Report a vulnerability*). Only the maintainers can see the report.

Please include:
- what is affected (component, file or route, and the commit or version),
- how to reproduce it, step by step,
- what an attacker gains (for example: read another person's files, run a command without approval, bypass the update signature check).

We aim to acknowledge a report within 7 days and to agree a disclosure date with you once we understand it. We credit reporters in the advisory unless you ask us not to.

## What is in scope

Everything in this repository: the OS image and update path (`os/`, RAUC bundles, TUF metadata), the gateway (`core/`), the node daemon and CLI (`cmd/`, `internal/`), the dashboard and clients, the install scripts (`deploy/`) and the Market app manifests (`apps/`).

Problems we especially want to hear about:
- anything that lets an app or an AI agent act **without the owner's approval** (the capability gateway is the core promise of OneMind OS),
- update or image signature bypasses, and rollback that does not happen when it should,
- secrets, tokens or personal data leaking into logs, the audit chain or this public repository.

Third-party apps packaged in `apps/` are in scope for how we package and isolate them; bugs in the upstream app itself belong with its own project.

## Supported versions

OneMind OS is **pre-alpha** and has no signed release yet. Fixes land on `main` only. This section will list supported releases from `v0.1.0-alpha` on.

## How we work

The threat model and the hardening backlog are public: [docs/security/THREAT-MODEL.md](docs/security/THREAT-MODEL.md) and [docs/security/HARDENING-BACKLOG.md](docs/security/HARDENING-BACKLOG.md). CI runs gitleaks and hygiene checks on every PR, and a nightly security suite.
