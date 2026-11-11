# Sources: LAB-fedora-bootc (Fedora bootc + greenboot VM lab)

**Spike:** `evidence/lab/fedora-bootc/` · **Accessed:** 2026-11-10/11 (UTC) · **Claims:** `evidence/claims/LAB-fedora-bootc.csv` (C-LAB-fedora-bootc-001 … 017)

## How these sources were used

- **Lab observations** are primary evidence from runs on 2026-11-11 (UTC). Logs are in `evidence/lab/fedora-bootc/logs/`, and the scripts that produced them are in `evidence/lab/fedora-bootc/scripts/`.
- **Code** was read from a shallow clone of greenboot-rs in `../.lab/src/` (outside the repo) and through `gh api` at pinned SHAs. A commit SHA cannot change, so the permalink is its own archive.
- **Archiving:** the request to save new Wayback snapshots (`web.archive.org/save/...`) was **denied by this environment's permission policy** (classified as a public data upload), and I did not work around it. Instead, the two load-bearing issue pages are saved as text with SHA-256 hashes in `sources/LAB-fedora-bootc/`. For other pages, the closest *existing* snapshot was looked up with the read-only availability API. **ARCHIVE-GAP** marks pages that have no snapshot; Zeus can save them later.

## 1. Pinned code

| Source | Pin | Date | Type | Claims |
|---|---|---|---|---|
| github.com/fedora-iot/greenboot-rs @ v0.16.4 | `438eb9645f08dee53c3c766126f307d94847395a` | 2026-08-18 | PRIMARY (code) | 003, 004, 005 |
| github.com/fedora-iot/greenboot-rs @ v0.16.5 (= main HEAD) | `6efc3c109b54fec5e8a0ab575721258d28a85d9d` | 2026-11-04 | PRIMARY (code) | 003, 013 |
| github.com/bootc-dev/bootc tag v1.17.1 (the version in the image) | `434e0e7e1b2631c65babd0eee4c456fd77fa9070` | 2026-10-07 | PRIMARY-METADATA (release) | 002, 007 |

Key permalinks:
- Retry and rollback flow: https://github.com/fedora-iot/greenboot-rs/blob/438eb9645f08dee53c3c766126f307d94847395a/src/main.rs#L395-L445
- `handle_rollback` runs `bootc rollback`: https://github.com/fedora-iot/greenboot-rs/blob/438eb9645f08dee53c3c766126f307d94847395a/src/lib/handler.rs#L151-L187
- GRUB counter snippet: https://github.com/fedora-iot/greenboot-rs/blob/438eb9645f08dee53c3c766126f307d94847395a/grub2/08_greenboot.cfg#L1-L20
- Trigger unit (ExecStop, RequiredBy finalize): https://github.com/fedora-iot/greenboot-rs/blob/438eb9645f08dee53c3c766126f307d94847395a/usr/lib/systemd/system/greenboot-set-rollback-trigger.service#L1-L15
- Fallback detection, unchanged in v0.16.5: https://github.com/fedora-iot/greenboot-rs/blob/6efc3c109b54fec5e8a0ab575721258d28a85d9d/src/main.rs#L223-L249 and #L298-L310

## 2. Web and issue pages

| URL | Accessed | Type | Archive | Claims |
|---|---|---|---|---|
| https://github.com/fedora-iot/greenboot-rs/issues/219 | 2026-11-10 | PRIMARY (upstream bug report, open) | ARCHIVE-GAP in Wayback; saved text `sources/LAB-fedora-bootc/greenboot-rs-issue-219.txt`, sha256 `4708f47aaa08b9d0a3cd66fecc109bb68fa949dc7699543cab62c181b99f71de` | 012 |
| https://github.com/fedora-iot/greenboot-rs/issues/218 | 2026-11-10 | PRIMARY (upstream bug report, open) | ARCHIVE-GAP; saved text `sources/LAB-fedora-bootc/greenboot-rs-issue-218.txt`, sha256 `f6b78dab322f760d495d1e308121c6ec5a140be2a7f89dbca71f486ad6770af5` | 014 |
| https://github.com/fedora-iot/greenboot-rs/issues/217 (closed 2026-10-28) | 2026-11-10 | PRIMARY (read for context: version-skew trigger bug) | not archived (context only) | — |
| https://github.com/fedora-iot/greenboot-rs/releases | 2026-11-10 | PRIMARY-METADATA (via `gh api`) | repo snapshot http://web.archive.org/web/20260601011011/https://github.com/fedora-iot/greenboot-rs (older than the releases cited; tags are pinned above) | 003 |
| https://github.com/bootc-dev/bootc/releases (v1.17.1) | 2026-11-10 | PRIMARY-METADATA (via `gh api`) | http://web.archive.org/web/20261020214826/https://github.com/bootc-dev/bootc | 002 |
| https://quay.io/repository/fedora/fedora-bootc | 2026-11-10 | PRIMARY-METADATA (`skopeo inspect` digest + labels) | digest pinned (content-addressed) | 001 |
| https://quay.io/repository/centos-bootc/bootc-image-builder | 2026-11-10 | PRIMARY-METADATA (`skopeo inspect`) | digest pinned | 016 |
| docker.io/library/registry:2 (lab registry only) | 2026-11-10 | PRIMARY-METADATA | digest `sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373` | — |

## 3. Lab tooling (host)

| Tool | Version | Role |
|---|---|---|
| Lima | 2.3.0, template `fedora-44`, vmType vz, aarch64 | Disposable build VM: podman 5.8.1, skopeo 1.22.3, registry, bootc-image-builder |
| QEMU (Homebrew) | 11.1.3, `-accel hvf`, edk2-aarch64 UEFI | Test-VM hypervisor only |
| Host | Apple M5 Max, macOS 27.2 | — |

## 4. Prior repo research this builds on

- `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` §4 (bootc facts, greenboot-rs, Pi caveats). This lab adds measured behaviour and does not repeat that desk work.
- `context/03-repo-findings-index.md` (open item "bootc rollback").
