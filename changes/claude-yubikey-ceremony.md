---
pr: pending
branch: claude/yubikey-ceremony
---
Makes the first root key ceremony ready to run on three YubiKeys (2-of-3, PIV slot 9c, PIN and touch policy always): scripts/tuf-bootstrap-root.sh yubikey-key makes each holder's key ON the device with ykman and checks the device's attestation (os/update/piv-attest.py), rehearse-tokens runs the whole ceremony on three SoftHSM tokens with the same create/check/renew commands, ceremony-guide.py --yubikey walks it step by step, and the token signer now logs in again for each signature when a key asks for it (YubiKey slot 9c's default, which the plain signer could not sign with). CI runs the rehearsal and the box's own verifier on a token-held first root. os/update/KEYS.md maps every release key and lays out the RAUC CA and Secure Boot owner key choices. Real-YubiKey steps are marked UNVERIFIED; using YubiKeys for the first ceremony changes D-010 and needs the founder's decision entry.
