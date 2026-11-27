<!-- SPDX-License-Identifier: Apache-2.0 -->
# Step 5: the key ceremony, then the first real signed update on the Dell

**One page for the day.** Goal: make OneMind's real update keys, put the trust in the Dell's image, publish one real signed update, and watch the Dell install it and go back. Every step names its command. Nothing here is done by an agent: **you (Zeus) and the two other holders run it**; agents built and rehearsed the tools.

**Words.** *TUF root*: the file every box trusts first, signed by 2 of 3 root keys. *Online keys*: the three keys the nightly signs with. *RAUC CA*: the certificate the image trusts for bundles; the *signer* is the yearly key it vouches for. *Channel*: the signed list of updates, on GitHub Releases.

## 0. Before the day (online; nothing blocks the next step if all are ticked)
- [ ] **Founder decisions** in `docs/DECISIONS.md` (see [KEYS.md](KEYS.md)): root on three YubiKeys from the first ceremony (changes D-010), and the RAUC CA option (recommended now: **B**, an encrypted CA file on two holders' sticks).
- [ ] **Rehearsals green:** `scripts/tuf-bootstrap-root.sh rehearse-tokens /tmp/r1` and `python3 scripts/ceremony-guide.py --yubikey --rehearsal` print `REHEARSAL PASSED`; `make update-signed BOARD=x86_64-efi` passes US0-US6 (the same flow on a VM with throwaway keys: good update in, tampered / wrong-key / older updates refused).
- [ ] **Spare YubiKey trial** passed and the three YubiKeys prepared ([CEREMONY.md](CEREMONY.md#ceremony-on-yubikeys-proposed-changes-d-010)).
- [ ] **Offline computer:** Debian live USB with `ykman`, `ykcs11`, `openssl`, `softhsm2`, git, the repo at a reviewed commit, and the pinned TUF tools (`python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt`). Yubico's PIV CA downloaded, its sha256 written down.
- [ ] Printed: [CEREMONY-CHECKLIST.md](CEREMONY-CHECKLIST.md) (part Y) and this page. Three people, a transfer stick, two sticks for the RAUC CA.

## 1. The ceremony (offline computer, network off, about an hour)
1. `export PYTHON=V/bin/python PYKCS11LIB=<libykcs11 path> YUBICO_PIV_CA=<CA file>`, then `python3 scripts/ceremony-guide.py --yubikey`. It makes each holder's root key on their YubiKey, the online keys in `<work>/online/`, signs the security root with two YubiKeys, and prints **the sheet**. All three read it aloud and sign it.
2. **RAUC CA and this year's signer** (decision 1, option B; you type a passphrase for the CA key):
   ```sh
   openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -keyout rauc-ca.key -out rauc-ca.pem -subj "/O=OneMind/CN=OneMind RAUC CA 1" \
     -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign
   openssl req -newkey rsa:3072 -nodes -sha256 -keyout signer.key -out signer.csr -subj "/O=OneMind/CN=OneMind release signer 2026"
   openssl x509 -req -in signer.csr -CA rauc-ca.pem -CAkey rauc-ca.key -CAcreateserial -days 365 -sha256 -extfile os/assemble/signer.ext -out signer.pem
   openssl verify -CAfile rauc-ca.pem signer.pem && openssl x509 -in rauc-ca.pem -noout -fingerprint -sha256   # write the fingerprint on the sheet
   ```
   Copy `rauc-ca.key` (encrypted) to two holders' sticks; it never goes online.
3. **Transfer stick, public files:** `out-security/root.json`, `rauc-ca.pem`, `signer.pem`. **Private, only for step 2.2 and then wiped:** `online/*.key`, `signer.key`.

## 2. Publish the trust (online computer)
1. PR: commit `root.json` as `os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json` (check its sha256 against the sheet). Merge to `main` after the gate's review.
2. Secrets (CEREMONY.md step 9): GitHub Environment `tuf-signing` (main only) gets `ONEMIND_TUF_TARGETS_KEY`, `_SNAPSHOT_KEY`, `_TIMESTAMP_KEY`; repository secrets `ONEMIND_RAUC_SIGNING_KEY` (signer.key), `ONEMIND_RAUC_SIGNING_CERT` (signer.pem), `ONEMIND_RAUC_KEYRING_CERT` (rauc-ca.pem). Then wipe the transfer stick.
3. Leave `ONEMIND_SECURITY_PUBLISH` off until step 4.

## 3. The Dell's image trusts these keys
1. From `main` (it now carries `root.json`): `make image BOARD=x86_64-efi VERSION=0.1.0 KEYRING=rauc-ca.pem`. Only the **public** CA certificate is used; it prints the CA fingerprint: compare it with the sheet. Use `VERSION=0.1.0` exactly: the channel's `min_from_version` is `0.1.0`, and a `0.1.0-dev` box would be skipped.
2. Install it on the Dell as in the Step 5 install, then at the Dell: `sha256sum /usr/lib/onemind/tuf/security/root.json` (= the sheet) and `openssl x509 -in /etc/rauc/keyring.pem -noout -fingerprint -sha256` (= the sheet). `onemind update check` should say `decision: nothing` (no release yet).

## 4. The first real signed update
1. Set the repository variable `ONEMIND_SECURITY_PUBLISH=true`. Run **Actions → security-nightly → Run workflow** on `main` with `force_rebuild: true`, `dry_run: false`. It builds a newer version (`0.1.<snapshot>`), signs the bundle with the signer, signs the channel with the online keys, verifies it as a box would, and publishes to the `os-channel-security` release.
2. At the Dell: `onemind update check` → `decision: install` with the new version. Install it as an owner: `onemind update apply` from your laptop files an approval you confirm with your passkey (or, at the Dell, `sudo onemind update apply --local`).
3. **Watch it:** the Dell installs into the other slot, reboots, the health gate logs `RESULT mark-good slot=B version=0.1.<snapshot>`, and `onemind update status` says `committed`.

## 5. Watch it go back
1. `onemind update rollback` files the owner's go-back; approve it with your passkey in the dashboard (Approvals). The Dell boots the previous slot (`0.1.0`) and the gate logs `committed-boot slot=A`. After the next `onemind update check`, `onemind update status` says `rolled_back` (owner request). The newer version is still offered (an owner go-back is not a bad verdict): installing it again is step 4.2, and the service that would do it on its own stays off (see below).
2. Write on the sheet: the published version, the Dell's two gate lines, and the time. **Step 5 done.**

**If anything prints FAIL, refuses, or differs from the sheet: stop, change nothing, and ask the gate.** Not covered here (by design): the nightly auto-install (`onemind-update.service` stays off until it is decided), Secure Boot keys (KEYS.md decision 2), and the stable channel (a second `create` at the ceremony).
