<!-- SPDX-License-Identifier: Apache-2.0 -->
# The local CI runner on the founder's Mac (CI-10, CI-13)

**Ties to:** issue [#299](https://github.com/onemindos/ONEMINDOS/issues/299); builds on [`ci-capacity.md`](ci-capacity.md) (CI-09). Changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md). The Beelink is the offline signing machine and is **never** a runner.

## What it is, in plain language
A **runner** is a machine that executes CI jobs. GitHub Free lends the org 20 hosted runners at a time, so jobs queue. A **self-hosted runner** is one of our own: it takes jobs from the same queue, so every job it runs frees a GitHub slot, and it costs nothing. Ours is a small Debian 13 (arm64) virtual machine, made with **Lima** (a tool that runs Linux VMs on a Mac), on the founder's Apple Silicon Mac.

It has **two pools** (CI-13):

- **Workers** (label `onemind-local`): build and test jobs. Each job gets a fresh VM cloned from a provisioned base VM, and the clone is deleted afterwards. Up to 3 run side by side (`INSTANCES`).
- **Gate** (label `onemind-gate`): small VMs for `merge-gate` only. Like the workers, every gate job gets a fresh clone (1 CPU, 1 GB) of a small, stopped gate base VM (`onemind-ci-gate`), and the clone is deleted afterwards. Up to `GATE_RUNNERS` gate jobs run side by side (default 4, at most 8), each in its own clone. `merge-gate` does no building: it polls the GitHub API for up to three hours, waiting for the other workflows of its commit. On GitHub-hosted runners those waits filled 8 of the 12 running slots (measured 2026-11-18); on the Mac a gate clone's CPU is idle almost all the time.

**Each pool has its own switch** (a repo variable): `LOCAL_RUNNER` sends build and test jobs to the workers, `LOCAL_GATE` sends `merge-gate` to the gate pool. They are separate on purpose. `merge-gate` is the one check every merge needs, so if it followed `LOCAL_RUNNER` while the gate pool had no runners (`GATE_RUNNERS=0`, or a missing gate VM), every merge would wait for a runner that never comes. The runner loop starts with `LOCAL_GATE=off` and sets it `on` only once a gate slot's runner has registered and is online at GitHub. It sets it `off` when the gate pool is 0 or its base VM is missing, after three gate failures in a row in one slot (of any kind: no registration token, a clone that does not start, a runner round that fails, a runner that does not come online within 5 minutes; the slot keeps trying and switches it back on once its runner is online again), and when the loop stops normally.

**Ephemeral** means one job per registration. The runner takes one job, the work folder is deleted, and a fresh runner registers for the next. Nothing one job leaves behind reaches the next.

## Why fork PRs never run on the Mac
The repo is public. Anyone can open a pull request from a fork, and a pull request runs code the author wrote. On a GitHub-hosted runner that code lands on a throwaway machine. On the Mac it would land on a machine you own. So each job that may use the Mac chooses its runner with one expression:

- the pool's switch is `on` (**LOCAL_RUNNER** for workers, **LOCAL_GATE** for `merge-gate`), **and**
- the event is not a pull request, **or** the pull request comes from this repo (`head.repo.full_name == github.repository`), not a fork.

Anything else gets `ubuntu-24.04`. A workflow that sends a job to the Mac may also never be started by `pull_request_target`, `workflow_run` or `issue_comment`: those events run with this repo's context on behalf of someone else's code or comment. Four more guards: the VM mounts nothing from the Mac (`mounts: []`), so a job cannot read your home folder; no job that reads a secret or an environment may use it (a test fails the PR otherwise); the VM holds no tokens; and you can delete the VM at any time.

Which jobs (a test, `test/unit/test_local_runner_policy.py`, keeps this list honest):

| Pool | Jobs |
|---|---|
| gate | `merge-gate` |
| workers | `ci`: `lint`, `unit`, `changes`, `dco`; `hygiene`; `ci-core`: `plan` and the 3 SQLite shards; `ci-sdk`; `ci-ui`; `ci-dashboard`; `ci-apps`: `validate`; `ci-mobile`: `typecheck + jest`; `e2e`: `e2e-unit`; `brand`: `sync`, `icons`; `ui-quality`: `build`; `site`: `build` |

They are arm64-safe, need no Docker and use no secrets. They stay on GitHub, and why:

- **Need x86_64 or KVM:** `image`, `battery`, `nightly`, `net-2vm`, `e2e` `golden-path`, `ci` `rauc-build` (it builds on both architectures on purpose), `ci-onemindd` (it runs the amd64 binary it built).
- **Need Docker:** the 4 PostgreSQL shards of `ci-core` (service containers) and its `image` job; all of `ci-deploy` (`docker compose`, privileged containers); `ci-apps` `gate` and `apps-gate-all` (k3d).
- **Need GitHub's preinstalled SDKs or other systems:** `ci-mobile` `android` (Android SDK, x86 Java) and `ios` (macOS); `ci-desktop` (macOS, Windows).
- **Results depend on the machine:** `ui-quality` browsers (its visual snapshots were taken on x86 Ubuntu; arm64 renders fonts differently), `perf-smoke` (its budgets were measured on GitHub's arm runner).
- **Write to the repo or read secrets:** `release`, `security-nightly`, `apps-rescan`, `changes-collect`, `dev-build`, `ui-quality` `commit-baseline`, `test-all` (it dispatches workflows).
- **Long and informational, so they would hold a Mac worker while PRs wait:** `go-fuzz`, `api-fuzz`.

## Rolling out CI-13 (PR #360) on the live runner
PR #360's own `merge-gate` cannot wait for the gate pool, because the gate pool is made by the code in that PR. There is no deadlock, because of the separate switch: until `LOCAL_GATE` is `on`, `merge-gate` runs on GitHub-hosted runners, so #360 can also merge first and the gate pool can come up afterwards. To run the new kit before the merge instead (it tests the gate pool on #360 itself), in the runner checkout `~/ONEMINDOS-worktrees/ci-runner-main`:

1. Fetch and check out the PR branch (detached):

```bash
cd ~/ONEMINDOS-worktrees/ci-runner-main && git fetch origin && git checkout --detach origin/ci/13-mac-capacity
```

2. Stop the old loop (its exit sets `LOCAL_RUNNER=off`; jobs use GitHub meanwhile):

```bash
scripts/ci-runner/down
```

3. Start both pools with this Mac's sizes (`up` provisions the worker base VM and creates and provisions the gate base VM; the first time takes a few minutes):

```bash
CPUS=3 MEMORY=6 INSTANCES=3 GATE_RUNNERS=4 scripts/ci-runner/up --service --on
```

4. Check that runners named `onemind-gate-…` are online and `LOCAL_GATE` is `on`:

```bash
scripts/ci-runner/status
```

5. Re-run #360's `merge-gate` (PR → Checks → merge-gate → Re-run), and merge when it is green.
6. Put the runner checkout back on main:

```bash
git fetch origin && git checkout --detach origin/main
```

The running agent keeps working: it runs `scripts/ci-runner/cycle` from this checkout, and the merged main has the same kit. If main's kit differs from the PR branch (a later fix), run `down` and step 3 again.

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

   `--service` installs the launchd agent (it keeps running and restarts after a reboot; while running it keeps `LOCAL_RUNNER=on`, and sets `LOCAL_GATE=on` once a gate runner is online; it sets both `off` when it stops normally); `--on` sets `LOCAL_RUNNER` right away (`LOCAL_GATE` is left to the loop). Prefer to watch it in the foreground first? Run `scripts/ci-runner/up` and `Ctrl-C` stops it.

   *If you would rather paste a one-off registration token* (GitHub → org Settings → Actions → Runners → New runner → copy the token from the `config.sh` line): export it only in that terminal, `RUNNER_REG_TOKEN=<paste> scripts/ci-runner/up`, which serves exactly **one** job and then falls back to `gh`. Tokens expire in an hour, which is why the `gh` route is the real one.

5. **Check it:**

```bash
scripts/ci-runner/status
```

You should see both base VMs `Stopped` (they are only cloned), worker and gate clones `Running` while they wait for or run a job, the service `loaded`, runners named `onemind-local-…` and `onemind-gate-…` online, and both `LOCAL_RUNNER` and `LOCAL_GATE` `on`.

## Sizing: this Mac serves the whole team
Codex's workers and the Claude builders run on the same Mac, so the VMs are capped. `up` reads:

| Setting | Meaning | Default |
|---|---|---|
| `INSTANCES` | parallel workers, 1 to 3 | 1 |
| `CPUS`, `MEMORY` (GiB) | size of each worker | half the cores, 8 |
| `GATE_RUNNERS` | parallel gate slots, each with its own clone, 0 to 8 (0 turns the gate pool off and sets `LOCAL_GATE=off`) | 4 |
| `GATE_CPUS`, `GATE_MEMORY` (GiB) | size of each gate clone | 1, 1 |

**For a 12-core, 32 GB Mac (the founder's):** 3 workers at 3 CPU and 6 GB, plus 4 gate slots at 1 CPU and 1 GB: **18 + 4 = 22 GB** when everything is busy, under the 24 GB budget. That leaves about 10 GB for macOS and the agents. The vCPUs add up to 13, more than 12 cores, but the gate clones' CPUs are almost always idle (they wait on the API), and cores are shared: a busy CI slows the agents but does not stop them.

```bash
CPUS=3 MEMORY=6 INSTANCES=3 GATE_RUNNERS=4 scripts/ci-runner/up --service --on
```

`CPUS`, `MEMORY`, `GATE_CPUS` and `GATE_MEMORY` size each clone when it is made, so a new size applies from the next job (they are also kept in the launchd agent). `up` warns when the VMs could use more than three quarters of the Mac's memory. `status` shows the Mac's cores and memory next to both pools.

## Everyday use
| I want to | Run |
|---|---|
| see state and queue counts | `scripts/ci-runner/status` |
| stop taking jobs, keep the VMs | set both variables `off` (commands below), and the jobs go to GitHub in the next run |
| send only `merge-gate` back to GitHub | `gh variable set LOCAL_GATE --body off --repo onemindos/ONEMINDOS` (or run `up` again with `GATE_RUNNERS=0`) |
| stop everything and send jobs back to GitHub | `scripts/ci-runner/down --off` |
| start from a clean VM | `scripts/ci-runner/down --off --wipe`, then `up --service --on` |
| read what it is doing | `~/Library/Logs/onemind-ci-runner.log` |

## Switch it off before the Mac sleeps
**Say it plainly: before you close the lid, shut the Mac down, or leave for a long time, run `scripts/ci-runner/down --off`.** It sets both switches off. From anywhere, without the Mac, run both:

```bash
gh variable set LOCAL_GATE --body off --repo onemindos/ONEMINDOS
```

```bash
gh variable set LOCAL_RUNNER --body off --repo onemindos/ONEMINDOS
```

**A closed lid with `LOCAL_GATE` on stalls every merge:** `merge-gate` is the one required check, and it waits for a gate runner that is asleep. A job already pointed at `onemind-local` or `onemind-gate` waits for a runner that is not there, up to GitHub's 24-hour limit, and a *queued* job does not move to GitHub by itself. With the variables off, new runs use GitHub-hosted runners; cancel and re-run anything already queued (for a stuck PR, re-run its `merge-gate`).
What the kit does for you: while the loop runs it keeps `LOCAL_RUNNER=on` (and `LOCAL_GATE=on` once a gate runner is online), and when the loop is stopped normally (Ctrl-C, `down`, logout, a `kill` without `-9`) it sets both `off`. The next start of the loop sets `LOCAL_GATE=off` first, so a stale `on` does not outlive a restart. The launchd agent runs under `caffeinate -i`, so an idle Mac does not sleep while the loop is up.

**What it cannot do: switch anything off when it gets no chance to run.** A `kill -9` (SIGKILL), a kernel panic, a power cut, a closed lid, or a reboot where nobody logs in (the launchd agent starts only at login) leaves **both variables `on`**, and every `merge-gate` then waits for a gate runner that is gone. Run the off-switch from any machine with `gh`:

```bash
gh variable set LOCAL_GATE --body off --repo onemindos/ONEMINDOS
```

```bash
gh variable set LOCAL_RUNNER --body off --repo onemindos/ONEMINDOS
```

Then cancel and re-run the stuck runs (for a stuck PR, re-run its `merge-gate`).

## Limits and known risks
- **Not tested on real hardware by the author.** The kit is checked by tests and shellcheck only. The first `up` on your Mac is the real test; send me anything that fails.
- **Every job gets a new VM.** `up` provisions one base VM and leaves it stopped. Before each job `cycle` clones it, starts the clone, runs the one job, and deletes the clone, so a changed binary or patched toolchain dies with the job (the `runner` user has passwordless `sudo`, because the moved jobs run `sudo apt-get`; this is why the reset matters). The cost is the clone-and-boot time before each job. `cycle` logs it: `grep 'fresh worker VM ready' ~/Library/Logs/onemind-ci-runner.log`. **The author has not measured it** (no Lima here); the first lines of that log are the measurement. If it is too slow, `FRESH=none` reuses one VM (fast, not clean) and `down --wipe` plus `up` rebuilds it from the pinned image; ask for a scheduled rebuild instead. Two instances means two clones running at once, so twice the memory.
- **The gate pool is cloned per job too.** An earlier draft ran several runner processes side by side in one long-lived gate VM. A job could then leave something behind for the next gate job, or read a sibling runner's registration token (from `/proc/<pid>/cmdline`, or by patching the shared runner binaries). Now each gate job gets its own fresh clone, deleted afterwards, and the runner user has no `sudo` in it. The cost is the clone-and-boot time before each gate job (`grep 'fresh gate VM ready' ~/Library/Logs/onemind-ci-runner.log`; not measured yet).
- **Registration tokens never appear on a command line.** The Mac hands the token to the VM on stdin, and `run-one.sh` gives it to `config.sh` in the `ACTIONS_RUNNER_INPUT_TOKEN` environment variable (the runner's own input for this), never as `--token`, for both pools.
- **Four gate slots means four merge-gate checks at once.** A fifth waits for a free slot. If PRs stack up, raise `GATE_RUNNERS` (up to 8; each busy slot is a 1 GB clone).
- Results come from arm64 Linux, not the x86 hosted image. A job that passes there and fails on GitHub (or the reverse) is a real signal, not noise: report it.
- The runner version and image are pinned with checksums in `scripts/ci-runner/runner.pin` and `lima.yaml`; bump them in a PR.
