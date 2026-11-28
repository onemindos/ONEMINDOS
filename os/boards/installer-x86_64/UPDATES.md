<!-- SPDX-License-Identifier: Apache-2.0 -->
# Updating a box that was installed from the USB stick

Ties to: #234 (M-LIVE), D-010 (root-key ceremony), D-007 (Debian 13), `os/update/CEREMONY.md`, `os/update/CHANNEL.md`.

## Why this page exists, in plain words

A box that cannot take updates stops getting security fixes the day it is installed. The USB stick installs the `x86_64-efi` image. That image updates itself with **RAUC** (the tool that writes a new copy of the system into the spare "B" slot and boots it, going back to "A" if it does not come up healthy). RAUC only installs a bundle (one signed update file, `.raucb`) if the bundle was signed by a key the box already trusts. The box learns what to trust from a **keyring** (a list of trusted certificates) baked into the image.

So an update has to match the box on three things: the board (`compatible` string), the version (must be newer, and the box's own minimum `min_from_version` must be met), and the signing authority (the CA in the box's keyring). `scripts/release/dev-release.py` now checks all three before it publishes, with the same ordering rules the on-box updater uses (`internal/update/semver.go`).

## What a dev release gives you today

Every nightly dev pre-release carries, for the installer board:

| File | What it is |
|---|---|
| `onemind-x86_64-efi-<N>.raucb` | the system the stick installs, as an update bundle |
| `onemind-x86_64-efi-<N>-next.raucb` | the same system one version later: install this over a box that runs N |
| `dev-ca-x86_64-efi.cert.pem` | the public certificate of the throwaway CA that signed both (no key) |
| `update-compat-x86_64-efi.json` | board, compatible string, N, N+1, minimum version, CA fingerprint |

The **dev CA is made fresh for every build and destroyed with the build** (`os/assemble/dev-image.sh`). That is on purpose: no key store exists, nothing to steal. The price: a box installed from dev build N takes only the `-next` bundle of build N. It refuses a bundle from build N+1 because that was signed by a different throwaway CA. The compat file says this in its `note`.

## Install once, update forever

In plain words: you write the stick once, install the box once, and from then on the box only takes updates. That works only if the box, from its very first boot, trusts the same signing authority that signs every later release. Which authority it trusts is decided when the stick is built, because the stick carries the box's whole system, keyring included. So the stick has to be built from the image that holds the **release** CA, not a throwaway one.

## What happens on ceremony day

The founder runs the root-key ceremony (`os/update/CEREMONY.md`) and commits `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json`. Nothing else in the repository changes:

1. The release keys `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT` and (optional) `ONEMIND_RAUC_KEYRING_CERT` are set (D-010: secrets of a GitHub Environment that only `main` may use; see the second follow-up below for where the workflow reads them today). On a publishing run `security-nightly.yml` writes them to a private temp folder and `os/update/build-release.sh` (`KEYDIR=`) signs the `x86_64-efi` bundle with them. `x86_64-efi` is already in `os/update/channel.json`. Next to the bundle it keeps `<bundle>.keyring.pem`: the public CA certificate the bundle was checked against (`rauc info --keyring`), the same file the image ships as `/etc/rauc/keyring.pem`.
2. The `installer` job of the same run builds the stick from the release-keyed image:
   - `scripts/release/installer-payload.py` reads `release-x86_64-efi.json`. `"dry_run": false` means release-signed: it copies only that public `keyring.pem` into a folder of its own. It refuses a publishing run with a dry-run release, a release on a run that does not publish, another board or version, and a keyring that holds anything but certificates.
   - `make release-image` (`os/assemble/release-image.sh`) assembles the `x86_64-efi` disk image with that keyring and **no signing key**: it makes no bundle, and refuses a folder that holds any file but `keyring.pem`, a private key, a `-dev` version or `SECUREBOOT=1` (`make release-image` passes `SECUREBOOT` on, so the refusal also holds through make). After assembly it reads `/etc/rauc/keyring.pem` back from the assembled tree, the tree the image's root filesystem is packed from. If that file is missing or is not byte for byte the given CA (for example an assembler that ignores or replaces `--keyring`), it deletes the image and its `SHA256SUMS` and stops. The `release-ca.cert.pem` it leaves next to the image is that read-back file, not a copy of the input.
   - `scripts/release/check-release-image.sh` then checks the image against the signed build. The keyring read back from the image must be byte for byte the bundle's `keyring.pem`, and no dev CA may sit next to it. `rauc info --keyring=<that keyring>` (tools container) must accept this run's bundle, which is what the installed box will do. The image's `packages.txt` must equal the bundle's, because the stick's image comes from a second rootfs build and only the first was scanned (Trivy, ClamAV) and signed.
   - Then the job builds the stick (`make installer`) and runs I1-I5 on it. The stick, the CA certificate and a `README.txt` that names the mode are kept as the run's `installer-security-x86_64-release` artifact (`-dev` on a dry run). The job does not wait for publishing, so the README says to flash a release stick only if `os-security-<version>` was published.
3. A box installed from that stick runs release N and trusts the release CA, so release N+1 (and every one after it) installs as an update. The "same build only" limit of the dev stick disappears because every build is signed by the same authority.
4. No script reads, prints or logs a key. The `installer` job reads no secret and declares no environment: the only thing it gets from the signing side is the public certificate in the `build` artifact, and both stick scripts refuse that file if it holds a key. The signing keys stay where they are; this change does not move them.
5. `dev-release.py` stays as it is: it never signs, it only picks the files an image.yml run produced.

**When the keys are absent (every dry run, and image.yml always):** nothing changes. image.yml's installer job still runs `make image` (`os/assemble/dev-image.sh`, throwaway CA) and `make installer`, and the security build's `installer` job runs that same `make image` command. `test/unit/test_installer_release_payload.py` pins both.

**The release path is rehearsed on every dry run.** A dry run's release record carries a public throwaway `keyring.pem` (the CA its dry-run bundle was signed under). The `installer` job runs `make release-image` with it into a separate `out-rehearsal/`, runs `check-release-image.sh` on the result (read-back keyring, `rauc info` with the dry-run bundle, package list), and deletes it. The stick itself stays the dev stick from `make image`. So `release-image.sh` and the checks run with the real assembler on every security build that rebuilds, not first on ceremony day. A red rehearsal stops that night's dev stick too, on purpose.

## What is NOT done yet (follow-ups, not hidden)

- **The release stick is not published yet.** It is a 14-day workflow artifact of the security build; attaching it to the `os-security-<version>` release or the downloads page is a separate change. Until the ceremony, every stick is still the dev stick above.
- **The RAUC secrets are not in a GitHub Environment in the workflow yet.** The `build` job reads them without `environment:` (hardening item H-07, `docs/security/HARDENING-BACKLOG.md`), and `os/update/README.md` leaves that Environment to the founder. The stick path does not depend on it, because it never reads a secret.
- **The release path has not run with the real release keys yet.** The dry-run rehearsal above runs `make release-image`, `release-image.sh` and the checks with a throwaway keyring on every security build that rebuilds. But the publishing branch (mode `release`, the real release CA, a release-keyed stick through I1-I5) first runs on the first publishing security build. Neither path has run in CI from this change yet: CI on a PR runs only `update-unit` for this workflow.
- **The keyring is read back from the assembled tree, not from inside the `.img`.** The tree is what `mke2fs -d` packs into the root filesystem in the same `assemble.py` run. Reading `/etc/rauc/keyring.pem` out of the disk image's `onemind-system-a` partition (as `os/boards/rpi5/check-image.py` does with `debugfs`) would close the last step. That is a possible follow-up.
- **The stick's root filesystem is a second build.** Only its package list is compared with the scanned and signed build, not its bytes (the reproducible-build check `make repro-check` is separate).
- **Secure Boot:** the release image is the GRUB route. A release-signed Secure Boot stick needs the release db key (`os/secureboot/README.md`), not part of this.
- The on-box side (dashboard approval to host install) is #493, not this PR.
- No hardware proof: the update has run only in QEMU.

## What CI must show for the installer board

The preregistered criteria (`test/qemu/CRITERIA.md`, hash in `PREREGISTRATION.sha256`) are not edited. The installer writes the very same `x86_64-efi` disk image that the battery tests, so the battery rows below are the evidence for the installer board too. CI's first run of this PR is their first run with the new step.

| Row | Must show on `x86_64-efi` (battery job, `image.yml` matrix, `upto: T5`) | Installer-board reading |
|---|---|---|
| T2 signature control | a bundle signed by a wrong key is refused, boot order unchanged, no trial marker | a box from the stick refuses any bundle outside its keyring, including a dev bundle of another build |
| T5 stale-Ready trap | an update that breaks the node is marked bad and the box returns to the old slot with no input | a bad update on a box from the stick rolls back by itself |
| I1-I5 (`CRITERIA-INSTALLER.md`) | the stick installs and the target boots | the image the bundles above update is the one I1-I5 installed |
| new (unit) | `test/unit/test_installer_updates.py`: the bundles of release N and N+1 are an accepted pair, a foreign CA or older version is refused, the installer's `target_board` is covered by the battery matrix | |
| new (unit) | `test/unit/test_installer_release_payload.py`: release-signed means the release keyring and no key, a dry run means the unchanged dev path plus the release-path rehearsal, every mismatch is refused, an assembler that drops the keyring is refused, and `check-release-image.sh` fails on a foreign keyring, a dev CA, a RAUC refusal or a different package set | the security build's stick trusts the CA that signs the channel |

Hardware: kit `LT-X86-01` runs the same A to B update and the forced bad update on a real PC (never run yet).
