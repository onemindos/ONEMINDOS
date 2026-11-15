<!-- SPDX-License-Identifier: Apache-2.0 -->
# The local CI runner on the founder's Mac (CI-10)

**Ties to:** issue [#299](https://github.com/onemindos/ONEMINDOS/issues/299); builds on [`ci-capacity.md`](ci-capacity.md) (CI-09). Changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md). The Beelink is the offline signing machine and is **never** a runner.

## What it is, in plain language
A **runner** is a machine that executes CI jobs. GitHub Free lends the org 20 hosted runners at a time, so jobs queue. A **self-hosted runner** is one of our own: it takes jobs from the same queue, so every job it runs frees a GitHub slot, and it costs nothing. Ours is a small Debian 13 (arm64) virtual machine, made with **Lima** (a tool that runs Linux VMs on a Mac), on the founder's Apple Silicon Mac.

**Ephemeral** means one job per registration. The runner takes one job, the work folder is deleted, and a fresh runner registers for the next. Nothing one job leaves behind reaches the next.

## Why fork PRs never run on the Mac
The repo is public. Anyone can open a pull request from a fork, and a pull request runs code the author wrote. On a GitHub-hosted runner that code lands on a throwaway machine. On the Mac it would land on a machine you own. So each job that may use the Mac chooses its runner with one expression:

- the **LOCAL_RUNNER** repo variable is `on`, **and**
- the event is not a pull request, **or** the pull request comes from this repo (`head.repo.full_name == github.repository`), not a fork.

Anything else gets `ubuntu-24.04`. Four more guards: the VM mounts nothing from the Mac (`mounts: []`), so a job cannot read your home folder; no job that reads a secret or an environment may use it (a test fails the PR otherwise); the VM holds no tokens; and you can delete the VM at any time.

Which jobs: `lint` and `unit` in `ci`, `ci-sdk`, `ci-ui`, `ci-dashboard`, and the `validate` job of `ci-apps`. They are arm64-safe and use no secrets. Not moved: image builds, the QEMU battery, anything needing x86 or KVM; `ci-onemindd` (it builds and runs an amd64 binary); `ci-core` (waits for #264); everything that signs or releases.

## Founder steps (only an org admin can do these)
Nothing here puts a token in the repo, a PR or a chat. The runner gets its short-lived registration tokens from your own `gh` login, one per job.

1. **Create the runner group.** GitHub → onemindos org → Settings → Actions → Runner groups → New runner group. Name it exactly `onemind-local`. Repository access: *Selected repositories* → `ONEMINDOS` only. Leave *Allow public repositories* **on** (the repo is public, and without it the group will not serve it).
2. **Fork PR approval.** Repo → Settings → Actions → General → *Fork pull request workflows from outside collaborators* → **Require approval for all outside collaborators**.
3. **Let `gh` mint registration tokens.** In a terminal on the Mac:

```bash
brew install lima gh
```

```bash
gh auth refresh -h github.com -s admin:org
```

4. **Start it** from a checkout of this repo (the first run downloads the Debian image, about 5 minutes):

```bash
scripts/ci-runner/up --service --on
```

   `--service` installs the launchd agent (it keeps running and restarts after a reboot); `--on` sets the repo variable `LOCAL_RUNNER=on`. Prefer to watch it in the foreground first? Run `scripts/ci-runner/up` and `Ctrl-C` stops it.

   *If you would rather paste a one-off registration token* (GitHub → org Settings → Actions → Runners → New runner → copy the token from the `config.sh` line): export it only in that terminal, `RUNNER_REG_TOKEN=<paste> scripts/ci-runner/up`, which serves exactly **one** job and then falls back to `gh`. Tokens expire in an hour, which is why the `gh` route is the real one.

5. **Check it:**

```bash
scripts/ci-runner/status
```

You should see the VM `Running`, the service `loaded`, a runner named `onemind-local-…` online, and `LOCAL_RUNNER` `on`.

## Everyday use
| I want to | Run |
|---|---|
| see state and queue counts | `scripts/ci-runner/status` |
| stop taking jobs, keep the VM | set the variable `off`: `gh variable set LOCAL_RUNNER --body off --repo onemindos/ONEMINDOS`, and the jobs go to GitHub in the next run |
| stop everything and send jobs back to GitHub | `scripts/ci-runner/down --off` |
| start from a clean VM | `scripts/ci-runner/down --off --wipe`, then `up --service --on` |
| read what it is doing | `~/Library/Logs/onemind-ci-runner.log` |

## What if the Mac is off or asleep?
A job already pointed at `onemind-local` waits for a runner that is not there, up to GitHub's 24-hour limit, and a *queued* job does not move to GitHub by itself. Two defences:
- Before you close the lid for a long time, run `scripts/ci-runner/down --off`. New runs then pick GitHub-hosted runners; already queued ones: cancel and re-run.
- The loop only registers a runner while `LOCAL_RUNNER` is `on`. If the Mac is merely asleep for minutes, jobs wait and then run when it wakes.
The honest limit: the switch is manual. Making it automatic (a heartbeat that flips the variable) needs a token with write access to variables, which is your decision, not something this PR does.

## Limits and known risks
- **Not tested on real hardware by the author.** The kit is checked by tests and shellcheck only. The first `up` on your Mac is the real test; send me anything that fails.
- The VM keeps its disk between jobs (only the work folder is deleted) and the `runner` user has passwordless `sudo`, because the moved jobs run `sudo apt-get`. That is acceptable only because the VM holds nothing secret and only trusted events reach it. For a stronger reset, `down --wipe` and `up`.
- Results come from arm64 Linux, not the x86 hosted image. A job that passes there and fails on GitHub (or the reverse) is a real signal, not noise: report it.
- The runner version and image are pinned with checksums in `scripts/ci-runner/runner.pin` and `lima.yaml`; bump them in a PR.
