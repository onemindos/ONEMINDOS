# OneMind OS update channel: the shared interface

**Status:** binding for the OS security pipeline (`os/update/`, `.github/workflows/security-nightly.yml`) and the on-box updater (`onemindd`, brief 30 B4.2). Both implement exactly this file. A change to it is a separate PR that both streams adopt.
**Serves:** poc-v0 §10.1; brief 30 B4.3 (release contract), BD-09 (update policy), B4.6 (keys), D-B1.5 (SBOM + CVE report).

**Terms used here.**
- **TUF** (The Update Framework) is a standard for signing update metadata so that a stolen online key, a replayed old file or a frozen mirror cannot trick a device into installing something bad.
- **Target** is any file the channel distributes, such as a RAUC bundle.
- **Role** is one signed metadata file with its own key: `root`, `targets`, `snapshot` or `timestamp`.

## 1. Channels and policy (BD-09)

| Channel | Content | Default `policy` on the box |
|---|---|---|
| `security` | Nightly rebuilds of the current release with Debian security fixes (same features) | `auto`: installs inside the maintenance window |
| `stable` | Feature releases | `notify`: shows the update and waits for the owner |

`policy` values:
- `auto` installs inside `window`.
- `notify` waits for the owner's approval.
- `off` does not check.

OS updates still pass through the gateway's approval rules (REC-DEC-13). `auto` only means that the owner has pre-approved this class of update.

## 2. Trust root on the box

- Each channel is its own TUF repository (TUF specification 1.0, compatible with python-tuf and go-tuf v2).
- The image ships the channel's root at `/usr/lib/onemind/tuf/<channel>/root.json`.
  - The image build gets it from `os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json`.
  - The founder commits that file after the offline ceremony (`scripts/tuf-bootstrap-root.sh`).
  - Until then, images carry no root and the channel cannot be published.
- **Roles:**
  - `root`: offline keys, threshold set at the ceremony; the brief's default is 2-of-3 (K-ROOT).
  - `targets`, `snapshot`, `timestamp`: one online key each, threshold 1, used by CI (K-TUF-ONLINE).
- **Keys:** ed25519 (`"keytype": "ed25519"`, `"scheme": "ed25519"`).
- `consistent_snapshot` is **false**, so metadata files have fixed names (see §3).
- **Expiry:**

  | Role | Expires after | Re-signed |
  |---|---|---|
  | `timestamp` | 1 day | every 6 hours |
  | `snapshot` | 7 days | when 3 days or fewer remain |
  | `targets` | 30 days | when 10 days or fewer remain |
  | `root` | 1 year | at an offline ceremony (a new `<N+1>.root.json`, signed by the old and the new root keys) |

  The CI job `security-nightly.yml` → `timestamp` does the 6-hourly re-signing.

  Brief 30 B4.3 proposed 7, 30 and 180 days plus an offline-grace setting. This file follows the shorter values that the pipeline and updater streams were given. The founder owns the choice (§7).

## 3. Repository layout (flat)

All files of a channel sit side by side under one base URL `<url>`:

```
<url>/1.root.json, 2.root.json, ...     every root version (the client walks the chain)
<url>/root.json                         the newest root (convenience; clients use the numbered files)
<url>/timestamp.json
<url>/snapshot.json                     not version-prefixed (consistent_snapshot = false)
<url>/targets.json
<url>/<basename of each target path>    e.g. onemind-x86_64-efi-0.1.20261112025704.raucb
```

- **Metadata:** standard TUF, with the metadata base URL = `<url>/`.
- **Target files:** fetched from `<url>/<basename(target path)>`, **not** from `<url>/<target path>`.
  - Basenames are unique by construction, because they embed the board and the version.
  - The flat layout works on hosts that have no directories, such as GitHub Release assets.
  - With go-tuf v2, the updater downloads the file itself and checks it with `TargetFiles.VerifyLengthHashes`, instead of calling `DownloadTarget` with a base URL.
  - Length and sha256 come from `targets.json`. A file that fails the check is discarded, whatever served it.
- **HTTP:** clients must follow HTTP redirects, because GitHub serves release assets through a redirect.
- **Order:** the publisher uploads targets first, then `targets.json`, `snapshot.json`, and `timestamp.json` last. A client that reads mid-update sees either the old set or the new one.

## 4. Box configuration: `/etc/onemind/update.conf`

```
# comment lines start with #; one key=value per line; unknown keys are ignored
channel=security
url=https://github.com/onemindos/ONEMINDOS/releases/download/os-channel-security
window=02:00-05:00
policy=auto
```

| Key | Meaning | Default |
|---|---|---|
| `channel` | `security` or `stable`; picks `/usr/lib/onemind/tuf/<channel>/root.json` | `security` |
| `url` | Channel base URL (§3). A LAN or USB mirror is just another `url`, because trust comes from TUF, not the host | the GitHub Releases URL of the channel |
| `window` | Local-time maintenance window `HH:MM-HH:MM`; may wrap past midnight (`23:00-04:00`) | `02:00-05:00` |
| `policy` | `auto`, `notify` or `off` (§1) | `auto` for `security`, `notify` for `stable` |

- The image ships the default file at `os/rootfs/layers/base/etc/onemind/update.conf`.
- Owner changes are stored where the updater keeps writable state. Location and precedence belong to the updater stream.

## 5. Targets and their custom metadata

Each security build adds, per board, three targets under `<board>/<version>/`:

| Target path | What |
|---|---|
| `<board>/<version>/onemind-<board>-<version>.raucb` | The signed RAUC bundle (verity format) |
| `<board>/<version>/onemind-<board>-<version>.spdx.json` | SBOM of the rootfs (syft, SPDX JSON) |
| `<board>/<version>/onemind-<board>-<version>.cve-report.json` | Trivy JSON with the Debian-tracker VEX applied |

Custom metadata of a **bundle** target (all fields always present):

```json
{
  "board": "x86_64-efi",
  "version": "0.1.20261112025704",
  "compatible": "onemind-x86_64-efi",
  "min_from_version": "0.1.0",
  "security": true,
  "built_from_snapshot": "20261112T025704Z",
  "sbom": "x86_64-efi/0.1.20261112025704/onemind-x86_64-efi-0.1.20261112025704.spdx.json",
  "cve_report": "x86_64-efi/0.1.20261112025704/onemind-x86_64-efi-0.1.20261112025704.cve-report.json"
}
```

**Fields:**
- `compatible` is the RAUC compatible string from `os/boards/<board>/board.yaml`. It equals `[system] compatible` in the box's `/etc/rauc/system.conf`, and RAUC itself refuses a mismatch.
- `sbom` and `cve_report` name the sibling targets, so they are verified the same way.
- The SBOM and CVE-report targets carry `{"board", "version", "kind": "sbom" | "cve_report"}`.

**Versions:**
- Format: `<base_version>.<YYYYMMDDHHMMSS>`, where the last part is the snapshot.debian.org timestamp and `base_version` comes from `os/update/channel.json`.
- They are monotonic with the snapshot. The same value is written to `ONEMIND_VERSION` in the bundle's `/usr/lib/os-release` and to the RAUC manifest.
- Compare them as dot-separated integers.

**Client selection:**
1. Keep only `.raucb` targets with `custom.board` equal to the box's board and `custom.compatible` equal to its RAUC compatible.
2. Keep only versions newer than the booted `ONEMIND_VERSION`.
3. Keep only those whose `min_from_version` is at or below the booted version.
4. Take the highest remaining version.
5. Never offer a release listed in the box's `bad-releases` (B4.2).

**Retention and anti-rollback:**
- The channel keeps the newest 3 versions per board.
- The publisher refuses a version that is not newer than every version already listed for that board.

## 6. Publishing (CI side) and keys

| Secret (GitHub Actions) | Used by | Without it |
|---|---|---|
| `ONEMIND_RAUC_SIGNING_KEY`, `ONEMIND_RAUC_SIGNING_CERT` | `build` (bundle signature) | throwaway CA per run, dry run |
| `ONEMIND_RAUC_KEYRING_CERT` (optional, public) | `build`: the CA cert put into the image's `/etc/rauc/keyring.pem` | the signing cert itself is the keyring |
| `ONEMIND_TUF_TARGETS_KEY`, `ONEMIND_TUF_SNAPSHOT_KEY`, `ONEMIND_TUF_TIMESTAMP_KEY` | `tuf`, `timestamp` | throwaway TUF root and keys per run, dry run |
| `ONEMIND_TUF_ROOT_KEY` | **not read by CI, by design**: the root signs offline (§2); it is listed so nobody adds it | n/a |

**Publishing switch:** the repository variable `ONEMIND_SECURITY_PUBLISH`. CI publishes only when all of these hold:
- the variable is `true`;
- every required secret above exists;
- the channel root is committed;
- the run is not a `dry_run` dispatch.

Otherwise the run is a dry run: it builds, scans, tests, signs with throwaway keys, verifies, and keeps the results as workflow artifacts only.

## 7. Open choices (founder-owned; defaults in place)

- **Real keys and their custody.** These are K-ROOT, K-RAUC-CA/SIGN and K-TUF-ONLINE (B4.6, Z-04). The pipeline only names the secrets. It never creates a production key.
- **Hosting.** The default is GitHub Releases on this repository:
  - the rolling release `os-channel-<channel>` holds the TUF repository;
  - the release `os-<channel>-<version>` holds each build's bundles, SBOMs, CVE reports, VEX, gate results and metadata copy.

  To move the channel, serve the same flat files from the new host, then change `url` in two places: `os/update/channel.json` (CI) and `os/rootfs/layers/base/etc/onemind/update.conf` (the image default). Boxes already in the field keep their old `url` until an update or the owner changes it, so keep the old location serving, or redirecting, for at least one release cycle.
- **Expiry values** (§2) versus brief 30 B4.3's 7, 30 and 180 days plus offline grace.
