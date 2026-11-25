<!-- SPDX-License-Identifier: Apache-2.0 -->
# Merge-queue runner pool (`MQ_RUNNER`, label `onemind-mq`)

**Why.** Merge-queue (`merge_group`) runs used to wait behind `pull_request` runs for GitHub's ~20 hosted
slots, and nothing merged for hours. A job went either to hosted runners or to the `onemind-local` pool.
Now every job that can use `onemind-local` has one more branch, checked first:

```
(vars.MQ_RUNNER == 'on' && github.event_name == 'merge_group') && ["self-hosted","onemind-mq"]
  || <the existing LOCAL_RUNNER expression, unchanged>
  || 'ubuntu-24.04'
```

- **Off by default.** With `MQ_RUNNER` unset the first branch is false and routing is exactly what it was.
- **merge_group only.** A pull request (fork or not) can never select `onemind-mq`. A `merge_group` run only
  executes code already approved into the queue, so it is always trusted and needs no fork check.
- **Same jobs as `onemind-local`**, nothing else: no secrets, no repo writes, no Docker, no KVM. `gate.yml`
  (`merge-gate`, `LOCAL_GATE`) and the image/battery jobs (`KVM_RUNNER`) are untouched.
  `test/unit/test_local_runner_policy.py` enforces all of this.

## Turning it on

1. Register runners with the label `onemind-mq` (any mix of the Mac VMs, DigitalOcean and the R530 worker;
   `run-one.sh` today accepts only `onemind-local|onemind-gate`, so register mq runners with GitHub's own
   `config.sh --ephemeral --labels onemind-mq` until `cycle` learns the label).
2. `gh variable set MQ_RUNNER --body on`.
3. Off switch: `gh variable set MQ_RUNNER --body off` (or delete it). Queued jobs fall back to hosted on the next run.

If `MQ_RUNNER` is on but no `onemind-mq` runner is online, merge-queue jobs wait. Switch it off.

## What the pool image must provide

The jobs were written for GitHub's hosted Ubuntu 24.04 image. A plain Ubuntu 24.04 or Debian 13 runner needs
these, which the jobs use without installing them:

| Needed | Used by |
|---|---|
| `git`, `curl`, `jq`, `make`, `build-essential`, `unzip`, `xz-utils` | most jobs (same list as `provision.sh`) |
| `python3`, `python3-venv`, `python3-yaml`, `python3-pip` | ci.yml `unit` (it also runs `sudo apt-get install python3-yaml`), ci-apps, hygiene |
| `shellcheck` | e2e.yml, `make lint` |
| Node 22 (pinned in `runner.pin`; worker VM only) | ci-apps `validate` (offline-map JS tests; it also runs `setup-node`) |
| passwordless `sudo` | ci.yml, brand.yml (`apt-get install python3-pil`), ci-apps.yml (clamav), hygiene.yml (gitleaks to `/usr/local/bin`), e2e.yml |
| a writable tool cache and network to the GitHub and npm/PyPI/Go registries | `setup-node`, `setup-go`, `setup-uv`, `setup-python` download their own toolchains |
| a Go toolchain only through `setup-go`; Docker is not required | ci-sdk.yml runs `go vet` and `go test` after `setup-go` |
| browsers and their system libraries (`npx playwright install --with-deps`) | e2e.yml and ui-quality.yml run it themselves, which needs sudo |
| Android SDK, Xcode, Docker, KVM | not used by any job that can reach this pool |

`setup-python` has no Python 3.13 build for Debian; the one known job is ci-apps `validate` (see the policy
test). An x86_64 pool (DigitalOcean, R530) does not have this arm64 limit.
