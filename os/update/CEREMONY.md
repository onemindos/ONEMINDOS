<!-- SPDX-License-Identifier: Apache-2.0 -->
# The root key ceremony (REL-01, #153, decision D-010)

**What this is.** The one-time, offline event that makes the **root of trust** for OneMind's signed updates. Every OneMind box ships a file, `root.json`, and trusts only updates that chain back to it. This runbook makes that file and the keys behind it.

**Who does what.**
- **You (Zeus) and two other key holders** run the real ceremony, on a machine with no network, with your own hands. **No agent ever holds, sees or types a real root key**, and the root keys never touch CI.
- An agent built the script, rehearsed it end to end on throwaway keys, and wrote this runbook. The rehearsal result is in [Rehearsal record](#rehearsal-record). The printable one-page version is [CEREMONY-CHECKLIST.md](CEREMONY-CHECKLIST.md).

## Words you need

- **TUF** ("The Update Framework"): the signing design OneMind uses (see [CHANNEL.md](CHANNEL.md) and [lesson 08](../../docs/learning/08-security-pipeline-and-tuf.md)). One stolen key cannot push a bad update.
- **Root key:** signs `root.json`, which says which keys may sign updates. Kept **offline**, rarely used. D-010: **three** root keys, each on its own encrypted USB stick, and **any 2 of the 3** must sign. One lost stick or one stolen stick changes nothing by itself.
- **Online keys:** `targets`, `snapshot`, `timestamp`. The release pipeline signs with these every night, so CI holds them as GitHub secrets. They are different keys from the root keys, and if one leaks the root can replace it.
- **Passphrase:** each root key file is locked with a passphrase its holder chooses. A stolen stick is useless without it, and a lost passphrase cannot be recovered.
- **Air-gapped:** a computer with no network at all (Wi-Fi off, cable out, no Bluetooth). The script warns if it still sees a route out.

## What you need

| Item | Notes |
|---|---|
| 3 USB sticks, one per holder | Encrypted at the file-system level (step 3). Kept in 3 places: home, off-site, a trusted person (D-010) |
| 1 extra stick, the "transfer stick" | Carries only **public** files in and out. Never a private key |
| 1 offline computer | Best: a laptop booted from a Debian live USB (it forgets everything at shutdown). A Mac with networking off also works |
| 3 people | You, the other two holders, ideally all three in one room. Only 2 sign, but all 3 sticks are made |
| Paper and a printer | To print the sheet from step 7 and the checklist |
| This repo at a commit you have reviewed | Write the commit hash on the checklist |

## Before the day: rehearse (step 0)

On the offline machine (or any Linux machine or container with networking off), once:

```sh
python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt   # needs a network: do it BEFORE going offline
PYTHON=V/bin/python scripts/tuf-bootstrap-root.sh rehearse /tmp/rehearsal-1
```

You should see `REHEARSAL PASSED`. It does the whole ceremony on throwaway keys: three root keys, 2-of-3 signing with one holder absent, online keys, the final check and a signed test release checked as a box would. Delete `/tmp/rehearsal-1` afterwards. The command refuses an existing directory and refuses to run in CI.

## The ceremony

Use the commands as written. `<stick-a>` is where holder A's stick is mounted (for example `/Volumes/STICK-A`).

1. **Go offline.** Do all steps that need a network first (clone the repo, install the pinned tools as above). Then switch off Wi-Fi and Bluetooth and unplug the cable. Run `scripts/tuf-bootstrap-root.sh` once: it must **not** print `WARNING: this machine has a default route`.
2. **Check the code.** `git rev-parse HEAD` must equal the hash on your checklist, and `git status` must be clean.
3. **Encrypt each stick.** Each holder does their own, alone, and picks their own strong passphrase (at least 12 characters; a few random words is good).
   - Mac: Disk Utility → Erase → format *APFS (Encrypted)*.
   - Linux: Disks → format → *Encrypted (LUKS)*.
   The stick's passphrase and the key's passphrase (step 4) may be the same; they are never written down in the repo or on the stick.
4. **Make the root keys, one holder at a time.** Each holder mounts their own stick and types their own passphrase, twice:
   ```sh
   scripts/tuf-bootstrap-root.sh root-key <stick-a> root     # holder A
   scripts/tuf-bootstrap-root.sh root-key <stick-b> root     # holder B
   scripts/tuf-bootstrap-root.sh root-key <stick-c> root     # holder C
   ```
   Each stick now has `root.key` (private, stays on the stick) and `root.pub` (public). Copy each `root.pub` to a folder on the machine named `pubs/a.pub`, `pubs/b.pub`, `pubs/c.pub`. The script never overwrites an existing key.
5. **Make the online keys.** `scripts/tuf-bootstrap-root.sh online-keys online` writes `online/targets.key`, `snapshot.key`, `timestamp.key` (private) and the `.pub` files.
6. **Sign the root.** Two holders sign. Here A and B are present and sign; C's public key is trusted but C's stick stays untouched. Each signer types their own passphrase when asked:
   ```sh
   scripts/tuf-bootstrap-root.sh create out security 2 <stick-a>/root.key <stick-b>/root.key pubs/c.pub -- \
     online/targets.pub online/snapshot.pub online/timestamp.pub
   ```
   Change `security` for the other channel (a second `create` with a new directory, for example `out-stable ... stable ...`). The script refuses to write into a directory that already holds a root.
7. **Read the sheet out loud, then print it.** `scripts/tuf-bootstrap-root.sh check out 2 3` prints the numbers a box will trust. All must be true: `root threshold 2 of 3`, three different root key ids, one key each for targets, snapshot and timestamp, two valid signatures, about 365 days left. **All three holders read the `sha256` line and the key ids from the screen** and sign the printout. Exit code 1 means stop: something is wrong, do not use these files.
8. **Move the public file out.** Copy **only** `out/root.json` to the transfer stick. Check the sha256 on the online computer matches the printout (`shasum -a 256 root.json`).
9. **Publish (on the online computer, by you).**
   - Commit `root.json` as `os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json` (and `.../stable/root.json` for the stable channel) in a PR, so the gate reviews it. `root.json` is public.
   - Put the three online private keys into GitHub as **repository secrets** (this is what `.github/workflows/security-nightly.yml` reads today):
     ```sh
     gh secret set ONEMIND_TUF_TARGETS_KEY   < online/targets.key
     gh secret set ONEMIND_TUF_SNAPSHOT_KEY  < online/snapshot.key
     gh secret set ONEMIND_TUF_TIMESTAMP_KEY < online/timestamp.key
     ```
     Do this by carrying the three `.key` files on the **transfer stick only for this step**, then wipe it. Moving them into a protected GitHub *Environment* (CORE-SEC-8) needs the workflow to declare that environment: a separate change, not part of this ceremony.
   - Signed releases need more than the TUF keys: `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT` and the variable `ONEMIND_SECURITY_PUBLISH=true` ([README](README.md)). Those are not made here.
10. **Wipe the online machine.** Shut the live USB down (it forgets), or securely delete `online/` and `out/`. The root `.key` files exist only on the three sticks. Wipe the transfer stick.
11. **Store the sticks** in three places, one each: home, off-site, a trusted person. The succession note (who may act if you cannot, and where the sticks and passphrases are) goes in a **sealed envelope, never in the repo**.
12. **Calendar the renewal.** The root **expires after 365 days** ([channel.json](channel.json)), and a box refuses an expired root, so put a reminder 60 days before. **Renewal is not built yet:** it needs a new `2.root.json` signed by 2 of the 3 holders (and by the old root keys, as TUF's root rotation requires). `tuf-repo.py init-root` has a `--version` option, but `scripts/tuf-bootstrap-root.sh` has no renewal command and no rehearsal for it. That is a follow-up to finish within the year; moving the root onto hardware tokens (#272) is the same kind of rotation and counts as the required drill (D-010).

## If something goes wrong

| Symptom | What it means | What to do |
|---|---|---|
| `refusing: a TUF root is made offline, never in CI` | A `CI` or `GITHUB_ACTIONS` variable is set | Run it in a normal terminal, not in a workflow |
| `WARNING: this machine has a default route` | The machine can still reach a network | Stop. Unplug and switch off networking, then start again |
| `wrong passphrase` | That holder mistyped | Retype. Three failures: check the stick is the right one |
| `refusing to overwrite a key` / `already holds a root.json` | The folder already has a key or a root | Use a **new** folder. Never delete a real root.json to retry: ask the gate |
| `need at least 2 distinct root keys, 2 of them to sign` | Fewer than 2 private keys were given | Two holders must be present and sign |
| `check` prints a `FAIL` line | The root is not the shape D-010 requires | Do not use it. Delete the output folder and redo step 6 |
| A holder loses a stick or its passphrase | One of three is gone; 2-of-3 still works for signing | Nothing breaks today. Replacing the third key needs the renewal tooling (step 12), which is not built yet: tell the gate |

## Rehearsal record

First run by **Claude builder 2** on 2026-11-15, throwaway keys only, in a Linux container (`python:3.13-slim-trixie`, pinned dependencies from `requirements-tuf.txt`) with **networking off** (`--network none`), the stand-in for an air-gapped VM:

- `scripts/tuf-bootstrap-root.sh rehearse` completed: three encrypted root keys, a 2-of-3 root signed by two of them with the third trusted by its public key only, `inspect` clean (threshold 2 of 3, 365 days), a test release signed with the online keys and `tuf verify: 3 target(s) checked, 0 problem(s)`.
- The same steps run for real (`root-key` ×3, `online-keys`, `create` with a `.pub` for the absent holder, `check`) are in `os/update/tests/test_tuf_ceremony.py` and run in CI on every change to `os/update/`.

**Gaps the rehearsal found, now fixed:** the old `rehearse` made one root key at threshold 1 (not the real shape) and never verified the result; root keys could not be passphrase-protected, so D-010's encrypted sticks could not be used; `create` could not take an absent holder's public key; nothing prevented a second `create` from overwriting a root; the old header pointed to a `handbook/keys/CEREMONY.md` that did not exist.

**Not covered by the rehearsal (needs people and hardware):** typing real passphrases at the terminal (the rehearsal reads a throwaway one from the environment), encrypting real sticks, the order of who reads what aloud, and the GitHub secret step. The checklist covers them.
