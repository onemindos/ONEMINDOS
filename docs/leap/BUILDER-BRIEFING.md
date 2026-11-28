<!-- SPDX-License-Identifier: Apache-2.0 -->
# Builder briefing: read this before you change anything

**For every agent (Claude, Codex, GPT) and person building a OneMind OS PR.** It lists the mistakes that cost the most review rounds on 2026-11-24/25. Each one is cheap to avoid and expensive to miss: one extra round means another full image build and VM boot (30 to 90 minutes).

The full rules stay in [AGENT-QUEUE.md](AGENT-QUEUE.md) and the repo's `CLAUDE.md`. This page is the short list of what reviewers kept sending back.

## Why OneMind changes take longer than a normal Debian change

OneMind is an appliance OS: a read-only root, A/B updates through RAUC, health-gated rollback, encrypted `/data`. A Debian package that installs fine on a normal system can still break first boot, an update or a rollback here. That is why OS changes are proven in QEMU, not just installed.

## Before you open the PR: the checklist

1. **Run the WHOLE unit suite**, not only your test file: `python3 -I -m unittest discover -s test/unit`. Many repo-wide checks live there (unit hardening, services registry, pins, pre-registration). Most "round 2" reds came from skipping this.
   - **Run it on Linux with `ONEMIND_REQUIRE_SYSTEMD_ANALYZE=1`**, as CI does. On a Mac `systemd-analyze` is missing, so `test_unit_security.py` skips the hardening test silently and a green Mac run proves nothing for item 2.
   - Three suites need the gateway's Python and skip under system Python: CI runs `test_firstboot.py`, `test_rescue_install.py` and `test_starting.py` with `core/.venv/bin/python -I -m unittest discover -s test/unit -p '<file>'` (after `uv sync --project core --frozen --python 3.12`; see `.github/workflows/ci.yml`).
2. **New or changed systemd unit?**
   - It must pass `test/unit/test_unit_security.py`: sandbox it (`ProtectSystem=strict`, minimal `ReadWritePaths`, `NoNewPrivileges`, `CapabilityBoundingSet`, `RestrictAddressFamilies`, `ProtectKernel*`, `SystemCallFilter=@system-service`). Never raise `DEFAULT_CEILING`; add a `CEILINGS` entry only with a written reason.
   - Add its card to `os/rootfs/layers/onemind/usr/lib/onemind/services.yaml` (checked by `test/unit/test_services_registry.py`).
3. **The root filesystem is read-only.** Anything a service writes (state, caches, keys, configs a person changes) goes on `/data`:
   - a bind mount in the board fstab: `os/rootfs/layers/base/etc/fstab` on x86; rpi5 and the installer have their own copies at `os/boards/<board>/rootfs/etc/fstab`. The binds use `x-systemd.requires=onemind-data-layout.service`;
   - the directory, created by `onemind-data-layout.service`;
   - a mount point in the Containerfile;
   - the unit ordered after the data check: `After=onemind-data-layout.service` or `RequiresMountsFor=/data`.
   - Writes to `/etc` at runtime fail (read-only root) or are lost at the next update.
4. **New QEMU check?** Pre-register it: commit the criteria (in the matching `test/qemu/CRITERIA-*.md`) in its own commit **before** the code, and append the file's new sha256 to `test/qemu/PREREGISTRATION.sha256`.
   - `PREREGISTRATION.sha256` is an **append-only log**: one line per version (`<sha256>  <FILE>  <UTC time>  (note)`). Tests check that the current hash is listed somewhere. After a merge that changes a CRITERIA file, **append a new line** with the merged file's hash and a note. Never edit or replace an old line.
   - A CRITERIA file only grows by new dated sections at the end (typo fixes excepted), as each file's Status line says.
5. **Recommends are off** in the image (`os/rootfs/sources/configure-apt.sh`). List every package you need explicitly; a dependency you get on a laptop may be missing on the box.
6. **Anything a person can change** needs the API (in `core/`), a dashboard screen (`@onemind/sdk`, commit only `sdk/openapi/onemind-v1.json`), and an `onemind` CLI command (Cobra, `--json`), in the same PR or stated under "Not done". Writes are **owner actions through the approval queue**; agents and the CLI only request. Do not invent your own check: use the gateway's existing passkey step-up (L1 today). D-028 sets **L2** as the target for destructive and physical approvals and every security-related setting, and every new agent, app and person starts on "Always ask". The locked rule stays: AI never actuates without human approval (D-027, D-028 in `docs/DECISIONS.md`).
   - **This is a test now, not only a review rule** (#1232). `test/unit/test_surface_parity.py` runs `sdk/tools/surface-parity` over `sdk/openapi/onemind-v1.json`: every operation needs a dashboard caller, every write (POST, PUT, PATCH, DELETE) an `onemind` command, and every operation in the phone's scope a mobile caller. A caller is found by `@onemind/sdk` or Go SDK method, or by a call with its HTTP method; comments, tests, mocks and compared paths do not count, and a path sent by a helper that hides the method counts only through an `indirect` line naming where the method is sent. Anything else must be listed in `sdk/tools/surface-parity/exemptions.txt` under a group with a reason and an owner issue. Never add a line there to get green: build the screen and the command, or argue the group in review under "Not done". When your screen or command lands, the test reports the line as stale: delete it in the same PR. See every operation's callers with `python3 -I sdk/tools/surface-parity --report`.
   - **Mobile scope for 1.0** (founder to confirm, #1232): the phone covers approvals, files, photos and the person's own devices. Market, Work, Machines, Storage and Troubleshoot are dashboard-only. The `mobile-scope` lines at the top of `exemptions.txt` hold this decision.
7. **Root never follows a path the owner or an app controls.** Refuse symlinks (`-L`) in home and app directories, or do the write as that user (`runuser`). A symlinked `authorized_keys` pointing at the shadow file was a real hole.
8. **Network and firewall changes** must have an automatic revert (NetworkManager checkpoint, or a revert timer) that a failure cannot skip: save first, then stop the timer.
9. **Durable writes** for anything first boot creates: write a temp file, fsync it, rename, fsync the directory, then `syncfs` before marking first boot done. A power cut in the first minute otherwise leaves 0-byte keys.
10. **Sovereignty check (founder, 2026-11-26; [docs/design/SOVEREIGNTY.md](../design/SOVEREIGNTY.md)).** For every new dependency, engine, service, Market app or feature, answer these in the PR:
    - Does it work offline on the box?
    - Is its licence open? Under D-035, only MIT/BSD/Apache-2.0/MPL-2.0/public-domain code goes in app binaries, and never Google Play Services or another closed SDK.
    - Does it need any outside account or cloud?
    - Is the data open and exportable?
    - Does it call home?
    - Can the owner use their own keys and their own update source?
    - Can it be swapped?
    - Did you check for a Debian package or Linux feature first?

    A "no" needs a written reason or an issue.
11. **Every app is API, CLI and MCP native** (D-035): a REST route in the OpenAPI, an `onemind <app>` CLI group, and MCP tools (reads, plus request-only tools that a person approves), all in the same PR.
12. **Before every push and in the PR:**
   - `make lint`, `python3 -I scripts/changes.py check`, `make hygiene`, gitleaks. Sign off every commit (`git commit -s`). Never rebase or force-push; merge `origin/release/next` in instead. Never export `GIT_DIR` or `GIT_WORK_TREE`.
   - The base branch is `release/next`.
   - Write **`Refs #n`, never `Closes #n`**: this is the gate rule in force. Known conflict, flagged for the founder: `docs/leap/AGENT-QUEUE.md` and `.github/pull_request_template.md` still say `Closes #`. Follow the gate rule until they are fixed.
   - One `changes/<branch-with-dashes>.md` fragment per PR. Never edit `CHANGELOG.md` or `docs/leap/STATUS.md`.
   - After a `core/` API change: `make -C sdk gen`, then `make -C sdk check-stale`.

## Testing an OS change without wasting hours

- **While iterating**, run the smaller set: your unit and Go/Python tests, then image build plus first boot only:
  `make image BOARD=x86_64-efi TOOLS=onemind-tools:ci && make fixtures && make firstboot FUPTO=F2`.
  `make fixtures` defaults to `UPTO=T5`, the smallest set (do not pass `UPTO=T0`: the script treats anything but T5 as the larger T10 set and builds extra bundles). Do not force a KVM flag: the Makefile adds `--device /dev/kvm` itself when `/dev/kvm` is writable, and forcing it where KVM is missing only hides the real problem.
- **Once, at the end**, run the full OS sequence: `make bootlock`, `make firewall`, `make battery UPTO=T5`. **Battery runs last** because it boots the fixture disk itself and leaves it updated; `firstboot`, `bootlock` and `firewall` copy the disk, so they must run before it (or after fresh fixtures).
- **Plus the target for the area you touched:** `make wizard`, `make edge` (fixtures made with `EDGE=1`), `make sysextguard`, `make dataenc` (fixtures with `DATA_FS=luks2`), `make memory-test`, `make secureboot-test`.
- **Known harness reds that are not yours** (as of 2026-11-25; check the tracking issues before assuming): the firewall scan running before k3s listening (FW3, fixed in #1108); bootlock B2 **fails on unmodified release/next** ([#1150](https://github.com/onemindos/ONEMINDOS/issues/1150)); the F3/B2 hang after a reboot on fast hosts ([#1159](https://github.com/onemindos/ONEMINDOS/issues/1159)). Note them in the PR; do not "fix" them by weakening a test.
- **`om-remote` is a local helper on the founder's build Mac, not in this repo.** Agents elsewhere (Codex, GPT) will not have it. The fallback is the same `make` commands on a Linux host with KVM, or CI's `image` workflow. A Mac cannot run the Linux-only steps (unit hardening, QEMU with KVM). Where `om-remote` exists it runs on shared build machines: wrap a command as `om-remote <worktree> '<commands>'`, and do not leave long runs behind. If you stop waiting, the remote run is stopped for you, but a killed agent can still leave one.

## Reading reviews

The Opus review is the merge gate. Fix **every** item it lists, including the "should fix" ones, and answer each in your push summary. Do not push wording changes after an approval without asking for a re-review. (Gate practice, not enforced in the repo: the gate skips a PR with commits newer than its last approval.)
