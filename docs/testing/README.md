<!-- SPDX-License-Identifier: Apache-2.0 -->
# Testing OneMind OS

> **Explain it like I am the founder**
> Three files work together. [TEST-REGISTER.md](TEST-REGISTER.md) lists every test we still owe (each has a `TR-###` id). [RESULTS.md](RESULTS.md) is the logbook: one line per run, never edited afterwards. This README says how to run a test, how to write the line, and what happens when a test fails.

## 1. Pick a test

Open [TEST-REGISTER.md](TEST-REGISTER.md) and pick a row whose **Now?** column you can satisfy:

- `now` + `agent·CI`: run it from GitHub Actions (section 2).
- `now` + `agent·VM`: an agent runs it in a disposable Lima VM or on a CI runner with KVM. Nothing is installed on the Mac itself; the VM is deleted afterwards.
- `founder`: you run it with the hardware or account named in **Who**. If the row links a lab kit (`lab-kits/LT-*`), follow the kit; it has its own pre-registered pass/fail table.
- `after <branch>` or `after #NN`: wait for that merge.

Rule from the QEMU battery ([`test/qemu/CRITERIA.md`](../../test/qemu/CRITERIA.md) §1): a test that cannot run because of the environment is **BLOCKED** with the reason, never PASS.

## 2. Run every automated test at once

The `test-all` workflow ([`.github/workflows/test-all.yml`](../../.github/workflows/test-all.yml)) dispatches every test workflow on `main`, waits for them and writes one summary table (workflow, run link, outcome).

- GitHub: **Actions → test-all → Run workflow**. Inputs: `ref` (a branch or tag, default `main`), `heavy` (also run the image build, the nightly battery and the security pipeline in dry-run mode; on by default), `wait_minutes` (how long to wait before reporting runs as still running).
- Terminal: `gh workflow run test-all.yml -f ref=main -f heavy=true`, then `gh run watch`.

Light workflows take minutes; with `heavy` on, expect a few hours (the nightly battery runs T0–T10 on two boards). The security pipeline is always dispatched with `dry_run=true`, so it never publishes. A workflow on `main` that `test-all` does not know is listed as "not in test-all" so it gets added.

One workflow at a time: `gh workflow run <file> [-f key=value]`, for example `gh workflow run battery.yml -f board=vm -f upto=T5`.

## 3. Record the result

Two ways, both fine:

1. **Issue form:** New issue → **Test result**. Fill in the TR id, environment, outcome and logs. A maintainer copies the line into RESULTS.md.
2. **Directly:** append one line to the table in [RESULTS.md](RESULTS.md) in a PR.

Each line has:

| Field | What to write |
|---|---|
| Date | UTC date of the run, `YYYY-MM-DD` |
| TR | The register id, e.g. `TR-005` (several: `TR-005, TR-006`) |
| Commit | The short commit of the code under test (`git rev-parse --short HEAD`, or the run's commit) |
| Tester | Your GitHub handle, or `agent` for an AI agent run |
| Environment | Where it ran, without private details: `GitHub ubuntu-24.04`, `Lima debian-13 arm64`, `Beelink U55`, `Pi 5 4 GB`, `iPhone (iOS 26)` |
| Outcome | `pass`, `fail`, `blocked` (environment limit, with the reason) or `partial` (say which steps) |
| Evidence | A link: the Actions run, the issue, or a file under `research-output/evidence/` or a lab kit's RESULT file |

Then update the row's **Status** in the register in the same PR (`passed`, `failed`, `fix needed`).

**Keep the public repo clean.** Logs and photos must not show IP addresses, MAC addresses, serial numbers, e-mail addresses, tailnet names, tokens or home paths. Redact first: [`lab-kits/common/redact.sh`](../../lab-kits/common/redact.sh). `make hygiene` blocks most of these, but read what you paste.

## 4. When a test fails

1. Record the `fail` line in RESULTS.md with the evidence link, and set the row's status to `fix needed`.
2. Open an issue (or use the Test result issue) that names the TR id, what was expected (copy the **Expected result** cell) and what happened.
3. The fix goes in its own PR. Its title or body says `Fixes TR-###` and links the issue; the PR puts its number in the row's **Fix PR** column.
4. After the fix merges, rerun the same test the same way and append a new line. Never edit the old line: the log shows the failure and the fix.
5. If the fix changes a pre-registered pass/fail table (a lab kit or `CRITERIA*.md`), add a new dated section to that file; do not edit the old criteria.

## 5. Adding tests

Every PR that adds behaviour it could not test (no hardware, no account, emulation only) adds a register row in the same PR, with the next free id in its group. IDs are never reused.
