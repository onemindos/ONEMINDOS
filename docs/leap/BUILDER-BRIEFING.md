<!-- SPDX-License-Identifier: Apache-2.0 -->
# Builder briefing: read this before you change anything

**For every agent (Claude, Codex, GPT) and person building a OneMind OS PR.** It lists the mistakes that cost the most review rounds on 2026-11-24/25. Each one is cheap to avoid and expensive to miss: one extra round means another full image build and VM boot (30 to 90 minutes).

The full rules stay in [AGENT-QUEUE.md](AGENT-QUEUE.md) and the repo's `CLAUDE.md`. This page is the short list of what reviewers kept sending back.

## Why OneMind changes take longer than a normal Debian change

OneMind is an appliance OS: a read-only root, A/B updates through RAUC, health-gated rollback, encrypted `/data`. A Debian package that installs fine on a normal system can still break first boot, an update or a rollback here. That is why OS changes are proven in QEMU, not just installed.

## Before you open the PR: the checklist

1. **Run the WHOLE unit suite**, not only your test file: `python3 -I -m unittest discover -s test/unit`. Many repo-wide checks live there (unit hardening, services registry, pins, pre-registration). Most "round 2" reds came from skipping this.
2. **New or changed systemd unit?**
   - It must pass `test/unit/test_unit_security.py`: sandbox it (`ProtectSystem=strict`, minimal `ReadWritePaths`, `NoNewPrivileges`, `CapabilityBoundingSet`, `RestrictAddressFamilies`, `ProtectKernel*`, `SystemCallFilter=@system-service`). Never raise `DEFAULT_CEILING`; add a `CEILINGS` entry only with a written reason.
   - Add its card to `os/rootfs/layers/onemind/usr/lib/onemind/services.yaml` (checked by `test/unit/test_services_registry.py`).
3. **The root filesystem is read-only.** Anything a service writes (state, caches, keys, configs a person changes) goes on `/data`: a bind mount in the board fstab, the directory created by `onemind-data-layout.service`, a mount point in the Containerfile, and the unit ordered after the data check. `/etc` changes at runtime do not stick.
4. **New QEMU check?** Pre-register it: commit the criteria (in the matching `test/qemu/CRITERIA-*.md`) in its own commit **before** the code, and append the file's new sha256 to `test/qemu/PREREGISTRATION.sha256`. After a merge that touches the same criteria file, recompute the last hash line.
5. **Recommends are off** in the image (`os/rootfs/sources/configure-apt.sh`). List every package you need explicitly; a dependency you get on a laptop may be missing on the box.
6. **Anything a person can change** needs the API (in `core/`), a dashboard screen (`@onemind/sdk`, commit only `sdk/openapi/onemind-v1.json`), and an `onemind` CLI command (Cobra, `--json`), in the same PR or stated under "Not done". Writes are **owner actions through the approval queue**; agents and the CLI only request. Destructive and security-related changes need the passkey step-up (D-027, D-028).
7. **Root never follows a path the owner or an app controls.** Refuse symlinks (`-L`) in home and app directories, or do the write as that user (`runuser`). A symlinked `authorized_keys` pointing at the shadow file was a real hole.
8. **Network and firewall changes** must have an automatic revert (NetworkManager checkpoint, or a revert timer) that a failure cannot skip: save first, then stop the timer.
9. **Durable writes** for anything first boot creates: write a temp file, fsync it, rename, fsync the directory, then `syncfs` before marking first boot done. A power cut in the first minute otherwise leaves 0-byte keys.
10. **Before every push:** `make lint`, `python3 -I scripts/changes.py check`, `make hygiene`, gitleaks. Sign off every commit (`git commit -s`). Never rebase or force-push; merge `origin/release/next` in instead. Never export `GIT_DIR` or `GIT_WORK_TREE`.

## Testing an OS change without wasting hours

- **While iterating**, run the smaller set: your unit and Go/Python tests, then image build plus first boot only:
  `om-remote <worktree> 'make image BOARD=x86_64-efi TOOLS=onemind-tools:ci && make fixtures UPTO=T0 && make firstboot FUPTO=F2 KVM="--device /dev/kvm"'`.
- **Once, at the end**, run the full OS sequence: `make bootlock`, `make firewall`, `make battery UPTO=T5`.
- **Known harness reds that are not yours** (as of 2026-11-25; check the tracking issues before assuming): the firewall scan running before k3s listens (FW3, fixed in #1108), the F3/B2 hang after a reboot on fast machines, bootlock B2 flakiness. Note them in the PR; do not "fix" them by weakening a test.
- `om-remote` runs on the shared build machines. Do not leave long runs behind: if you stop waiting, the remote run is stopped for you, but a killed agent can still leave one.

## Reading reviews

The Opus review is the merge gate. Fix **every** item it lists, including the "should fix" ones, and answer each in your push summary. Do not push wording changes after an approval without asking for a re-review: the merge train skips any PR with commits newer than its last approval.
