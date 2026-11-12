<!-- SPDX-License-Identifier: Apache-2.0 -->
# Forum: GitHub Discussions now, Discourse on OneMind later

**Date:** 2026-11-12 · **Serves:** W-1, A-6, R-2 · **Decision owner:** the founder (nothing has been created on GitHub or anywhere else).
**Inputs:** [`RESEARCH.md`](RESEARCH.md) §1; [`research-output/14-…`](../research-output/14-family-education-community-website.md) §5.2 (REC-W13-09 recommended hosted Discourse Pro first, then self-host).

> **Explain it like I'm the founder.** A forum is where users help each other, so you don't answer the same question twenty times. Almost every competitor uses **Discourse**: Umbrel, Home Assistant, Start9, TrueNAS and YunoHost all run it (checked 2026-11-12). But a forum with ten members feels empty, and Discourse costs money or admin time. So: **turn on GitHub Discussions now** (free, zero admin, everyone who'd use OneMind today already has a GitHub account). **Move to Discourse when the community outgrows it, and run that Discourse on OneMind itself.** That second step is a good test: if OneMind can't host its own forum reliably, it isn't ready for anyone else's.

## Recommendation

| Phase | Forum | When | Why |
|---|---|---|---|
| **Now** | **GitHub Discussions** on `onemindos/ONEMINDOS` | Switch it on when the site goes live (currently off; read 2026-11-12 with the GitHub API) | Free; no server; same accounts as issues and PRs; threads can turn into issues; good search-engine indexing; Markdown like the docs |
| **Later** | **Discourse, self-hosted as a OneMind app** on a OneMind box | When one of the triggers below fires | The pattern every competitor converged on; the forum becomes a dogfooding target and a showcase app |

**Triggers to move:** (any one) more than ~50 new threads a month; a need for categories with their own moderators, trust levels or private groups (e.g. hardware beta testers); support volume that needs Discourse's "solved" plugin and templates (the support-bundle ID template from 14 §7); or non-developers who won't use GitHub.

**Skip the hosted Discourse step** that 14 §5.2 proposed ($100/month): Discussions covers the early phase at no cost, and the self-hosted step tests OneMind. If the self-hosted forum is not stable when a trigger fires, hosted Discourse remains the fallback.

## Comparison

| | GitHub Discussions | Discourse self-hosted on OneMind | Discourse hosted |
|---|---|---|---|
| Cost | $0 | hardware + time | from ~$100/month (14 §5.2) |
| Admin work | none | updates, backups, email delivery, spam | none |
| Accounts | GitHub only | email, SSO, GitHub login | same as self-hosted |
| Data ownership | GitHub's; export via API | ours; full export | ours; full export |
| Dogfooding | no | **yes**: backups, updates, approvals and monitoring on a real public service | no |
| Fit for non-developers | weak | strong | strong |
| Licence | proprietary service | GPL-2.0, run unmodified as a separate service (fine next to Apache-2.0 code: we don't link or ship it) | — |

## What self-hosting needs from OneMind first
Each item is on the roadmap anyway; the forum is the forcing function.
1. **Backups with verified restores** ([Backups](src/content/docs/docs/concepts/backups.md)): the forum's PostgreSQL and uploads.
2. **HTTPS on a public hostname** and a way to expose one app to the internet safely.
3. **Outbound email** (Discourse needs it for sign-up and notifications).
4. **Updates and monitoring**: Uptime Kuma (already a seed app) watching the forum; ntfy alerts.
5. A Discourse app in the catalog, passing the same CI gate as every other app.

## Migration path
Discussions → Discourse has no official one-click import. Plan: keep Discussions read-only with a pinned link to the new forum; import only the top threads by hand or with a small script over the GitHub GraphQL API. Do not delete Discussions: old links keep working.

## Founder decisions needed
- **F-1:** switch on GitHub Discussions when the site launches (yes/no), and the starting categories (suggested: Q&A, Ideas, Show and tell, Hardware reports, Announcements).
- **F-2:** switch on GitHub private vulnerability reporting (currently off), which the Community page's security section asks for.
