<!-- SPDX-License-Identifier: Apache-2.0 -->
# x86 KVM CI runner on a Proxmox VE host (CI-14)

**Ties to:** the CI capacity work (CI-09, CI-10 issue #299, [`docs/learning/self-hosted-runner.md`](../../docs/learning/self-hosted-runner.md)) and M-LIVE: OS images have to build and pass the battery before anyone can use them. Changes no decision in `docs/DECISIONS.md`.

## What it is, in plain language
The heaviest CI jobs build OneMind OS images and boot them in QEMU: `image` (x86 boards), `smoke`, `battery`, `cloud` and `installer`. They need an **x86** machine with **KVM** (hardware virtualisation), so they could not move to the Mac runner, and they are what fills GitHub Free's ~20 job slots. Any Proxmox VE server has both. This kit turns one into a runner for exactly those jobs.

- **One fresh VM per job.** A template VM (Ubuntu 24.04, like GitHub's `ubuntu-24.04` runners, with Docker and the pinned Actions runner) is cloned for each job (a ZFS or LVM-thin *linked clone*: instant, near-zero space), takes **one** job as an **ephemeral** runner, powers off, and is destroyed. Nothing one job does reaches the next.
- **Its own network.** Job VMs sit on `vmbr1`, a bridge with no physical port, NATed to the internet over IPv4. Blocked: every private range (the home LAN, `100.64.0.0/10` for the mesh, link-local), the Proxmox host itself, spoofed source addresses and **all IPv6**. Each job VM's port is *isolated*, so concurrent jobs cannot see each other. CI code can download packages but cannot reach the iDRAC, Proxmox, the lab VMs or anything else at home.
- **A single-use credential.** For each VM the host asks GitHub for a *just-in-time* (JIT) runner config: it registers exactly one runner, with fixed labels (`self-hosted`, `onemind-kvm`) in a fixed group, and works once. Unlike an org registration token, a job that digs it out of memory cannot use it to register other runners. It reaches the VM through the QEMU guest agent on stdin (no SSH, no LAN address), and the runner registration is deleted when the VM is.
- **Nothing changes under a job.** Clones do no package upgrade at boot (`ciupgrade 0`), the apt timers and unattended-upgrades are gone, and the buildkit image is already in the template (Docker Hub rate-limits anonymous pulls).
- **A switch.** The repo variable `KVM_RUNNER` decides. While the service runs it is `on`; when the service stops it is set `off`, and the jobs go back to GitHub-hosted runners in the next run.

## Which jobs, and how fork PRs are kept out
Two layers. **On the machine:** every job first runs a job-started hook in the VM that refuses any pull-request event whose head repository is not this repository (or is gone). A fork PR runs its own copy of the workflow files and could hard-code this runner's labels, but it cannot change the VM. **In the workflows:** each job chooses its runner with one expression: `KVM_RUNNER` is `on` **and** the event is not a pull request or the pull request comes from this repo (never a fork). Otherwise `ubuntu-24.04`. Jobs: `image` (x86 legs only; arm64 legs keep `ubuntu-24.04-arm`), `smoke`, `cloud`, `installer` in `image.yml`, and `battery` in `battery.yml`, except when `security-nightly` calls it: the release-signing path always stays GitHub-hosted, so a home machine never vouches for a release. `test/unit/test_kvm_runner_policy.py` fails a PR that changes these expressions by a single character, adds an unreviewed `self-hosted` job, or lets one of these jobs read a secret; it also runs the fork hook against sample events. Fork-PR approval stays **Require approval for all outside collaborators**: approving a fork PR's run does not get it past the hook.

## Founder steps (once)
1. **Runner group:** reuse `onemind-local` (CI-10 made it: ONEMINDOS only, public repos allowed). Fork-PR approval stays **Require approval for all outside collaborators**.
2. **A fine-grained GitHub token** (github.com → Settings → Developer settings → Fine-grained tokens → Generate):
   - Resource owner: **onemindos**; expiry: 90 days (put a reminder in your calendar);
   - Repository access: **Only select repositories → ONEMINDOS**; Repository permissions: **Variables: Read and write**;
   - Organization permissions: **Self-hosted runners: Read and write** (it mints JIT configs and deletes finished runners). Nothing else.
   If the org requires approval for fine-grained tokens, approve it under org Settings → Personal access tokens.
3. **On the Proxmox host** (as root), copy this folder and run `up` once to write the settings file, set `STORAGE` (VM disks) and `SNIPPETS` (a storage with "Snippets" content) in `/etc/onemind-ci-kvm.env`, then give it the token. You type the token; it is never shown or stored outside `/etc/onemind-ci-kvm.token` (root, 0600):

```bash
scp -r scripts/ci-runner-kvm root@<proxmox-host>:/opt/
```

```bash
ssh -t root@<proxmox-host> /opt/ci-runner-kvm/up --token
```

The first `up` with a token builds the network and the template (about 10 minutes), then starts `onemind-ci-kvm.service`.

## Everyday use (on the host)
| I want to | Run |
|---|---|
| see the switch, template, job VMs and recent rounds | `/opt/ci-runner-kvm/status` |
| watch it work | `journalctl -fu onemind-ci-kvm` |
| stop taking jobs (KVM_RUNNER off, jobs go to GitHub) | `/opt/ci-runner-kvm/down` |
| rebuild the template from the pinned image | `/opt/ci-runner-kvm/down --wipe`, then `up` |
| more or fewer parallel jobs | `INSTANCES=` in `/etc/onemind-ci-kvm.env`, then `systemctl restart onemind-ci-kvm` (each job VM: 4 cores, 8 GiB, a 150 GiB thin disk) |

## Limits and known risks
- **Queued jobs do not move by themselves.** If the host goes down without the service stopping cleanly (power cut), `KVM_RUNNER` stays `on` and new x86 jobs wait for it. Set it off from anywhere: `gh variable set KVM_RUNNER --body off --repo onemindos/ONEMINDOS`, then re-run the waiting jobs.
- **Results come from a different x86 machine than GitHub's.** A job that passes here and fails on GitHub (or the reverse) is a real signal: report it.
- The runner, the Ubuntu image and their checksums are pinned in `runner.pin`; bump them in a PR. A JIT runner may still update itself when GitHub requires a newer version; the next template rebuild picks up the pin.
- Job limits: a job is stopped after `MAX_JOB_MIN` (300) minutes counted from when it starts; a VM that gets no job within `MAX_IDLE_MIN` (360) is recycled with a fresh config.
- The template's `runner` user has passwordless `sudo`, as on GitHub's runners. That is safe only because each job VM is destroyed afterwards and holds no secret.
