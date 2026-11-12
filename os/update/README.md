# OS security pipeline (`os/update/`)

This directory is the CI side of poc-v0 §10.1. Every night CI asks one question: "does Debian have a security fix the OneMind image lacks?" If it does, CI rebuilds the image from a newer frozen copy of the Debian archive, scans and tests the result, signs it, and offers it on the **security channel**.

On the box, `onemindd` installs from that channel by the owner's policy (BD-09: automatic by default), and the RAUC health gate rolls back anything that does not come up healthy.

Why it works this way: the image's root filesystem is read-only, so packages are never upgraded in place on a box. OneMind applies Debian's own default policy ("security updates install automatically, new features do not") **at build time**, and ships the result as a signed A/B update.

The interface between this pipeline and the updater is **[CHANNEL.md](CHANNEL.md)**.

## Pipeline (`.github/workflows/security-nightly.yml`)

| Job | Does | Code |
|---|---|---|
| `unit` | Unit tests for everything here (also on every PR touching `os/update/`) | `tests/` |
| `check` (per board) | Package list of the **last published** build (channel assets `current-<board>.*`), or of a fresh rootfs build when nothing is published yet | — |
| `decide` | Debian security tracker JSON → per-board report; choose a newer snapshot.debian.org timestamp that carries the fixes; publish switch | `check-security.py`, `pick-snapshot.py` |
| `build` (per board: x86_64-efi, vm, vm-do, arm64-efi) | Rootfs from the commit plus the generated snapshot change; post-build check; OpenVEX from the tracker; SBOM (syft); CVE scan (Trivy v0.76.2 with the VEX); ClamAV with fresh signatures; scan gate; signed RAUC bundle | `scan-rootfs.sh`, `debian-vex.py`, `scan-gate.py`, `build-release.sh` |
| `battery-*` | QEMU battery through `battery.yml` (new optional `snapshot` input): T0–T5 incl. T4v/T5v on x86_64-efi and vm-do (+TC1), T0–T1 on arm64-efi. Any FAIL fails the job, and `tuf`/`publish` depend on it | `test/qemu/` (unchanged) |
| `tuf` | TUF targets/snapshot/timestamp on top of the published channel; a python-tuf client then verifies every new file | `tuf-repo.py` |
| `publish` | Only when the switch is on (below). Tags the exact source, creates release `os-security-<version>`, updates the rolling release `os-channel-security` (targets first, `timestamp.json` last) | — |
| `timestamp` (every 6 h) | Re-signs `timestamp.json` (1-day expiry), and `snapshot`/`targets` near expiry | `tuf-repo.py refresh` |

**Triggers and permissions:**
- **Triggers:** cron nightly at 02:23 UTC, plus 6-hourly for re-signing.
- **`workflow_dispatch` inputs:**
  - `force_rebuild`: build even when no new fix was found.
  - `dry_run`: default **true** for manual runs.
- **Permissions:** `contents: read` everywhere, except `publish` and `timestamp`, which need `contents: write` to upload release assets and push the tag.

**The gate fails the board, and so blocks publishing, when:**
- ClamAV finds anything, or did not run;
- Trivy reports a **CRITICAL** finding whose Debian fix the image does not carry.

**The gate reports without failing:**
- other fixable findings;
- sources still behind an archive fix (from the post-build check);
- files ClamAV could not open.

### Reproducible from the commit

- The only input that changes between nights is the snapshot timestamp.
- `pick-snapshot.py apply --snapshot <TS>` writes it into `os/rootfs/debian.args` and `os/versions.lock.yaml` (the "generated change").
- Every job (`build`, `battery`, `publish`) applies the same value to the same commit.
- `publish` commits that change and pushes it as the tag `os-security-<version>`. So "what was built" is always a commit, and `git checkout os-security-<version> && make rootfs` rebuilds it.
- Tagging the change does not update `main`, so a maintainer must also merge it there. The nightly `check` reads the last *published* package list, so an unmerged bump does not trigger the same rebuild again.

## Keys, the publish switch, and dry runs

These are founder decisions ([CHANNEL.md §6–7](CHANNEL.md)). The pipeline names the secrets and never creates a production key (brief 30 SB-10, B4.6).

| Repository setting | Kind | Purpose |
|---|---|---|
| `ONEMIND_RAUC_SIGNING_KEY` | secret | PEM private key that signs RAUC bundles (K-RAUC-SIGN; certificate with EKU codeSigning) |
| `ONEMIND_RAUC_SIGNING_CERT` | secret | Its certificate (PEM) |
| `ONEMIND_RAUC_KEYRING_CERT` | secret (public content), optional | The CA certificate the image trusts (`/etc/rauc/keyring.pem`, K-RAUC-CA); defaults to the signing cert |
| `ONEMIND_TUF_TARGETS_KEY` / `_SNAPSHOT_KEY` / `_TIMESTAMP_KEY` | secrets | ed25519 PKCS#8 PEM private keys of the online TUF roles (K-TUF-ONLINE) |
| `ONEMIND_TUF_ROOT_KEY` | — | **Deliberately not used.** The root signs offline (K-ROOT, 2-of-3). CI never holds it |
| `ONEMIND_SECURITY_PUBLISH` | variable | `true` turns publishing on |

**Publishing happens only when all of these hold:**
- the RAUC and online TUF secrets exist;
- `os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json` is committed;
- the variable is `true`;
- the run is not a `dry_run` dispatch.

**Otherwise the run is a dry run:**
- Bundles are signed by a throwaway CA made inside the build container, and TUF metadata by a throwaway root and keys made inside the `tuf` job. Both are deleted when the step ends.
- Results stay as workflow artifacts (`release-<board>`, `tuf-security-metadata`, `decide`).
- Nothing is uploaded to a release.

**Recommended, not configured here:** put the signing secrets in a GitHub **Environment** restricted to `main`. A required reviewer would stop the nightly automation, so that choice is the founder's.

**Bootstrapping the root (offline, once per channel).**
1. Run `scripts/tuf-bootstrap-root.sh rehearse <dir>` in a VM with networking off to practise.
2. At the ceremony, run `scripts/tuf-bootstrap-root.sh create <dir> security 2 <root1.key> <root2.key> -- targets.pub snapshot.pub timestamp.pub`.
3. Commit `<dir>/root.json` as `os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json`.
4. Store the three online private keys as the secrets above.

The script refuses to run in CI. Root keys on hardware tokens need a token-backed signer, which is not built yet: `tuf-repo.py` signs with PEM key files, and `securesystemslib` has HSM/PKCS#11 signers to add when the token model is chosen (B4.6 `<HSM-OR-TOKEN-MODEL>`).

**Moving the hosting:** see [CHANNEL.md §7](CHANNEL.md). Any static host that serves the flat files works. Change `url` in `channel.json` and `os/rootfs/layers/base/etc/onemind/update.conf`, and keep the old URL serving for a release cycle.

## Running it locally

There is no Docker on the Mac, so builds run in a Lima VM (`limactl start --name <n> --tty=false --cpus 8 --memory 16 template:docker`, with the worktree mounted writable; `make`/`python3-yaml` installed; `qemu-user-binfmt` for amd64 under an arm64 VM).

```sh
# unit tests (stdlib), then the TUF tests with the pinned python-tuf
python3 -I -m unittest discover -s os/update/tests -p 'test_*.py'
python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt
V/bin/python -I -m unittest discover -s os/update/tests -p 'test_tuf_repo.py'

# what does the current image lack?
curl -fsSL -o tracker.json https://security-tracker.debian.org/tracker/data/json
make rootfs BOARD=arm64-efi && tar -xf out/rootfs-debian-arm64-efi.tar usr/lib/onemind/packages.txt var/lib/dpkg/status
python3 -I os/update/check-security.py --packages usr/lib/onemind/packages.txt --status var/lib/dpkg/status --tracker tracker.json
python3 -I os/update/pick-snapshot.py pick --report check.json --archs arm64

# scan, sign (throwaway CA), TUF (throwaway keys), verify
os/update/fetch-tools.sh ~/bin && TRACKER=tracker.json BIN=~/bin os/update/scan-rootfs.sh <rootfs-dir> arm64-efi rel onemind-arm64-efi-<v>
docker run --rm -v $PWD:/src:ro -v $PWD/out:/out -v $PWD/rel:/rel -e BOARD=arm64-efi -e VERSION=<v> -e SNAPSHOT=<ts> \
  -e ROOTFS=/out/rootfs-debian-arm64-efi.tar onemind-tools:arm64 /src/os/update/build-release.sh /rel
V/bin/python -I os/update/tuf-repo.py keygen --out-dir k && V/bin/python -I os/update/tuf-repo.py init-root --root-key k/root.key \
  --targets-pub k/targets.pub --snapshot-pub k/snapshot.pub --timestamp-pub k/timestamp.pub --out root
V/bin/python -I os/update/tuf-repo.py build --repo chan --root root/root.json --release rel/release-arm64-efi.json \
  --targets-key k/targets.key --snapshot-key k/snapshot.key --timestamp-key k/timestamp.key
V/bin/python -I os/update/tuf-repo.py verify --repo chan --root root/root.json
```

## Files

| File | Purpose |
|---|---|
| `CHANNEL.md` | The shared interface (TUF layout, custom metadata, `update.conf`) |
| `channel.json` | CI settings: base version, expiries, retention, channel URLs and release tags |
| `check-security.py` | debsecan-style check: installed **source** packages (via `dpkg` status) against the tracker's `resolved` fixed versions |
| `pick-snapshot.py` | Choose the snapshot timestamp (`pick`), write the generated change (`apply`), print the release version (`version`) |
| `debian-vex.py` | OpenVEX v0.2.0 from tracker states: `not_affected` (fixed_version 0), `fixed`, `affected` with Debian's no-dsa/ignored/postponed reason |
| `scan-rootfs.sh`, `fetch-tools.sh`, `scan-gate.py` | Scans and the gate; Trivy and syft pinned by version + sha256, ClamAV by image digest (`os/versions.lock.yaml`) |
| `build-release.sh` | Tree → ext4 → signed verity bundle + `release-<board>.json`, in the tools container |
| `tuf-repo.py`, `requirements-tuf.txt` | TUF tool on python-tuf 7.0.1 (hash-pinned): keygen, offline `init-root`, `build`, `refresh`, `verify` |
| `tests/` | `unittest` suites with a recorded tracker fixture (subset of the 2026-11-12 tracker JSON plus synthetic states) |

## Local results (2026-11-12, Lima VM, arm64 host)

- **check-security** on the real `arm64-efi` rootfs (175 binaries) against the live tracker found **zlib**: CVE-2026-27171, -76844 and -85091 are fixed in `1:1.3.dfsg+really1.3.1-1+deb13u1`, and the image has `…-1+b1`.
  - Without `dpkg` status the check misses it, because binary `zlib1g` ≠ source `zlib`. That is why CI always passes `--status`.
- **pick-snapshot** against the live snapshot API chose `20261112T025704Z`. It also reported `not_picked_by_build: ["zlib"]`: the fix is **already in** the current snapshot `20261111T000000Z`, yet the image does not have it.
  - Cause: `os/rootfs/Containerfile` runs `apt-get install <list>` but never `apt-get upgrade`. Packages that come from the `debian:trixie` base image (zlib1g here) stay at the base image's versions, whatever the snapshot.
  - **A new snapshot alone cannot fix base-image packages.** The fix belongs in the Containerfile, outside this stream: one `apt-get -y upgrade` after `apt-get update` in the `rootfs` stage. Until then, `decide` reports these packages and the gate fails if one of them is CRITICAL.
- **Scans** of the same rootfs:
  - Trivy found 516 findings (0 CRITICAL, 130 HIGH), 3 of them fixable (the zlib ones), and 1 more suppressed by our VEX (Trivy's own Debian data already covers most tracker states).
  - The VEX has 2055 statements.
  - syft wrote the SBOM.
  - ClamAV 1.5.3 with fresh signatures: 13,724 files, 0 infected.
  - Gate: **PASS**.
  - Under the VM's *rootless* Docker, 13 root-only files (e.g. `/etc/shadow`) could not be opened. The gate lists them as `unscanned`. GitHub runners use rootful Docker, where they are expected to be readable (not yet observed in CI).
- **Release** `arm64-efi`: a verity bundle signed by a throwaway CA, which `rauc info --keyring` verifies. Then TUF metadata (throwaway keys), and the python-tuf client verified all 3 targets. A one-byte change to the bundle is reported as a length mismatch.
- **x86_64-efi** (amd64 emulated under qemu-user in the arm64 VM) went through the same pass: rootfs → throwaway-CA verity bundle (verified by `rauc info`) → scans (ClamAV 12,579 files, 0 infected; same zlib finding; gate PASS).
  - Its TUF build on top of the arm64 channel produced metadata version 2 with both boards.
  - The client verified all 6 targets against the dry-run root embedded in the images.
  - No published artifact contains a host path.
- **Not run locally:** the QEMU battery and the GitHub workflow itself. Both need GitHub's runners (`battery.yml` with KVM). This stream does not push, so the first CI run comes after review.
