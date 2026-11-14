<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 01: what "onemindd" means, and why GitHub Free is enough for now

**For:** Zeus · **Date:** 2026-11-14
**Status:** founder-requested learning entry. It adds no decision.
**Feeds:** alpha readiness ([`docs/leap/ALPHA-CHECKLIST.md`](../../leap/ALPHA-CHECKLIST.md)), F-27 (signing secrets), F-5 (website hosting), and how work is planned for AI agents ([`docs/leap/LANES.md`](../../leap/LANES.md)).

---

## 1. Why `onemindd` has two d's
The name is `onemind` plus `d`. The **d stands for "daemon"**: a program that runs in the background all the time, with no window and no one typing into it. This is an old Unix naming habit:

| Name | What it is |
|---|---|
| `sshd` | the SSH daemon: waits for remote logins |
| `containerd` | the container daemon: starts and stops containers |
| `systemd` | the system daemon: starts everything else at boot |
| `onemindd` | the OneMind daemon: the agent always running on each box |

The repo has both halves:
- [`cmd/onemind/`](../../../cmd/onemind/) is the **CLI**: the `onemind` command a person types.
- [`cmd/onemindd/`](../../../cmd/onemindd/) is the **daemon**: it runs OS updates, node identity, backups and the other background jobs ([`cmd/onemindd/README.md`](../../../cmd/onemindd/README.md)).

## 2. GitHub runs the project; the box runs the OS
GitHub does not run the OS. It runs everything around it:

| Job | GitHub piece |
|---|---|
| Keep the code | the repo |
| Plan the work | Projects (board), Issues (one task each), Milestones (one per version) |
| Build the image and test it on every change | GitHub Actions (CI) |
| Ship versions | Releases (image files, checksums, notes) |
| Host the website and docs | GitHub Pages (the proposed default for F-5) |
| Hear from users later | Issues with templates, Discussions |

The OS itself runs on the boxes: Debian 13, k3s, NATS, the gateway and `onemindd`. Boxes check a signed update feed, which can live on GitHub Releases or Pages at first and move to a CDN (a fast download network) when downloads get heavy.

**A proven project works this way.** Home Assistant OS develops, builds and ships its images from GitHub: release 18.5 (2026-11-06) attaches disk images (`.img.xz`) and RAUC bundles (`.raucb`) to the GitHub release. Checked with `gh release view -R home-assistant/operating-system` on 2026-11-14. umbrelOS also develops on GitHub, but its release 2.0.1 has no files attached; its images are downloaded from its own website.

## 3. Why the Free plan is enough today
`gh api orgs/onemindos` showed the org on the **Free** plan (2026-11-14). The repo is **public**, and GitHub gives public repositories most paid features at no cost. The ones OneMind uses or should use:

- **GitHub Actions:** standard runners for public repos, which covers the image builds and the QEMU battery.
- **Security:** secret scanning with push protection, CodeQL code scanning, Dependabot alerts.
- **Protected environments with required reviewers:** the place to keep the F-27 signing secrets so a release only runs after Zeus approves it.
- **Projects, Milestones, Releases, Pages, Discussions.**

UNVERIFIED: current prices, minute limits and which features are free change over time; check github.com/pricing before relying on a specific limit.

**When to pay:**
- **Team plan:** when hired developers need private repositories with full branch protection and seat controls.
- **Larger runners:** if image builds become too slow on the free machines.
- Copilot is not needed; the project's agents are Claude.

## 4. A planning setup for one founder plus AI
1. Turn on a **GitHub Project** for the repo. Its board updates itself as PRs merge, which avoids a hand-edited status file going stale.
2. Make a **Milestone** per version, starting with `v0.1.0-alpha`, and put the alpha checklist items under it as issues.
3. Write **one issue per agent task**: what is in scope, the files it owns, the spec to read, and the test that proves it is done. The agent opens a PR that says "closes #N".
4. Use the **GitHub Mobile** app (iPhone and Android) for notifications, reviews, merges and re-running CI. Plan on the website; the mobile app's Projects view is more limited.

Agents need the `project` permission on the GitHub login to use Projects: `gh auth refresh -s read:project,project` (noted in [`docs/leap/HANDOFF.md`](../../leap/HANDOFF.md) §5).

**Linear** is a good tool, but it is a second system to keep in sync with GitHub. Reconsider it when a hired team finds the GitHub board slow; Linear can import from GitHub.

## 5. Words used
- **Daemon:** a background program that runs all the time.
- **CLI:** command-line interface, a program you type commands into.
- **CI:** continuous integration, the robot that builds and tests every change.
- **CDN:** content delivery network, servers around the world that make big downloads fast.
- **Runner:** the machine GitHub Actions uses to run a CI job.

## 6. Check yourself
1. Which of `onemind` and `onemindd` would you type a command into, and which keeps running after you log out?
2. Why does a public repo get more for free than a private one?
3. Where should the F-27 signing secrets live so a release cannot run without you?
