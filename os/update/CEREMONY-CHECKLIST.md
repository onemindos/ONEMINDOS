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
- [ ] 10. GitHub Environment `tuf-signing` created (Settings → Environments), deployment branches: `main` only, **no** required reviewer. Secrets set **in that environment** with `gh secret set <NAME> --env tuf-signing < online/<role>.key`: `ONEMIND_TUF_TARGETS_KEY`, `ONEMIND_TUF_SNAPSHOT_KEY`, `ONEMIND_TUF_TIMESTAMP_KEY`. Only these three, never the root keys, never as repository secrets
- [ ] 11. Ceremony machine shut down (live USB) or `online/` and `out/` securely deleted; transfer stick wiped

## After
- [ ] 12. Sticks stored in 3 places: home ____________ · off-site ____________ · trusted person ____________
- [ ] 13. Succession note sealed in an envelope (never in the repo); location: ____________
- [ ] 14. Calendar reminder 60 days before the root expires (date: ____________, 365 days from today). Renewal tooling is a follow-up; boxes refuse an expired root
- [ ] 15. Still to do for a published release (not part of this ceremony): `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT`, `ONEMIND_SECURITY_PUBLISH=true`
- [ ] 16. Issue #153 updated with the root.json sha256 (never a key)

If any step prints `FAIL`, asks for something unexpected, or a passphrase fails three times: **stop**, change nothing, and ask.
