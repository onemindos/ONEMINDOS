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

**Easiest way:** `python3 scripts/ceremony-guide.py` walks you through all of this below step by step on the offline machine (`--rehearsal` first, with throwaway keys). The manual steps stay the source of truth.

**Using YubiKeys from the first day instead of sticks:** see [Ceremony on YubiKeys](#ceremony-on-yubikeys-proposed-changes-d-010) below (`python3 scripts/ceremony-guide.py --yubikey`). It is ready to rehearse, but D-010 still says sticks first, so it needs the founder's decision entry before a real root is made that way.

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
     gh secret set ONEMIND_TUF_TARGETS_KEY   --env tuf-signing < online/targets.key
     gh secret set ONEMIND_TUF_SNAPSHOT_KEY  --env tuf-signing < online/snapshot.key
     gh secret set ONEMIND_TUF_TIMESTAMP_KEY --env tuf-signing < online/timestamp.key
     ```
     Carry the three `.key` files on the **transfer stick only for this step**, then wipe it. Only the jobs `decide`, `tuf` and `timestamp` of `security-nightly.yml` declare `environment: tuf-signing`, and `test/unit/test_tuf_secrets.py` fails if any other job or workflow reads these keys. Because `main` is the only branch allowed, a manual dispatch from another branch stops at `decide`: run dry runs on `main`. Do **not** also set them as repository secrets.
   - Signed releases need more than the TUF keys: `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT` and the variable `ONEMIND_SECURITY_PUBLISH=true` ([README](README.md)). Those are not made here.
10. **Wipe the online machine.** Shut the live USB down (it forgets), or securely delete `online/` and `out/`. The root `.key` files exist only on the three sticks. Wipe the transfer stick.
11. **Store the sticks** in three places, one each: home, off-site, a trusted person. The succession note (who may act if you cannot, and where the sticks and passphrases are) goes in a **sealed envelope, never in the repo**.
12. **Calendar the renewal.** The root **expires after 365 days** ([channel.json](channel.json)), and a box refuses an expired root, so put a reminder 90 days before. The nightly (`root-expiry` job in `security-nightly.yml`) also goes red 60 days before expiry. Renewal is done as described in **Renewing the root** below (same keys), or as a rotation onto hardware keys ([below](#rotate-the-root-onto-hardware-keys-rel-02-272); the same command with the same keys as old and new also renews).

## Ceremony on YubiKeys (proposed; changes D-010)

**What this is.** The same ceremony, with one difference: each holder's root key is made **inside their own YubiKey** and never exists anywhere else. There are no root key files and no passphrases: a key is used with the YubiKey plugged in, its **PIN** typed, and a **touch** on the device. The 2-of-3 rule, the online keys, `root.json`, the check, the sheet and the GitHub step do not change.

**Decision needed (flag for the founder).** D-010 (2026-11-14) says: key files on encrypted sticks now, a rotation onto hardware keys later (#272). Using YubiKeys for the **first** ceremony changes that, so it needs a new decision entry from Zeus. What changes if he says yes:
- No rotation is needed later, and the "rotation drill" D-010 counted on is replaced by the renewal rehearsal (same keys, `renew`).
- Nothing to back up, nothing to copy: the 2-of-3 rule is the backup. One lost YubiKey changes nothing by itself; two lost means a new root and a re-flash of every box, exactly as with two lost sticks.
- The ceremony steps marked UNVERIFIED below have to work on a **spare** YubiKey first.
- The other release keys (RAUC CA, Secure Boot PK/KEK) and the choices for them are in [KEYS.md](KEYS.md).

**Why it is safer.** A stick holds a key file; a copy of the file plus the passphrase is a copy of the key, and nobody can prove it was never copied. A YubiKey key is made on the device and the device refuses to export it. The device can even sign a statement saying so (its **attestation**, checked below).

### More words
- **YubiKey PIV:** the smart-card part of a YubiKey 5. Its slot `9c` ("digital signature") holds the root key. PKCS#11 key id `2`.
- **PIN** (6 to 8 digits): unlocks the key. Three wrong tries lock it; the **PUK** unlocks the PIN; three wrong PUKs make the PIV part unusable until it is reset (which erases the key). Default PIN `123456`, PUK `12345678` (Yubico, "PIV PIN and Management Key"): change both before the day.
- **Management key:** a third secret that protects *changes* to the YubiKey (making a key). `--protect` stores a random one on the device behind the PIN, so the holder only ever types the PIN.
- **PIN policy "always":** the device wants the PIN for every signature (slot 9c's default). The holder types it **once per key** at the tool's prompt; the tool hands it to the device again before each signature it makes in that run. **Touch policy "always":** every signature waits for a finger on the device, so malware on the computer cannot sign by itself even while it holds the PIN. The touch is the per-signature human check.
- **Attestation:** a certificate the YubiKey signs about its own key: "this public key was generated here, with this PIN and touch policy". It chains to Yubico's PIV CA. An imported key gets none.
- **ykman:** Yubico's command-line tool (YubiKey Manager). **libykcs11:** Yubico's PKCS#11 module, which lets the signing tool use the key.

### What you need (in addition to the table above; no root sticks)
| Item | Notes |
|---|---|
| 3 YubiKeys, one per holder | YubiKey 5 series (PIV, firmware 5.x). Plus **1 spare** for the trial |
| ykman and libykcs11 on the offline machine | Debian: `apt-get install yubikey-manager ykcs11` (or `yubico-piv-tool`); Mac: `brew install ykman yubico-piv-tool`. Note the module path (Debian: `/usr/lib/x86_64-linux-gnu/libykcs11.so`; Mac: `$(brew --prefix)/lib/libykcs11.dylib`). UNVERIFIED package names: check with `apt-cache policy` / `brew info` while online |
| Yubico's PIV attestation CA | Download while online (developers.yubico.com, "PIV attestation"), write its sha256 on the checklist, carry it over. Set `YUBICO_PIV_CA=<file>` at the table. UNVERIFIED: firmware 5.7 and later may use a newer CA; if the check says the chain does not end at the CA, stop and ask |
| 1 transfer stick | Only `root.json` and, for the GitHub step, the online keys (as above) |

### The day before: prepare each YubiKey (each holder, alone)
UNVERIFIED on real hardware: do all of this on the **spare** first, then the full rehearsal below on the spare.
```sh
ykman list --serials                                   # note your YubiKey's serial (also printed on it)
ykman --device <serial> piv reset                      # ONLY a new or spare YubiKey: erases its PIV part
ykman --device <serial> piv access change-pin          # old PIN 123456, then your own (6-8 digits), twice
ykman --device <serial> piv access change-puk          # old PUK 12345678, then your own, twice
ykman --device <serial> piv access change-management-key --generate --protect   # asks your PIN
ykman --device <serial> piv info                       # slot 9c must be empty
```
Never type a PIN, PUK or management key as part of a command (it would stay in the shell history): let ykman prompt.

### Rehearse (any machine, any time)
```sh
PYTHON=V/bin/python scripts/tuf-bootstrap-root.sh rehearse-tokens /tmp/token-rehearsal-1   # needs softhsm2
PYTHON=V/bin/python python3 scripts/ceremony-guide.py --yubikey --rehearsal               # the guided walk
```
Both end with `REHEARSAL PASSED`. They use **SoftHSM**, a software token that speaks the same PKCS#11 as a YubiKey, with PIN-every-signature keys like slot 9c. The two differences from the real day, and the only ones: the token (software instead of a YubiKey), and how each key is made (`token-keygen` instead of `ykman`, so there is no touch and no attestation). Every later command (`token-pub`, `create`, `check`, `renew`) is the same code. CI runs both on every change to `os/update/` (`os/update/tests/test_tuf_token_ceremony.py`), plus the box's own verifier on a channel whose first root is held by tokens.

**On the spare YubiKey** (the go/no-go for the real day): prepare it as above, then
```sh
export PYKCS11LIB=<module path> YUBICO_PIV_CA=<downloaded CA file>
scripts/tuf-bootstrap-root.sh yubikey-key /tmp/spare-trial spare
```
It must end with `attestation OK` and print `PIN policy always, touch policy always`. Then reset the spare (`ykman --device <serial> piv reset`). If this fails, stop: the real three are not touched until the spare works.

`YUBICO_PIV_CA` is required. Without Yubico's CA the attestation proves nothing: any software can make a certificate that looks like the device's f9 certificate for a key that was imported, not made on the YubiKey. The script refuses to start without it. Only this spare trial may run without the CA (for example, to try ykman before the CA is downloaded): name the key `spare` and set `ONEMIND_ATTEST_WITHOUT_CA=spare-trial`. The script then writes `spare-NO-CA-RECORD.txt` (date, serial) and prints `attestation OK WITHOUT Yubico's CA (spare trial only)`. That does not count as Y1: run the trial again with the CA before the real day. The guide refuses the bypass.

If an attestation fails, the script writes **no** `<name>.pub` (the public key stays under a temporary name until the check passes, then is renamed) and moves the attestation files to `<name>-attestation-FAILED/`. Do not use that YubiKey for a root key. The attestation must also name the YubiKey serial the script was pointed at.

### The ceremony with YubiKeys
`python3 scripts/ceremony-guide.py --yubikey` walks all of it. By hand:
1. Steps 1 and 2 of the ceremony above (network off, commit checked). `export PYKCS11LIB=<module path> YUBICO_PIV_CA=<CA file>`.
2. **Each holder makes their key on their YubiKey**, one at a time, with only their own YubiKey plugged in:
   ```sh
   scripts/tuf-bootstrap-root.sh yubikey-key pubs a      # holder A; then pubs b (holder B), pubs c (holder C)
   ```
   ykman asks for the PIN (the management key is PIN-protected), the key blinks: touch it. The script refuses if slot 9c already holds a key. It refuses without `YUBICO_PIV_CA`. It prints the device serial (checked against the YubiKey it was pointed at), `attestation OK` and both policies, and only then writes `pubs/a.pub` (public) beside the attestation files. Write each serial on the checklist.
3. **Online keys:** step 5 above (`online-keys online`).
4. **Sign the root.** The two signers plug in their YubiKeys **together**; the third stays away:
   ```sh
   scripts/tuf-bootstrap-root.sh create out security 2 'hsm:2?yubikey=<serial A>' 'hsm:2?yubikey=<serial B>' pubs/c.pub -- \
     online/targets.pub online/snapshot.pub online/timestamp.pub
   ```
   Each signer types their PIN at their own prompt and touches their YubiKey when it blinks. Quotes as written (the `?`).
5. **Check and read aloud:** step 7 above, unchanged (`check out 2 3`). The root key ids are the ones the three `yubikey-key` runs printed.
6. Steps 8 to 12 above, unchanged, except: there are no root sticks to store; each holder stores their **YubiKey** (home, off-site, trusted person), and their PIN and PUK go in their own password manager or sealed envelope, never in the repo.

**Renewal** is the same `renew` command with two token references: `renew current/root.json out-renewed 'hsm:2?yubikey=<serial 1>' 'hsm:2?yubikey=<serial 2>'`.

### Not verified yet (needs the spare YubiKey)
- Every `ykman` command above, the module path and package names, and that libykcs11 reports slot 9c's PIN-always key the way SoftHSM does (the signer logs in again for each signature when the key asks for it; SoftHSM proves that path, a YubiKey has not yet).
- The attestation chain to Yubico's current CA (the checker is tested on synthetic certificates in Yubico's documented layout).
- The touch prompt while two YubiKeys sign in one command.

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
