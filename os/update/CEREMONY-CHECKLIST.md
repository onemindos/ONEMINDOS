<!-- SPDX-License-Identifier: Apache-2.0 -->
# Root key ceremony: checklist (print this)

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
- [ ] 10. GitHub Environment `tuf-signing` created (Settings â†’ Environments), deployment branches: `main` only, **no** required reviewer. Secrets set **in that environment** with `gh secret set <NAME> --env tuf-signing < online/<role>.key`: `ONEMIND_TUF_TARGETS_KEY`, `ONEMIND_TUF_SNAPSHOT_KEY`, `ONEMIND_TUF_TIMESTAMP_KEY`. Only these three, never the root keys, never as repository secrets
- [ ] 11. Ceremony machine shut down (live USB) or `online/` and `out/` securely deleted; transfer stick wiped

## After
- [ ] 12. Sticks stored in 3 places: home ____________ Â· off-site ____________ Â· trusted person ____________
- [ ] 13. Succession note sealed in an envelope (never in the repo); location: ____________
- [ ] 14. Calendar reminder 60 days before the root expires (date: ____________, 365 days from today). Renewal is `rotate-root` (below); boxes refuse an expired root
- [ ] 15. Still to do for a published release (not part of this ceremony): `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT`, `ONEMIND_SECURITY_PUBLISH=true`
- [ ] 16. Issue #153 updated with the root.json sha256 (never a key)

## Rotate the root onto hardware keys (REL-02, #272): full steps in [CEREMONY.md](CEREMONY.md)
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
- [ ] R6. After a release: a box that ships the old root has updated. Only then are the old sticks retired. Devices stored in 3 places: ____________ · ____________ · ____________

If any step prints `FAIL`, asks for something unexpected, or a passphrase fails three times: **stop**, change nothing, and ask.
