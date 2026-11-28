<!-- SPDX-License-Identifier: Apache-2.0 -->
# Root key ceremony: checklist (print this)

**First ceremony (D-031):** print the [Rehearsal checklist](CEREMONY.md#rehearsal-checklist). Zeus rehearses on one real spare first and is the sole holder of the three production YubiKeys, stored in three different places.

## D-010 file-key procedure (historical)

Full explanation: [CEREMONY.md](CEREMONY.md). Decision: D-010 (3 root keys, 2-of-3, encrypted sticks, offline).
**No real key is ever typed, shown or held by an agent. Root keys never touch CI.**

Date: ____________  Place: ________________  Channel(s): security / stable
Code commit (`git rev-parse HEAD`): ______________________________
Holders: A ______________  B ______________  C ______________  Witness (optional) ______________

## Before the day
- [ ] **Go/no-go:** rehearsal passed on the ceremony machine: `REHEARSAL PASSED` (the unit tests skip silently without python-tuf, so this is the proof) (`scripts/tuf-bootstrap-root.sh rehearse /tmp/rehearsal-1`), then `/tmp/rehearsal-1` deleted
- [ ] 3 USB sticks + 1 transfer stick + printer + this sheet + 3 envelopes (one for the succession note)
- [ ] Pinned tools installed (`pip install --require-hashes ... requirements-tuf.txt`) while still online

## At the table
- [ ] 1. Network off: Wi-Fi, Bluetooth, cable. The script prints **no** "default route" warning
- [ ] 2. `git rev-parse HEAD` equals the hash above; `git status` is clean
- [ ] 3. Each holder encrypted their own stick and chose their own passphrase (12+ characters)
- [ ] 4. Root keys made: `root-key` for A, B, C (each types their own passphrase twice). Public keys copied to `pubs/a.pub`, `b.pub`, `c.pub`
- [ ] 5. Online keys made: `online-keys online`
- [ ] 6. Root signed by two holders: `create out <channel> 2 <a>/root.key <b>/root.key pubs/c.pub -- online/targets.pub online/snapshot.pub online/timestamp.pub`
- [ ] 7. `check out 2 3` printed no `FAIL`. Read aloud together and compared with the screen:
  - root threshold **2 of 3**, three different key ids
  - targets, snapshot, timestamp: one key each, none the same as a root key
  - 2 valid root signatures; about 365 days left
  - **sha256 of root.json:** ____________________________________________________________
  - Signed by (initials): A ____  B ____  C ____
- [ ] 8. Only `out/root.json` copied to the transfer stick; sha256 on the online computer matches the line above
- [ ] 9. `root.json` committed in a PR as `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json`
- [ ] 10. GitHub Environment `tuf-signing` created (Settings → Environments), Deployment branches and tags → *Selected branches and tags* → `main` (verify with the two `gh api` checks in the YubiKey section), **no** required reviewer. Secrets set **in that environment** with `gh secret set <NAME> --env tuf-signing -R onemindos/ONEMINDOS < online/<role>.key`: `ONEMIND_TUF_TARGETS_KEY`, `ONEMIND_TUF_SNAPSHOT_KEY`, `ONEMIND_TUF_TIMESTAMP_KEY`. Only these three, never the root keys, never as repository secrets
- [ ] 11. Ceremony machine shut down (live USB) or `online/` and `out/` securely deleted; transfer stick wiped

## After
- [ ] 12. Sticks stored in 3 places: home ____________ · off-site ____________ · trusted person ____________
- [ ] 13. Succession note sealed in an envelope (never in the repo); location: ____________
- [ ] 14. Calendar reminder 90 days before the root expires (date: ____________, 365 days from today). The nightly also goes red 60 days before. Boxes refuse an expired root; renewal is part B below, a move onto hardware keys is the rotation section above
- [ ] 15. Still to do for a published release (not part of this ceremony): `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT`, `ONEMIND_SECURITY_PUBLISH=true`
- [ ] 16. Issue #153 updated with the root.json sha256 (never a key)

## Ceremony on YubiKeys (D-031): full steps in [CEREMONY.md](CEREMONY.md#ceremony-on-yubikeys-d-031)
Decision: D-031 (2026-11-25); sole key holder (2026-11-27). You type every PIN, PUK and passphrase yourself; no AI ever sees one; a PIN is never stored with its YubiKey. Defaults before you change them: PIN 123456, PUK 12345678 (3 wrong PINs lock it).

Date: ____________  Place: ________________
Code commit (`git rev-parse HEAD`, status clean): ______________________________
Yubico PIV CA file SHA-256 (recorded online, compared offline): ______________________________________________
- [ ] Y0. Software rehearsals passed: `rehearse-tokens` and `ceremony-guide.py --yubikey --rehearsal` printed `REHEARSAL PASSED`. Tools installed while online (`apt-get install yubikey-manager ykcs11 pcscd softhsm2`, module `/usr/lib/x86_64-linux-gnu/libykcs11.so`: both UNVERIFIED), `pip -r os/update/requirements-tuf.txt` run from the repo root. LUKS transfer drive made
- [ ] Y1. Spare YubiKey trial: reset, PIN/PUK/management key set, `yubikey-key` printed `attestation OK` (with `YUBICO_PIV_CA` set; a run without the CA does not count), `PIN policy always, touch policy always`; `create` + `check 2 3` passed with the spare; spare reset again. Spare serial: ____________
- [ ] Y2. Each production YubiKey prepared, one at a time: PIN and PUK changed, management key `--generate --protect`, slot 9c empty. PINs and PUKs stored apart from the YubiKeys (a PIN is never stored with its YubiKey), never in the repo
- [ ] Y3. Network off, commit checked (steps 1 and 2 above); `PYKCS11LIB` and `YUBICO_PIV_CA` set; the CA SHA-256 above matches
- [ ] Y4. Keys made ON each YubiKey (`yubikey-key "$W/pubs" <a|b|c> <serial>`), each printed `attestation OK`.
  - Serials (public): A ____________ B ____________ C ____________
  - Root key IDs printed: A ____________ B ____________ C ____________
- [ ] Y5. Online keys made (`online-keys "$W/online"`)
- [ ] Y6. Root signed by two YubiKeys plugged in together: `create "$W/out" <channel> 2 'hsm:2?yubikey=<A>' 'hsm:2?yubikey=<B>' "$W/pubs/c.pub" -- "$W/online/targets.pub" "$W/online/snapshot.pub" "$W/online/timestamp.pub"` (two PINs typed at prompts, two touches)
- [ ] Y7. `check "$W/out" 2 3`: no `FAIL`; threshold 2 of 3; the three key IDs match Y4.
  - **sha256 of root.json:** ______________________________________  Initials: ____
- [ ] Y8. Copied to the LUKS transfer drive before any reboot (live USB keeps `mktemp` folders in RAM): `out/root.json`, `out/1.root.json`, `pubs/*.pub` + attestation files (evidence), `online/*.key`. sha256 of `root.json` on the drive matches Y7
- [ ] Y9. `online/*.key` securely deleted (`shred -u`) on the offline machine; offline machine powered off
- [ ] Y10. Online computer: root.json sha256 matches Y7; root PR opened. `#1320`'s installer job and the root PR are on `main` before any dry run
- [ ] Y11. GitHub Environment `tuf-signing`: Deployment branches and tags → **Selected branches and tags** → `main` (not "Protected branches"). Verified: `gh api repos/onemindos/ONEMINDOS/environments/tuf-signing -q .deployment_branch_policy` shows `custom_branch_policies` true; `... /deployment-branch-policies -q '.branch_policies[].name'` prints only `main`
- [ ] Y12. Three secrets set with `gh secret set <NAME> --env tuf-signing -R onemindos/ONEMINDOS < online/<role>.key`; `gh secret list --env tuf-signing -R onemindos/ONEMINDOS` shows all three
- [ ] Y13. `online/*.key` securely deleted on the online computer and the transfer drive; the transfer drive wiped
- [ ] Y14. Dry run on `main` (`security-nightly.yml -f dry_run=true`): `publish=false`, I1 to I5 passed, artifact `installer-security-x86_64-dev`. Run ID: ____________
- [ ] Y15. **BLOCKED until a RAUC signing key procedure exists** (KEYS.md, RAUC CA options): publish run, release artifact check. RAUC CA SHA-256 fingerprint: ______________________________________________
- [ ] Y16. YubiKeys stored in three different places: ____________ · ____________ · ____________. Succession note (D-010) sealed, location: ____________
- [ ] Y17. **BLOCKED, as Y15** (needs the release stick). First signed update installed on the Dell, then rolled back ([#1178](https://github.com/onemindos/ONEMINDOS/pull/1178))

## Rotate the root onto hardware keys (REL-02, #272): full steps in [CEREMONY.md](CEREMONY.md)
**Not for the D-031 ceremony. Only for rotating an existing file-key root onto hardware later; a D-031 root is already on YubiKeys.** (Plain key generation here: no PIN/touch policy, no attestation.)

Date: ____________  Current root.json sha256 (the one being replaced): ______________________________
Needs: 3 hardware tokens (PIN set on each), their PKCS#11 module path, 2 old sticks + passphrases, `opensc` or `ykman`, offline machine.
- [ ] R0. Rehearsal passed: `scripts/tuf-bootstrap-root.sh rehearse-rotate /tmp/rotate-rehearsal-1` printed `REHEARSAL PASSED`; the YubiKey steps tried first on a **spare** device (not yet tested on hardware)
- [ ] R1. Key made ON each device (`pkcs11-tool --keypairgen --key-type EC:prime256v1 --id 02`, or `ykman piv keys generate --algorithm ECCP256 9c`); private key says `never extractable`
- [ ] R2. Public keys exported: `token-pub 'hsm:2?label=<label>' pubs/new-<x>.pub`; each holder read their key id aloud: A ____  B ____  C ____
- [ ] R3. `rotate-root <current root.json> rotated <channel> 2 <stick-a>/root.key <stick-b>/root.key -- 'hsm:2?label=<A>' 'hsm:2?label=<B>' pubs/new-c.pub` ran (2 old passphrases, 2 PINs typed; the PINs are never in a command)
- [ ] R4. `check rotated 2 3 <current root.json>`: no `FAIL`; `version 2`, `threshold 2 of 3`, `signatures on file: 4`, **`previous root v1: 2 of its keys signed this root too`**
  - **sha256 of the new root.json:** ____________________________________________________________
  - Read aloud, signed (initials): A ____  B ____  C ____
- [ ] R5. Only `rotated/root.json` (and `2.root.json`) carried out; sha256 matches; committed as `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json` in a PR
- [ ] R6. After a release: a box that ships the old root has updated. Only then are the old sticks retired. Devices stored in 3 places: ____________ / ____________ / ____________

If any step prints `FAIL`, asks for something unexpected, or a passphrase fails three times: **stop**, change nothing, and ask.

---

# Part B: renewing the root (before it expires; two holders, same rules as above)

Practise first: `scripts/tuf-bootstrap-root.sh rehearse-renewal <new empty path>` prints `REHEARSAL PASSED`. Date practised: ____________

- [ ] B1. Offline machine, networking off, live USB. Two holders present with their sticks. Current `root.json` of the channel on the machine (channel: ____________, version now: ____)
- [ ] B2. `scripts/tuf-bootstrap-root.sh renew current/root.json out-renewed <stick-1>/root.key <stick-2>/root.key` ran; each holder typed their own passphrase; no `FAIL`
- [ ] B3. Sheet read aloud by both holders: version is one higher (____), **root key ids are the same as before**, thresholds unchanged (root 2 of 3), two valid signatures, about 365 days left
  - **sha256 of the new root.json:** ____________________________________________________________
  - Signed by (initials): ____ ____
- [ ] B4. Only `root.json` and `<N+1>.root.json` copied to the transfer stick; sha256 matches on the online computer
- [ ] B5. `root.json` committed in a PR as `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json`; PR reviewed and merged
- [ ] B6. The next nightly published `<N+1>.root.json` on the channel, and all older `<N>.root.json` are still there
- [ ] B7. Spare box or old VM image updated without help and reached the new root
- [ ] B8. Offline machine and transfer stick wiped; sticks back in their 3 places; next reminder set (date: ____________)
