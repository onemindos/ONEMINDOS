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

   `--service` installs the launchd agent (it keeps running and restarts after a reboot; it also sets `LOCAL_RUNNER=on` while running and `off` when it stops); `--on` sets the repo variable `LOCAL_RUNNER=on`. Prefer to watch it in the foreground first? Run `scripts/ci-runner/up` and `Ctrl-C` stops it.

   *If you would rather paste a one-off registration token* (GitHub → org Settings → Actions → Runners → New runner → copy the token from the `config.sh` line): export it only in that terminal, `RUNNER_REG_TOKEN=<paste> scripts/ci-runner/up`, which serves exactly **one** job and then falls back to `gh`. Tokens expire in an hour, which is why the `gh` route is the real one.

5. **Check it:**

```bash
scripts/ci-runner/status
```

You should see the VM `Running`, the service `loaded`, a runner named `onemind-local-…` online, and `LOCAL_RUNNER` `on`.

## Sizing: this Mac serves the whole team
Codex's workers and the Claude builders run on the same Mac, so the VM is capped. `up` reads `CPUS` (default: half the Mac's cores), `MEMORY` in GiB (default 8) and `INSTANCES` (parallel runners, 1 or 2, default 1). Example: `CPUS=6 MEMORY=12 INSTANCES=2 scripts/ci-runner/up --service --on`. CPUS and MEMORY apply when the VM is created; to change them, run `down --wipe` and `up` again. `status` shows the Mac's cores and memory next to the runners.

## Everyday use
| I want to | Run |
|---|---|
| see state and queue counts | `scripts/ci-runner/status` |
| stop taking jobs, keep the VM | set the variable `off`: `gh variable set LOCAL_RUNNER --body off --repo onemindos/ONEMINDOS`, and the jobs go to GitHub in the next run |
| stop everything and send jobs back to GitHub | `scripts/ci-runner/down --off` |
| start from a clean VM | `scripts/ci-runner/down --off --wipe`, then `up --service --on` |
| read what it is doing | `~/Library/Logs/onemind-ci-runner.log` |

## Switch it off before the Mac sleeps
**Say it plainly: before you close the lid, shut the Mac down, or leave for a long time, run `scripts/ci-runner/down --off`** (or, from anywhere: `gh variable set LOCAL_RUNNER --body off --repo onemindos/ONEMINDOS`).
A job already pointed at `onemind-local` waits for a runner that is not there, up to GitHub's 24-hour limit, and a *queued* job does not move to GitHub by itself. With the variable off, new runs use GitHub-hosted runners; cancel and re-run anything already queued.
What the kit does for you: while the loop runs it keeps `LOCAL_RUNNER=on`, and when the loop stops (Ctrl-C, `down`, logout, a crash) it sets `LOCAL_RUNNER=off`. The launchd agent runs under `caffeinate -i`, so an idle Mac does not sleep while the loop is up. What it cannot do: notice a closed lid or a power cut, because the Mac stops before any script can react. That case is on you, hence the rule above.

## Limits and known risks
- **Not tested on real hardware by the author.** The kit is checked by tests and shellcheck only. The first `up` on your Mac is the real test; send me anything that fails.
- **Every job gets a new VM.** `up` provisions one base VM and leaves it stopped. Before each job `cycle` clones it, starts the clone, runs the one job, and deletes the clone, so a changed binary or patched toolchain dies with the job (the `runner` user has passwordless `sudo`, because the moved jobs run `sudo apt-get`; this is why the reset matters). The cost is the clone-and-boot time before each job. `cycle` logs it: `grep 'fresh VM ready' ~/Library/Logs/onemind-ci-runner.log`. **The author has not measured it** (no Lima here); the first lines of that log are the measurement. If it is too slow, `FRESH=none` reuses one VM (fast, not clean) and `down --wipe` plus `up` rebuilds it from the pinned image; ask for a scheduled rebuild instead. Two instances means two clones running at once, so twice the memory.
- Results come from arm64 Linux, not the x86 hosted image. A job that passes there and fails on GitHub (or the reverse) is a real signal, not noise: report it.
- The runner version and image are pinned with checksums in `scripts/ci-runner/runner.pin` and `lima.yaml`; bump them in a PR.
