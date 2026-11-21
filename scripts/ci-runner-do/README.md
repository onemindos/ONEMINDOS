<!-- SPDX-License-Identifier: Apache-2.0 -->
# DigitalOcean CI runners (CI-15), off by default

More CI power from DigitalOcean (DO) droplets, for trusted events only. Same pattern as the Mac pool
(`scripts/ci-runner`) and the x86 KVM pool (`scripts/ci-runner-kvm`): single-use runners, a fail-closed
fork guard on the machine, and a repo variable that switches the pool on and off.

**Nothing here has been run against a real DO account.** The scripts and the routing are unit-tested with a
stub `doctl` and `gh`; the founder runs `up`.

## What it is

- Label `onemind-do`, runner group `onemind-local`, switch variable `DO_RUNNER` (`on` or off/unset).
- Droplets run Ubuntu 24.04 with Docker. Each droplet has SLOTS job slots. A slot runs ONE job in a fresh
  container built from `Dockerfile` (Ubuntu 24.04, pinned x64 Actions runner, no Docker inside), deletes it, and starts the
  next. Nothing a job writes survives it.
- No `/dev/kvm` on DO droplets. Only jobs with no KVM and no Docker go here: the first set is `lint`, `unit`
  (ci.yml), `hygiene`, and the SQLite `test` shards (ci-core.yml). Image, battery, release and signing stay
  where they are.
- Routing when `DO_RUNNER=on` and the event is trusted (never a fork PR): `onemind-do`; otherwise exactly as
  before (the Mac pool if `LOCAL_RUNNER=on`, else `ubuntu-24.04`). Off is the default.

## Run it (founder)

```
doctl auth init                      # once; the token stays in doctl's own config, never in this kit
gh auth refresh -h github.com -s admin:org
export DO_SSH_KEY=<id or fingerprint from: doctl compute ssh-key list>
export DO_ADMIN_CIDR=<your public address>/32     # the only source allowed to reach port 22
scripts/ci-runner-do/up 2 c-16 nyc3  # prints the $ per hour, asks y/N, then provisions and runs the loop
```

`up` ends in `cycle`, which stays in the foreground (Ctrl-C stops it). Use `up ... --no-run` to provision only.
`status` shows the switch, droplets, $ per hour and runners. `down` destroys everything and turns the switch off.

## Cost guard

| Guard | Default | Where |
|---|---|---|
| Most droplets | `MAX_DROPLETS=4` (hard limit 8) | `up` |
| Most dollars per hour | `MAX_USD_HOUR=2.00`, price from `doctl compute size list` | `up` |
| Confirmation | y/N with the hourly and daily cost | `up` (`ASSUME_YES=1` skips) |
| Idle | destroy after `IDLE_HOURS=2` with no busy runner (GitHub's busy flag) | `cycle` |
| Lifetime | destroy after `MAX_HOURS=12` | `cycle` |
| Exit | loop stops or is interrupted: switch off and destroy (`KEEP=1` keeps droplets) | `cycle` |
| Failed `up` | destroys what it created | `up` |

Droplets bill while they exist. If the operator's machine dies (power cut, `kill -9`) the loop cannot destroy
them: run `status`, then `down`. A cloud-side dead-man timer is not built (see "Left").

## Security

- **No token on a droplet.** `cycle` runs on the operator's machine, mints a JIT config (one runner, fixed
  labels, fixed group, works once) with the operator's `gh` login, and pipes it over SSH on stdin into the
  container. It is never in argv, an environment variable list, or a file.
- **Fork PRs.** The workflow expression never selects the pool for a fork PR, and `job-started.sh` runs inside
  every container and refuses the job unless the event is on the allow-list and, for a PR, the head repository
  is this repository. It is the same policy as the KVM kit's hook.
- **Network.** The cloud firewall allows port 22 only from `DO_ADMIN_CIDR` (never the whole internet). Job
  containers reach the public internet only: the metadata service (169.254.0.0/16), all private ranges (the
  VPC, other droplets), CGNAT, and the droplet itself are dropped, and `start-job.sh` refuses to start a job if
  those rules are missing.
- **Only ours.** Everything is found by tag `onemind-ci-do` and name `onemind-do-<n>`; `down` touches nothing else.
- No secrets, environments or write permissions for any job that can pick the pool, enforced by
  `test/unit/test_do_runner_policy.py`.

## Left (not in this slice)

- A first real run to confirm the four routed jobs pass on the container image (the image carries git, make,
  gcc, python3 and shellcheck; the jobs install the rest with their setup actions). UNVERIFIED until then.
- `ubuntu:24.04` is pulled by tag; pin a digest after the first run.
- SSH host keys are learned on first contact (accept-new), not pinned from the DO console.
- A cloud-side dead-man timer (a DO function or scheduled destroy) for the case where the operator's machine dies.
- Routing more jobs (the PostgreSQL shards need Docker service containers, so they stay hosted).
