<!-- SPDX-License-Identifier: Apache-2.0 -->
# The root key ceremony (REL-01, #153, D-010 and D-031)

**What this is.** The one-time, offline event that makes the **root of trust** for OneMind's signed updates. Every OneMind box ships a file, `root.json`, and trusts only updates that chain back to it. This runbook makes that file and the keys behind it.

**Who does what.**
- **You (Zeus) are the sole key holder.** You run the first ceremony offline with three YubiKeys. Any two sign. Afterward, keep them in three different places under your sole control. Rehearse on one real spare YubiKey before preparing the three production keys. Root private keys stay inside the devices and never touch CI.
- An agent built the script, rehearsed it end to end on throwaway keys, and wrote this runbook. The rehearsal result is in [Rehearsal record](#rehearsal-record). The printable one-page version is [CEREMONY-CHECKLIST.md](CEREMONY-CHECKLIST.md).

## Rehearsal checklist

**2026-11-27** · Step 5, M-LIVE (#234) · [D-031 and D-010](../../docs/DECISIONS.md)

This is the one YubiKey procedure for the first ceremony ([D-031](../../docs/DECISIONS.md), anchor `#ceremony-on-yubikeys-d-031`). The file-key steps and printable file-key sheet further down describe the older D-010 procedure; the file-key defaults in `scripts/ceremony-guide.py` also describe it. **Secrets rule:** you type every PIN, PUK and passphrase yourself at the tool's prompt. No AI agent ever sees, holds or types one. Never put one in a command line, a file, a chat or this repo.

### Before the day

- [ ] Set aside one offline Debian laptop (a live USB works), three YubiKey 5 PIV devices for production, one spare with no credentials you need, and two USB ports or a hub so two keys can sign in the same command. Bring the paper checklist and a separate online computer with authenticated `gh` and repository settings access. For Step 5, bring a separate installer USB, the x86_64 Dell with console access, and a backup of anything on its install disk.
- [ ] **Make the transfer drive.** A USB drive used only to carry files between the offline machine and the online computer. On a Linux machine, encrypt it with LUKS (Disks → format → *Encrypted (LUKS)*, or `cryptsetup luksFormat`), with a passphrase you type yourself. It is the only thing that carries the online private keys, so it is the one place besides CI where they exist, and it is wiped at the end.
- [ ] Record the reviewed commit. The release-key installer is on `release/next` via [#1320](https://github.com/onemindos/ONEMINDOS/pull/1320). The first-ceremony commands `yubikey-key`, `rehearse-tokens` and `hsm:2?yubikey=<serial>` come from [#1172](https://github.com/onemindos/ONEMINDOS/pull/1172). Use a reviewed commit containing that tooling. Check `git rev-parse HEAD`, `git status --short` (empty), and the usage printed by `scripts/tuf-bootstrap-root.sh` (exit 2 with no arguments). If the commands are absent, stop before touching the production keys. Write the commit hash on the printed checklist. The single-device rehearsal and simultaneous signing are UNVERIFIED on real hardware.
- [ ] While the laptop is online, install `ykman`, Yubico's PKCS#11 module (`libykcs11.so`), PC/SC support, SoftHSM, and the pinned Python dependencies. On Debian: `sudo apt-get install yubikey-manager ykcs11 pcscd softhsm2` (UNVERIFIED package names: check with `apt-cache policy`). The module is then expected at `/usr/lib/x86_64-linux-gnu/libykcs11.so` (UNVERIFIED path: check with `dpkg -L ykcs11`). Run the `pip` line from the **repository root** (the path `os/update/requirements-tuf.txt` is relative to it). Use a venv outside the checkout to keep the source tree clean. Obtain the Yubico PIV attestation CA for your firmware, record its SHA-256 on the checklist before transfer, and compare it on the ceremony machine. [Yubico PIV attestation documentation](https://developers.yubico.com/PIV/Introduction/PIV_attestation.html)

  ```sh
  python3 -m venv "$HOME/onemind-tuf-venv"
  "$HOME/onemind-tuf-venv/bin/pip" install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt
  export PYTHON="$HOME/onemind-tuf-venv/bin/python"
  export PYKCS11LIB=/usr/lib/x86_64-linux-gnu/libykcs11.so   # UNVERIFIED path; use the real one
  export YUBICO_PIV_CA=/path/to/yubico-piv-ca.pem
  sha256sum "$YUBICO_PIV_CA"
  ```

  Pip must exit zero and the hash must match the recorded value. If either fails, resolve it while online. Turn off Wi-Fi and Bluetooth and unplug Ethernet before creating any keys. If the script prints a default-route warning, stop and isolate the laptop. Run `umask 077` and `unset ONEMIND_TUF_PIN ONEMIND_TUF_PASSPHRASE ONEMIND_ATTEST_WITHOUT_CA` in the ceremony shell so it uses the interactive prompts and requires attestation.
- [ ] **A live USB keeps its work in RAM.** On a live system, `mktemp -d` folders (`$R`, `$W` below) vanish at reboot or power-off. Before shutting the offline machine down, copy what you need to the transfer drive (list in step 3 of production devices). Nothing is recoverable afterwards.
- [ ] **YubiKey defaults.** A fresh YubiKey PIV has PIN `123456`, PUK `12345678` and a default management key. Anyone who knows these can use an unprepared key, so change them before the key holds a root. Three wrong PINs lock the PIN (the PUK unlocks it); three wrong PUKs block the PIV part until a reset, which erases its keys. A used or spare device is cleaned with `ykman --device "$SER" piv reset`: that erases every PIV key on it, so run it only on the spare or a brand-new key.
- [ ] **Where PINs and PUKs are kept.** Choose now. Never with their YubiKey: use a password manager you control, or a paper sealed in an envelope kept in a different place from every YubiKey. [D-010](../../docs/DECISIONS.md)'s sealed succession note (who may act if you cannot, and where the keys and PINs are) still applies and also stays out of the repo.

### Offline rehearsal and root creation

1. **Software rehearsal.** Run `scripts/tuf-bootstrap-root.sh rehearse-tokens /tmp/onemind-token-rehearsal` using the prepared `PYTHON`. Expect `REHEARSAL PASSED` for the 2-of-3 root, a verified test release, and a renewal using a different pair that refuses a lone signer. On failure, fix the logged dependency or signer error and use a fresh directory. Discard the rehearsal outputs. The same walk is available as `python3 scripts/ceremony-guide.py --yubikey --rehearsal`.
2. **One real spare.** With only the spare inserted, `ykman list --serials` must show its serial. Set `SER` to that serial. Reset it if it was ever used, then set the PIN, PUK and PIN-protected management key. The first four `ykman` commands prompt for credentials and you type them (the PIN-protected management key stores a random one on the device behind your PIN). `piv info` must show no certificate in slot 9c. If a slot is occupied after a reset, stop and choose a clean spare. Export `PYKCS11LIB` to the installed Yubico module and keep `YUBICO_PIV_CA` set. Touch the key when it blinks.

   ```sh
   ykman --device "$SER" piv reset
   ykman --device "$SER" piv access change-pin
   ykman --device "$SER" piv access change-puk
   ykman --device "$SER" piv access change-management-key --generate --protect
   ykman --device "$SER" piv info
   R=$(mktemp -d)
   scripts/tuf-bootstrap-root.sh yubikey-key "$R" spare "$SER"
   scripts/tuf-bootstrap-root.sh root-key "$R/b" root
   scripts/tuf-bootstrap-root.sh root-key "$R/c" root
   scripts/tuf-bootstrap-root.sh online-keys "$R/online"
   scripts/tuf-bootstrap-root.sh create "$R/out" security 2 \
     "hsm:2?yubikey=$SER" "$R/b/root.key" "$R/c/root.pub" -- \
     "$R/online/targets.pub" "$R/online/snapshot.pub" "$R/online/timestamp.pub"
   scripts/tuf-bootstrap-root.sh check "$R/out" 2 3
   ```

   Run each command only after the previous one succeeds. The old PIN and PUK are the defaults above, then your own, typed twice. `yubikey-key` must print the expected serial, `attestation OK`, PIN policy `always` and touch policy `always`, and write `spare.pub` beside the attestation files. **Passphrase prompts:** each `root-key` call asks for a key-file passphrase **twice** (set and confirm); these are throwaway keys, use a throwaway passphrase. `online-keys` writes three online key pairs without a passphrase (they are secrets for CI). A passphrase must be at least the script's minimum length. `create` asks for the passphrase of the `$R/b/root.key` file key (once) and then the spare's PIN, and needs a touch to sign; it reports root v1 and writes `1.root.json` and `root.json`. The two temporary file keys exercise 2-of-3 with the spare without using the production devices. `check` must exit zero and show **2 of 3**, two valid trusted signatures, three distinct root key IDs including the spare's, one key per online role and about 365 days left. Record the result, then discard the entire rehearsal directory and run `ykman --device "$SER" piv reset` again. If the PIN, touch, attestation or check fails, stop and diagnose the specific error. Check PC/SC, the module, the CA and the serial before retrying. Repeated PIN guesses can lock the device.
3. **Production devices.** After the spare passes, repeat the `change-pin`, `change-puk` and `change-management-key --generate --protect` commands and then `piv info` on each production YubiKey, one plugged in at a time (default PIN and PUK as above, then your own). Run `piv reset` on a production key only if you are sure it holds nothing you need. Use a fresh work directory (`W=$(mktemp -d)`). Set `A`, `B` and `C` to the respective serials as you identify the devices. Run each of the first three commands below with only its named device inserted. Record the serial and the printed public key ID for each on the printed checklist. After three successful attestations, generate the online keys once. Plug A and B in together and leave C unplugged. Use the PIN for each named device and touch it when prompted. `create` asks for no file passphrase here, only the two PINs.

   ```sh
   scripts/tuf-bootstrap-root.sh yubikey-key "$W/pubs" a "$A"
   scripts/tuf-bootstrap-root.sh yubikey-key "$W/pubs" b "$B"
   scripts/tuf-bootstrap-root.sh yubikey-key "$W/pubs" c "$C"
   scripts/tuf-bootstrap-root.sh online-keys "$W/online"
   scripts/tuf-bootstrap-root.sh create "$W/out" security 2 \
     "hsm:2?yubikey=$A" "hsm:2?yubikey=$B" "$W/pubs/c.pub" -- \
     "$W/online/targets.pub" "$W/online/snapshot.pub" "$W/online/timestamp.pub"
   scripts/tuf-bootstrap-root.sh check "$W/out" 2 3
   ```

   Verify the same v1, threshold, online-role, signature and expiry checks as for the spare. Match all three printed root key ID prefixes with the IDs recorded during generation and record the public `sha256` line on paper. If attestation fails or a slot is occupied, stop and retain the public diagnostics for review. For a signing or verification failure after successful attestation, fix the cause and retry with the same keys in a fresh output directory. Keep production devices intact.

   **Copy to the transfer drive, then before reboot.** Mount the LUKS transfer drive and copy exactly this list from `$W`, and nothing else:
   - `out/root.json` and `out/1.root.json` (public);
   - `pubs/*.pub` (public) and, as evidence, the attestation files next to them (`pubs/*-attest.pem`, `pubs/*-f9.pem`, `pubs/*-ykman.pub`);
   - `online/*.key` (the three online private keys, needed for the GitHub step; `online/*.pub` is also fine to copy).

   The root private keys are inside the YubiKeys and are not copied. After the copy, run `sync`, unmount, and compare `sha256sum out/root.json` on the transfer drive with the paper record.
4. **Secure deletion on the offline machine.** The online private keys now exist on the offline machine and on the transfer drive. On the offline machine, delete the `online/*.key` files with `shred -u "$W"/online/*.key` (on a live USB the RAM folders also vanish at power-off, so shut it down only after the copy is verified), then power the machine off. Do not rely on `rm`. `shred` is not reliable on SSDs and flash: that is why the drive is encrypted and wiped as a whole at the end of the handoff, and why the online keys are replaceable (rotating them is a new `online-keys` plus new secrets, no change to the root).
5. **Store the YubiKeys.** Store the three devices in three different places under your sole control. Keep the PINs and PUKs elsewhere, apart from every YubiKey. Calendar renewal 90 days before expiry. Seal the succession note (D-010) in an envelope.

### Online handoff and installer rehearsal

1. **Verify the public root.** On the online computer, mount the transfer drive. `sha256sum root.json` (or `shasum -a 256 root.json` on macOS) must match the paper record. Submit only the public root for review at `os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json`. On a hash mismatch, stop and repeat the transfer from the verified offline copy.
2. **Create the environment and load the three online TUF keys.** In GitHub: Settings → Environments → `tuf-signing` (create it if needed) → Deployment branches and tags → **Selected branches and tags** (not "Protected branches") → add `main`. Leave required reviewers off so nightly signing and timestamp refresh can run. **Verify before any `gh secret set`:**

   ```sh
   gh api repos/onemindos/ONEMINDOS/environments/tuf-signing -q .deployment_branch_policy
   gh api repos/onemindos/ONEMINDOS/environments/tuf-signing/deployment-branch-policies -q '.branch_policies[].name'
   ```

   The first must show `custom_branch_policies` true (and `protected_branches` false). The second must print only `main`. If not, stop and fix the setting. Then, from the directory on the transfer drive that holds the `online/` folder (pass `-R` so the secrets go to the repository, not to whatever repo the current folder belongs to), run:

   ```sh
   gh secret set ONEMIND_TUF_TARGETS_KEY --env tuf-signing -R onemindos/ONEMINDOS < online/targets.key
   gh secret set ONEMIND_TUF_SNAPSHOT_KEY --env tuf-signing -R onemindos/ONEMINDOS < online/snapshot.key
   gh secret set ONEMIND_TUF_TIMESTAMP_KEY --env tuf-signing -R onemindos/ONEMINDOS < online/timestamp.key
   gh secret list --env tuf-signing -R onemindos/ONEMINDOS
   ```

   Each upload must exit zero. The list shows names and timestamps. If an upload fails, verify the repository and environment, retry the failed upload, and confirm all three names.
   **Then delete and wipe.** Only after all three names are listed: securely delete `online/*.key` (`shred -u online/*.key`) on this online computer and on the transfer drive, then wipe the transfer drive as a whole (for example `cryptsetup luksErase` on the device, then re-create or `shred`/overwrite it; for flash media treat the wipe as best effort and discard the drive if in doubt). Do not clean up before the list is confirmed.
3. **Gate: wait for main before the dry run.** The dry run (step 4 below) uses the `installer` job of `security-nightly.yml`, which [#1320](https://github.com/onemindos/ONEMINDOS/pull/1320) adds. Do not continue until both the reviewed root PR and the installer job are on `main`. Check: `gh api 'repos/onemindos/ONEMINDOS/contents/.github/workflows/security-nightly.yml?ref=main' -H 'Accept: application/vnd.github.raw' | grep -n '^  installer:'` prints a line. This gate comes after the secrets step on purpose: the environment and secrets do not need the installer job, so the online keys leave the transfer drive (it is wiped) before you wait for `main`; only the dry run needs `main`.
4. **Rehearse the installer in CI before enabling publication.** From the online checkout, run:

   ```sh
   gh workflow run security-nightly.yml --ref main -R onemindos/ONEMINDOS -f force_rebuild=true -f dry_run=true
   gh run list --workflow security-nightly.yml --branch main --event workflow_dispatch --limit 5 -R onemindos/ONEMINDOS
   gh run watch "$RUN_ID" --exit-status -R onemindos/ONEMINDOS
   ```

   Set `RUN_ID` to the new dispatch in the list. The summary must show `publish=false` and `dry_run=true`. The installer job selects `mode=dev`, rehearses the release image with a throwaway public CA, and logs `ok: ... image trusts the bundle's CA, RAUC accepts the bundle with it, same packages as the signed build`. Verify I1–I5 passed and that the artifact is `installer-security-x86_64-dev`. If a job fails or is skipped, inspect it with `gh run view "$RUN_ID" --log-failed -R onemindos/ONEMINDOS` and resolve the cause before publishing.
5. **BLOCKED until a RAUC signing key procedure exists (see [KEYS.md](KEYS.md), "Decision 1: where the RAUC CA lives", RAUC CA options A, B and C).** The repository has no procedure that makes the RAUC release signing key, signer certificate or CA, and this runbook does not invent one. RAUC is the separate bundle signer. The current `build` job reads repository-accessible `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT` and optional `ONEMIND_RAUC_KEYRING_CERT`; the `decide` job checks the first two for presence. Do not proceed to steps 6 and 7 until Zeus has chosen an option and a reviewed procedure is in the repo. **Open follow-up:** those RAUC signing secrets are repository-wide, not scoped to the `tuf-signing` environment, so any workflow on any branch that can read repository secrets could read the signing key. Scoping them to an environment is not designed yet; see [installer workflow and RAUC follow-up](../boards/installer-x86_64/UPDATES.md). Keep the three TUF secrets scoped to `tuf-signing`. Once a CA exists, record its SHA-256 on the checklist with `openssl x509 -in "$RAUC_CA" -noout -fingerprint -sha256`.
6. **Build the production stick. BLOCKED, as step 5.** Once ready to publish, set repository variable `ONEMIND_SECURITY_PUBLISH=true`. Repeat the workflow commands above with `-f dry_run=false` and the new run ID. Expect `publish=true (keys=true committed_root=true switch=true dry_run=false)`, a build log that reports `dry_run=false`, TUF client verification, installer mode `release`, the same keyring/package check, and I1–I5 passing. If any check fails, stop before flashing. Use the workflow logs to resolve the failed gate and check for an already published release before retrying.
7. **Verify the artifact and installed trust. BLOCKED, as step 5.** Verify `gh release view "os-security-$VERSION" -R onemindos/ONEMINDOS` succeeds for the version printed by the run. Download its same-run installer with `gh run download "$RUN_ID" -R onemindos/ONEMINDOS -n installer-security-x86_64-release -D installer-release`. In the artifact's installer directory, read `README.txt` (must say `RELEASE-keyed` for that version), decompress the `.img.xz` with `xz -dk`, and run `sha256sum -c SHA256SUMS` on Linux. Expect `OK` for the image. Compare `openssl x509 -in release-ca.cert.pem -noout -fingerprint -sha256` with the recorded CA. On any mismatch, stop and recheck the run, release tag and artifact. Use the [installer instructions](../boards/installer-x86_64/README.md) on the intended Dell disk. After install, compare `sha256sum /usr/lib/onemind/tuf/security/root.json` and `openssl x509 -in /etc/rauc/keyring.pem -noout -fingerprint -sha256` with the paper record before applying a later update.
8. **First signed update, then rollback. BLOCKED, as step 5** (it needs the release stick from step 6). With the box installed from the release stick, the first real signed update is applied and then rolled back, the test the D-031 decision ties to Step 5. The tampered, wrong-key and older-update refusals are covered with throwaway keys in [#1188](https://github.com/onemindos/ONEMINDOS/pull/1188); the runbook for that is [#1178](https://github.com/onemindos/ONEMINDOS/pull/1178) and must be reconciled with the installer workflow above.

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
| 1 extra stick, the "transfer stick" | File-key procedure: carries only **public** files in and out, never a root private key. In the YubiKey ceremony it is the LUKS-encrypted transfer drive, which also carries the three **online** private keys for the GitHub step and is wiped after |
| 1 offline computer | Best: a laptop booted from a Debian live USB (it forgets everything at shutdown). A Mac with networking off also works |
| 3 people | You, the other two holders, ideally all three in one room. Only 2 sign, but all 3 sticks are made |
| Paper and a printer | To print the sheet from step 7 and the checklist |
| This repo at a commit you have reviewed | Write the commit hash on the checklist |

**Easiest way:** `python3 scripts/ceremony-guide.py` walks you through all of this below step by step on the offline machine (`--rehearsal` first, with throwaway keys). The manual steps stay the source of truth.

**Using YubiKeys from the first day instead of sticks:** see [Ceremony on YubiKeys](#ceremony-on-yubikeys-d-031) below (`python3 scripts/ceremony-guide.py --yubikey --rehearsal`, rehearsal only). The **real run follows the [Rehearsal checklist](#rehearsal-checklist)**, not the guide: the guide's real-run text still points to a section that no longer exists and describes a plain transfer stick (no LUKS drive, copy list or `shred`). D-031 (2026-11-25): the first ceremony runs on the founder's three YubiKeys, with a rehearsal on one real key first.

## Before the day: rehearse (step 0)

On the offline machine (or any Linux machine or container with networking off), once:

```sh
python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt   # needs a network: do it BEFORE going offline
PYTHON=V/bin/python scripts/tuf-bootstrap-root.sh rehearse /tmp/rehearsal-1
```

You should see `REHEARSAL PASSED`. **The rehearsal is the go/no-go:** the unit tests in `os/update/tests/test_tuf_ceremony.py` skip silently on a machine without python-tuf, so a green test run alone proves nothing there. If `REHEARSAL PASSED` does not appear on the ceremony machine, do not start. It does the whole ceremony on throwaway keys: three root keys, 2-of-3 signing with one holder absent, online keys, the final check and a signed test release checked as a box would. Delete `/tmp/rehearsal-1` afterwards. The command refuses an existing directory and refuses to run in CI.

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
   - Put the three online private keys into the GitHub **Environment** `tuf-signing` (D-010). First create it: repository **Settings → Environments → New environment → `tuf-signing`**, then *Deployment branches and tags* → *Selected branches and tags* → add `main` only. Leave *Required reviewers* off (a reviewer would stop the nightly and the 6-hourly re-sign). Then set the three secrets **in that environment**:
     ```sh
     gh secret set ONEMIND_TUF_TARGETS_KEY   --env tuf-signing -R onemindos/ONEMINDOS < online/targets.key
     gh secret set ONEMIND_TUF_SNAPSHOT_KEY  --env tuf-signing -R onemindos/ONEMINDOS < online/snapshot.key
     gh secret set ONEMIND_TUF_TIMESTAMP_KEY --env tuf-signing -R onemindos/ONEMINDOS < online/timestamp.key
     ```
     Carry the three online `.key` files (never a root key) on the LUKS-encrypted transfer drive only for this step, then `shred -u` them and wipe the drive. Only the jobs `decide`, `tuf` and `timestamp` of `security-nightly.yml` declare `environment: tuf-signing`, and `test/unit/test_tuf_secrets.py` fails if any other job or workflow reads these keys. Because `main` is the only branch allowed, a manual dispatch from another branch stops at `decide`: run dry runs on `main`. Do **not** also set them as repository secrets.
   - Signed releases need more than the TUF keys: `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT` and the variable `ONEMIND_SECURITY_PUBLISH=true` ([README](README.md)). Those are not made here.
10. **Wipe the online machine.** Shut the live USB down (it forgets), or securely delete `online/` and `out/`. The root `.key` files exist only on the three sticks. Wipe the transfer stick.
11. **Store the sticks** in three places, one each: home, off-site, a trusted person. The succession note (who may act if you cannot, and where the sticks and passphrases are) goes in a **sealed envelope, never in the repo**.
12. **Calendar the renewal.** The root **expires after 365 days** ([channel.json](channel.json)), and a box refuses an expired root, so put a reminder 90 days before. The nightly (`root-expiry` job in `security-nightly.yml`) also goes red 60 days before expiry. Renewal is done as described in **Renewing the root** below (same keys), or as a rotation onto hardware keys ([below](#rotate-the-root-onto-hardware-keys-rel-02-272); the same command with the same keys as old and new also renews).

## Ceremony on YubiKeys (D-031)

**This is the same procedure as the [Rehearsal checklist](#rehearsal-checklist) at the top of this file.** There is one YubiKey procedure, that checklist; this heading stays so that links to `#ceremony-on-yubikeys-d-031` keep working. The printable version is [CEREMONY-CHECKLIST.md](CEREMONY-CHECKLIST.md).

**What is different from the file-key ceremony.** Each of the three root keys is made **inside its own YubiKey** and never exists anywhere else. There are no root key files and no root-key passphrases: a key is used with the YubiKey plugged in, its **PIN** typed, and a **touch** on the device. The 2-of-3 rule, the online keys, `root.json`, the check, the sheet and the GitHub step do not change.

**Decision (D-031, 2026-11-25).** The first ceremony runs on the founder's three YubiKeys, with a rehearsal on one real key first. Zeus is the **sole key holder** (founder call, 2026-11-27): three YubiKeys in three different places, no second person, a PIN never stored with its YubiKey. D-010's sealed succession note still applies. No rotation is needed later; the 2-of-3 rule is the backup. One lost YubiKey changes nothing by itself; two lost means a new root and a re-flash of every box. The other release keys (RAUC CA, Secure Boot PK/KEK) are in [KEYS.md](KEYS.md).

### More words
- **YubiKey PIV:** the smart-card part of a YubiKey 5. Its slot `9c` ("digital signature") holds the root key. PKCS#11 key id `2`.
- **PIN** (6 to 8 digits), **PUK** (unblocks the PIN) and **management key** (protects changes to the device; `--protect` stores a random one behind the PIN): defaults and lock-out rules are in the checklist.
- **PIN policy "always":** the device wants the PIN for every signature; the tool asks once per key per run. **Touch policy "always":** every signature waits for a finger on the device, so malware cannot sign by itself even while it holds the PIN.
- **Attestation:** a certificate the YubiKey signs about its own key ("generated here, with this PIN and touch policy"), chained to Yubico's PIV CA. An imported key gets none. `YUBICO_PIV_CA` is required; `yubikey-key` refuses without it, except for a spare trial with `ONEMIND_ATTEST_WITHOUT_CA=spare-trial` (key named `spare`; it writes `spare-NO-CA-RECORD.txt` and does not count as a pass). On a failed attestation no `<name>.pub` is written and the files move to `<name>-attestation-FAILED/`; do not use that YubiKey.
- **ykman:** Yubico's command-line tool. **libykcs11:** Yubico's PKCS#11 module.

### Not verified yet (needs the spare YubiKey)
- Every `ykman` command, the module path and package names, and that libykcs11 reports slot 9c's PIN-always key the way SoftHSM does.
- The attestation chain to Yubico's current CA (firmware 5.7 and later may use a newer CA; if the check says the chain does not end at the CA, stop and ask).
- The touch prompt while two YubiKeys sign in one command.

**Renewal** is the same `renew` command with two token references: `renew current/root.json out-renewed 'hsm:2?yubikey=<serial 1>' 'hsm:2?yubikey=<serial 2>'`.

## Renewing the root
A root lives 365 days. If it expires, every box refuses every update, security fixes included, and a box cannot fetch a new root by itself without one signed by keys it already trusts. So the root is renewed **before** it expires, offline, by the same 2-of-3 holders. Renewal makes root **version N+1** with the **same keys and thresholds** and a new expiry. It is not a key rotation (no key changes), so a box needs nothing but the new file: it walks `1.root.json`, `2.root.json`, … and accepts each one signed by the threshold of the keys the previous one trusted (TUF's root rotation rule, [CHANNEL.md §2](CHANNEL.md)).

**When.** The nightly fails with `::error:: … expires in 60 days` from 60 days before expiry. Do it in the 30 days after that, not on the last day: holders travel.

**Practise first** (any time, on any machine; it uses throwaway keys and takes a few seconds):
```sh
scripts/tuf-bootstrap-root.sh rehearse-renewal /tmp/renewal-rehearsal   # a new, empty path
```
It runs the whole ceremony, then a renewal signed by holders B and C (A absent), checks that **one holder alone is refused**, and checks that a client which trusts only version 1 follows the chain to version 2.

**For real** (air-gapped machine, two holders present, as in the ceremony; the printed sheet is [CEREMONY-CHECKLIST.md](CEREMONY-CHECKLIST.md) part B):
1. Boot the offline machine, mount the two sticks, and copy the **current** committed `root.json` of the channel onto it.
2. Run (it asks each holder for their passphrase, and refuses if fewer than the threshold sign, if a key is not a root key of the current root, or in CI):
   ```sh
   scripts/tuf-bootstrap-root.sh renew current/root.json out-renewed <stick-1>/root.key <stick-2>/root.key
   ```
   It checks that a box holding version N accepts the result, then prints the sheet (version, sha256, key ids, expiry).
3. **Read the sheet aloud.** The key ids must be the **same** as in the old root, `version` one higher, about 365 days left, and two valid signatures. The holders sign the printout.
4. Carry only `out-renewed/root.json` and `out-renewed/<N+1>.root.json` out on the transfer stick. Commit `root.json` as `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json` in a PR (the gate reviews it). The next nightly publish copies `<N+1>.root.json` next to the older roots on the channel (the build keeps every numbered root), and new images carry the new `root.json`.
5. Wipe the offline machine and the transfer stick; set the next reminder.

**Order matters:** publish the renewed root on the channel (the next nightly after the PR merges) **before** the old one expires, and keep every older `<N>.root.json` on the channel: a box that was off for months needs the whole chain. Test it once the PR is in: on a spare box or VM image built before the renewal, update; it must reach the new root without help.

## Rotate the root onto hardware keys (REL-02, #272)

> **Not for the D-031 ceremony. Only for rotating an existing file-key root onto hardware later; a D-031 root is already on YubiKeys.** This section uses a plain `ykman`/`pkcs11-tool` key generation (no PIN or touch policy, no attestation) and `hsm:2?label=` references. Do not use it for the YubiKey ceremony; follow the [Rehearsal checklist](#rehearsal-checklist).

**What this is.** Today (after the ceremony above) the three root keys are files on three encrypted sticks. This moves the root onto **hardware keys**: three small devices, each holding one root key that **can never be copied out of the device**. Stealing the stick's file or its passphrase is no longer enough; the thief needs the device **and** its PIN. It is a **root rotation**: a new `root.json` (version 2) with a new set of root keys. Boxes that ship the version-1 root follow it by themselves, because TUF requires version 2 to be signed by **2 of the 3 OLD keys and 2 of the 3 NEW keys** (spec 5.3.4). If either group is short, a box refuses the new root, and `rotate-root` refuses to write it. The same command also **renews an expiring root** (use the same keys as old and new).

**You run this, never an agent.** Offline machine, your own hands, like the ceremony. The rehearsal below is the only part an agent runs, on throwaway keys.

### More words

- **Hardware token:** a small device (a YubiKey, a smart card) that makes and keeps a private key inside itself and signs for you on request. The key never leaves it.
- **PKCS#11:** the standard plug a program uses to talk to such a device. Each device type comes with a **module** (a `.so` or `.dylib` file) that implements it; `PYKCS11LIB` names that file.
- **PIV:** the smart-card feature of a YubiKey. It has numbered **slots**; slot `9c` is "digital signature", PKCS#11 key id `2`, and is what the tool uses by default.
- **PIN:** the short code that unlocks the device for signing. **Three wrong PINs lock a YubiKey**, so type slowly. It is typed at a prompt that shows nothing; it is never part of a command (a command is saved in your shell history).
- **ECDSA P-256:** the signature type the token keys use. (The sticks use ed25519, which PKCS#11 devices do not reliably support.) Box code handles both; this was checked with the box's own verifier.
- **Threshold:** how many of a role's keys must sign. Root: 2 (of 3), before and after.
- **Rotation:** replacing the keys a root trusts, with the old keys vouching for the new ones.

### What you need

| Item | Notes |
|---|---|
| 3 hardware tokens, one per holder | YubiKey 5 (PIV) or any PKCS#11 token that does ECDSA P-256. A fresh PIN set on each |
| The PKCS#11 module for the token | YubiKey: `libykcs11.so` (Linux, package `ykcs11` / `yubico-piv-tool`) or `libykcs11.dylib` (Mac, `brew install yubico-piv-tool`). Note its full path |
| 2 of the 3 old sticks, with their passphrases | The two holders who sign for the old root |
| The current root | The committed `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json`, copied onto the offline machine |
| The offline machine of the ceremony | Same rules: no network. `opensc` (`pkcs11-tool`) or `ykman` installed beforehand |

### 0. Rehearse (an agent or you, any machine)

```sh
PYTHON=V/bin/python scripts/tuf-bootstrap-root.sh rehearse-rotate /tmp/rotate-rehearsal-1
```
You should see `REHEARSAL PASSED: v1 -> v2 rotation signed by 2 old + 2 new keys, followed by a client that trusts only v1.` It uses throwaway file keys; the token path is tested in CI with SoftHSM (a software token) in `os/update/tests/test_tuf_hsm.py`. Delete the directory afterwards.

### The rotation

Use `--` and quotes as written: a token key is named `'hsm:2?label=<token label>'` (key id 2, the device's label), and the quotes stop the shell treating `?`.

1. **Make each hardware key ON its device, one holder at a time.** The private key is generated inside the device and is marked "never extractable".
   - Any PKCS#11 token (tested on SoftHSM): `pkcs11-tool --module <module path> --login --keypairgen --key-type EC:prime256v1 --id 02 --label onemind-root` (it asks for the PIN). Add `--token-label <label>` if several tokens are plugged in. The output must say `never extractable` for the private key.
   - YubiKey (PIV slot 9c): `ykman piv keys generate --algorithm ECCP256 9c <holder>-yk.pub`, then `ykman piv certificates generate --subject "OneMind root" 9c <holder>-yk.pub` (some versions of the PKCS#11 module only list a key that has a certificate). **UNVERIFIED on real hardware**: do this on a spare YubiKey first and check step 2 works before touching the real three.
2. **Export each public key.** The holder hands over the public part only:
   ```sh
   export PYKCS11LIB=<module path>
   scripts/tuf-bootstrap-root.sh token-pub 'hsm:2?label=<token label>' pubs/new-a.pub    # holder A's device plugged in
   scripts/tuf-bootstrap-root.sh token-pub 'hsm:2?label=<token label>' pubs/new-b.pub    # holder B
   scripts/tuf-bootstrap-root.sh token-pub 'hsm:2?label=<token label>' pubs/new-c.pub    # holder C
   ```
   It prints the key id. Each holder reads their key id aloud so the three `.pub` files are known to match the three devices. Nothing secret is exported.
3. **Rotate.** Two old holders and two token holders sign (C's device stays unplugged, its public key is trusted):
   ```sh
   scripts/tuf-bootstrap-root.sh rotate-root <current root.json> rotated security 2 \
     <stick-a>/root.key <stick-b>/root.key -- \
     'hsm:2?label=<token A label>' 'hsm:2?label=<token B label>' pubs/new-c.pub
   ```
   Arguments: the current root, an **empty** output directory, the channel, the new threshold (2), the two old private keys, `--`, then the new keys: a token reference **signs**, a `.pub` is only trusted. You type each stick's passphrase and each token's PIN at its own prompt, once. If fewer than 2 old keys or fewer than 2 new keys are given, nothing is written. A second run into the same directory is refused.
4. **Check it.** Name the old root too, so the check proves the old keys signed it:
   ```sh
   scripts/tuf-bootstrap-root.sh check rotated 2 3 <current root.json>
   ```
   All must be true: `root.json version 2`, `root threshold 2 of 3`, three different root key ids (the key ids of step 2), targets/snapshot/timestamp unchanged, `root signatures on file: 4`, and **`previous root v1: 2 of its keys signed this root too`**. All holders read the `sha256` line aloud and write it on the checklist. Any `FAIL`: stop and do not use these files.
5. **Publish (online computer, you).** Carry only `rotated/root.json` (and `rotated/2.root.json`, the same file) out on the transfer stick; check the sha256.
   - Commit `rotated/root.json` as `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json` in a PR. New images ship version 2 from then on.
   - The next release build writes `2.root.json` into the channel next to `1.root.json` (the build copies the committed root in as `<version>.root.json`, and the publish step uploads `[0-9]*.root.json`). **Boxes already out there trust only version 1** and walk to version 2 on their next check; keep the old files served.
6. **Keep or destroy the old sticks.** After at least one release has reached the boxes, the old sticks no longer matter for trust. Do not destroy them until a box that ships version 1 has been seen to update. Store the three devices as in step 11 above (three places), the PIN of each only in its holder's head or password manager.

If a device is lost, the other two still sign (2 of 3). Replacing the third key is the same command again: the two remaining **token** keys are the old keys, a newly made token key (or `.pub`) joins the new set.

### What this does not cover

- **Real hardware.** Everything here was exercised with SoftHSM, a software token that speaks the same PKCS#11 as a YubiKey. The `ykman` commands and the YubiKey module name have not been run or checked by an agent: the spare-device trial in step 1 is how you find out.
- **Touch or PIN policies:** a key whose PIN policy is "always" (slot 9c's default) is logged in again for every signature (tested with SoftHSM keys that ask for it, `os/update/tests/test_tuf_token_ceremony.py`). A touch policy makes the device wait for a touch while the tool waits; not tested on a real device.
- **The online keys** (`targets`, `snapshot`, `timestamp`) stay as they are unless you pass `--targets-pub` and friends to `tuf-repo.py rotate-root` directly; the channel metadata must then be rebuilt by hand.

## If something goes wrong

| Symptom | What it means | What to do |
|---|---|---|
| `refusing: a TUF root is made offline, never in CI` | A `CI` or `GITHUB_ACTIONS` variable is set | Run it in a normal terminal, not in a workflow |
| `WARNING: this machine has a default route` | The machine can still reach a network | Stop. Unplug and switch off networking, then start again |
| `wrong passphrase` | That holder mistyped | Retype. Three failures: check the stick is the right one |
| `refusing to overwrite a key` / `already holds a root.json` | The folder already has a key or a root | Use a **new** folder. Never delete a real root.json to retry: ask the gate |
| `need at least 2 distinct root keys, 2 of them to sign` | Fewer than 2 private keys were given | Two holders must be present and sign |
| `check` prints a `FAIL` line | The root is not the shape D-010 requires | Do not use it. Delete the output folder and redo step 6 |
| A holder loses a stick or its passphrase | One of three is gone; 2-of-3 still works for signing | Nothing breaks today. Renewing the root keeps the same keys; replacing a lost key is a key rotation (`rotate-root`, see [below](#rotate-the-root-onto-hardware-keys-rel-02-272)): the 2 remaining holders sign |

## Rehearsal record

First run by **Claude builder 2** on 2026-11-15, throwaway keys only, in a Linux container (`python:3.13-slim-trixie`, pinned dependencies from `requirements-tuf.txt`) with **networking off** (`--network none`), the stand-in for an air-gapped VM:

- `scripts/tuf-bootstrap-root.sh rehearse` completed: three encrypted root keys, a 2-of-3 root signed by two of them with the third trusted by its public key only, `inspect` clean (threshold 2 of 3, 365 days), a test release signed with the online keys and `tuf verify: 3 target(s) checked, 0 problem(s)`.
- The same steps run for real (`root-key` ×3, `online-keys`, `create` with a `.pub` for the absent holder, `check`) are in `os/update/tests/test_tuf_ceremony.py` and run in CI on every change to `os/update/`.

**Gaps the rehearsal found, now fixed:** the old `rehearse` made one root key at threshold 1 (not the real shape) and never verified the result; root keys could not be passphrase-protected, so D-010's encrypted sticks could not be used; `create` could not take an absent holder's public key; nothing prevented a second `create` from overwriting a root; the old header pointed to a `handbook/keys/CEREMONY.md` that did not exist.

**Not covered by the rehearsal (needs people and hardware):** typing real passphrases at the terminal (the rehearsal reads a throwaway one from the environment), encrypting real sticks, the order of who reads what aloud, and the GitHub secret step. The checklist covers them.
