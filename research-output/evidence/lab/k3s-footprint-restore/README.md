# Spike LAB-k3s-footprint-restore: k3s footprint, and backup/restore onto a fresh box

**Tag:** LAB-k3s-footprint-restore · **Written before running:** 2026-11-10 · **Mission ref:** RESEARCH-MISSION.md §7 items 4 and 5 · **Serves:** N-2, N-9, P-1, P-7, R-1, R-2, R-3, M-6, M-2 · **Closes (if it passes):** the open item "k3s single-node SQLite datastore backup coverage by `etcd-snapshot`" in `context/03-repo-findings-index.md` (ADR D5, VUPD §7).

> **Explain it like I'm the founder.** k3s is the small Kubernetes that would run on every OneMind box. Two questions decide whether that is safe for a home box: *how much of the box does k3s itself eat* (memory, CPU, disk) before the user installs anything, and *if the box dies, can we rebuild it on new hardware from a backup and have every app come back with its data?* This spike answers both on real (virtual) machines instead of trusting docs.

## Goal
1. Measure the idle and loaded footprint (RAM, CPU, disk) of a single-node k3s server on Debian 13, for both datastores k3s offers: **SQLite** (the default for one server) and **embedded etcd** (needed for multi-server HA).
2. Back up each box with **restic** (encrypted, deduplicated) plus the right k3s datastore backup, then **restore onto a brand-new VM** and verify that workloads and their data come back.

## Hypotheses (stated before running)
- **H1 (footprint).** On Debian 13 arm64 with k3s defaults (Traefik, CoreDNS, metrics-server, local-path-provisioner, ServiceLB), an idle SQLite server adds **≤ 1.2 GiB** of used memory over the bare OS, uses **≤ 15 % of one core** averaged over 120 s, and needs **≤ 2 GiB** of disk (binary plus pulled images plus datastore). Under a modest load (30 extra pods, one PostgreSQL with a volume, and API churn) the increase stays **≤ 2.0 GiB**, so a 4 GiB box stays usable. Embedded etcd costs **more** than SQLite, by **≤ 400 MiB** at idle.
- **H2 (SQLite snapshot coverage).** `k3s etcd-snapshot save` does **not** work on the SQLite datastore; the SQLite backup is a file-level copy of `/var/lib/rancher/k3s/server/db/` plus the server token. (This is the "UNVERIFIED" item; either outcome is recorded as a finding.)
- **H3 (SQLite restore).** A restic backup of the SQLite datastore (taken consistently), the server token and the local-path volume directory, restored onto a fresh VM with the same k3s version and the same **node name**, brings every workload back.
- **H4 (etcd restore).** A `k3s etcd-snapshot save` snapshot plus the token and volume directory, carried in a restic repository and restored on a fresh VM with `k3s server --cluster-reset --cluster-reset-restore-path=…`, brings every workload back.

## Pass / fail criteria (fixed before running)
| ID | PASS if | FAIL if |
|---|---|---|
| F1 idle | SQLite idle memory increase ≤ 1.2 GiB **and** idle CPU ≤ 15 % of one core **and** disk ≤ 2 GiB | any bound exceeded (numbers recorded either way) |
| F2 loaded | SQLite loaded memory increase ≤ 2.0 GiB on a 4 GiB VM, no OOM kill, all test pods Ready | OOM, pods not Ready within 5 min, or bound exceeded |
| F3 etcd delta | etcd idle memory − SQLite idle memory ≤ 400 MiB | > 400 MiB |
| F4 SQLite snapshot | Observation only: record the exact output of `k3s etcd-snapshot save` on SQLite | — |
| R1 SQLite restore | On the fresh VM, within 5 min of k3s start: node Ready; every test Deployment/StatefulSet Available; PostgreSQL row count and `md5` of the table equal the pre-backup values; the ConfigMap and Secret test values match; the sha256 of a file written into a local-path PVC matches | any check differs or times out |
| R2 etcd restore | Same checks as R1 after `--cluster-reset` restore | any check differs or times out |
| R3 hygiene | restic `check` passes on the repository; no plaintext secret visible in the repository files (`grep` for the Secret's value returns nothing) | `check` fails or plaintext found |

Also recorded (no pass/fail): backup size, backup time, restore time (k3s start → all checks green).

## Method (planned)
- Disposable Lima VMs on the Apple M5 Max host (Apple Virtualization framework, **aarch64** guests), Debian 13 template, **2 vCPU / 4 GiB / 20 GiB**, no host mounts. Names `kfr-sqlite`, `kfr-sqlite-restore`, `kfr-etcd`, `kfr-etcd-restore`. All four are deleted at the end.
- k3s and restic are official GitHub release binaries, checked against the release checksum files on the host before being copied into the VM. The k3s `install.sh` is downloaded, hashed and read, then run only inside the VM with `INSTALL_K3S_SKIP_DOWNLOAD=true`.
- Both source VMs set `node-name: omos-box` in `/etc/rancher/k3s/config.yaml` so the restored box has the same Kubernetes identity (local-path volumes are pinned to a node name).
- The restic repository is created inside the source VM, copied out to the host (playing the role of a USB drive or NAS), and copied into the restore VM.
- Footprint: `MemTotal − MemAvailable` before installing k3s, after 5 min idle, and under load; process RSS for `k3s server` and `containerd`; cgroup `memory.current`; CPU from `/proc/stat` deltas over 120 s; disk from `du`.

## Limits
aarch64 only (no x86_64 guest timing; x86 under emulation would distort CPU numbers). VMs on a very fast host: CPU percentages will be lower than on a Raspberry Pi; memory numbers transfer, CPU numbers do not. One node only; no Longhorn; no multi-server etcd quorum loss.

---
<!-- RESULTS BELOW ARE ADDED AFTER THE RUN -->

# Results (run 2026-11-10 20:13–20:34 US-Eastern, i.e. 2026-11-11 01:13–01:34 UTC)

**Status: complete for aarch64.** Everything planned ran for real in disposable VMs. Nothing was blocked except one Wayback archive request (see Sources). One pre-registered check failed on the first try (R2) and passed on a second, documented attempt. Both attempts are reported below.

## Pinned versions and hashes
| Item | Version | Hash / identity |
|---|---|---|
| Host | Apple M5 Max, macOS, Lima 2.3.0 (`vz`), aarch64 guests | — |
| Guest OS | Debian 13.7, kernel `6.12.115+deb13.1-cloud-arm64` (Lima `template:debian-13`), 2 vCPU / 4 GiB (3923 MiB visible) / 20 GiB, `--mount-none --containerd=none` | — |
| k3s | v1.37.2+k3s1 (go1.26.10), tag commit `f6973cb8` [C-LAB-k3s-footprint-restore-001] | `k3s-arm64` sha256 `a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b` (matches release file) |
| k3s installer | `install.sh` at tag v1.37.2+k3s1, read before use, run only in VMs with `INSTALL_K3S_SKIP_DOWNLOAD=true` | sha256 `ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b` |
| restic | 0.19.1 [C-LAB-k3s-footprint-restore-002] | `restic_0.19.1_linux_arm64` sha256 `2fb45ac6f9071b6f20eb883953a188f9e7c7cb6bbe43c67a2e47ada4e85ee7f0` (bz2 verified against release SHA256SUMS) |
| embedded etcd | 3.7.1 (as reported in the k3s log) | — |
| Test images | `nginx:1.29-alpine` (`sha256:5616878291a2…`), `postgres:17-alpine` (`sha256:3540c0362c80…`), `busybox:1.37` (`sha256:a7dbc319b143…`); k3s packaged images listed at the end of `logs/run-sqlite.log` | digests from `crictl images` |

Script hashes (sha256) are in the table at the end of this file.

## Footprint (F1–F3)

Memory is **used = MemTotal − MemAvailable** (what the OS cannot hand to a new app). Baseline is the same VM before k3s was installed. CPU is averaged over 120 s and given as "% of one core" (200 % = both vCPUs busy).

| Measure | Bare Debian 13 | k3s SQLite idle | k3s etcd idle | SQLite loaded | etcd loaded |
|---|---|---|---|---|---|
| Used memory (MiB) | 353 / 349 | **1289 (+936)** | **1308 (+959)** | **1882 (+1529)** | **1867 (+1518)** |
| of which Lima helper `kubectl` (not k3s) | — | 141 | 142 | 141 | 143 |
| of which load generator `kubectl` | — | — | — | ~109 | not in snapshot ² |
| **Attributable to k3s + workloads** | — | **~795** | **~817** | **~1279** | **≤ ~1375** |
| `k3s server` process RSS (MiB) | — | 780 | 805 | 759 | 779 |
| `containerd` RSS (MiB) | — | 197 | 176 | 212 | 219 |
| System CPU (% of one core) | 0.1 | **6.6** | **7.2** | 116.7 ¹ | 117.4 ¹ |
| `k3s server` CPU (% of one core) | 0 | 1.9 | 2.4 | 7.7 | 8.3 |
| Root disk used (MiB) | 938 | 2057 (+1119) | 2171 (+1233) | 2647 (+1709) | 2757 (+1819) |
| `/var/lib/rancher/k3s` (MiB) | — | 1020 | 1134 | 1607 | 1716 |
| Datastore dir `server/db` (MiB) | — | **17** | **131** | 26 | 135 |
| Pods running | — | 5 (+3 completed jobs) | 5 (+3) | 37 (+3) | 37 (+3) |
| OOM kills | — | — | — | 0 | 0 |

² The process list is a single snapshot; the short-lived churn `kubectl` was not running at that instant on the etcd VM.

¹ Dominated by the load generator, which forks a `kubectl` process about 9.5 times a second (1,140 create/delete cycles in 120 s). The `k3s server` process itself used 7.7–8.3 % of one core while serving that churn.

Notes on method: the RSS sum of all `containerd-shim` processes (98 → 740 MiB) double-counts shared pages and is not used. The `k3s.service` cgroup figure (1.8–2.7 GiB) includes page cache from unpacked images and is not used either. The ~141 MiB `kubectl` process is a child of `lima-guestagent` (the binary is the k3s multicall binary) and appears only in Lima VMs [C-LAB-k3s-footprint-restore-016]; it is subtracted in the "attributable" row.

**Verdicts:**
- **F1 idle: PASS.** +936 MiB raw (~795 MiB attributable) ≤ 1.2 GiB; 6.6 % of one core ≤ 15 %; +1.1 GiB disk ≤ 2 GiB [C-LAB-k3s-footprint-restore-007].
- **F2 loaded: PASS.** +1529 MiB raw ≤ 2.0 GiB on a 4 GiB VM, no OOM, all 37 pods Running; ~2.0 GiB stayed available [C-LAB-k3s-footprint-restore-008].
- **F3 etcd delta: PASS, and better than expected.** Embedded etcd on one node cost about the same memory as SQLite (+23 MiB, inside run-to-run noise), not "up to 400 MiB more". It does use more disk: 131 MiB vs 17 MiB for the datastore at idle [C-LAB-k3s-footprint-restore-009].
- **Context.** The k3s project's own profile (v1.26.5, p95 from Prometheus, a heavier Prometheus + Grafana workload) reports ~1.6 GB for a server with a workload on both x86 and a Pi 4B [C-LAB-k3s-footprint-restore-006]. Our numbers sit below that, which fits a lighter workload and a point-in-time reading rather than a p95. The documented minimum is 2 cores / 2 GB for a server [C-LAB-k3s-footprint-restore-005]: by our measurement that leaves about 1 GiB for the OS and apps on a 2 GB device, which is tight.

## Datastore backup coverage (F4): the open question is now answered
`k3s etcd-snapshot save` on the default SQLite datastore **fails**:
```
level=fatal msg="Error: see server log for details: etcd datastore disabled"
```
The server returns that error string from `pkg/cluster/managed.go#L151` at the release tag [C-LAB-k3s-footprint-restore-010]. On embedded etcd the same command saved a 13 MB snapshot. **So the k3s snapshot feature does not cover the single-box SQLite default.** That box needs a file-level backup, which is what the k3s docs describe: copy `server/db/` plus the token, "no special commands" [C-LAB-k3s-footprint-restore-003]. The docs do not say whether k3s must be stopped first. We avoided the question by taking an **online, consistent copy** with SQLite's own backup API (`sqlite3 state.db ".backup …"`, followed by `PRAGMA integrity_check` → `ok`). Copying the live files with plain `cp` was **not** tested.

## Backup (both datastores)
What went into restic: the datastore copy (SQLite `.backup` file or etcd snapshot), `server/token`, and the local-path volume directory `/var/lib/rancher/k3s/storage` (PostgreSQL data after a `CHECKPOINT`, plus the writer's file). That is about 80 MiB of data, stored as 27–28 MiB, in roughly 1 s. `restic check` reported no errors, and the test Secret's plaintext value does not appear anywhere in the repository files (**R3: PASS**) [C-LAB-k3s-footprint-restore-015]. The repository was moved to the fresh VM through the host, standing in for a USB drive or NAS.

## Restore onto a fresh VM (R1, R2)
| Check | SQLite → fresh VM | etcd attempt 1 (token **file** restored) | etcd attempt 2 (token **passed** with `--token-file`), brand-new VM |
|---|---|---|---|
| k3s starts | yes, node Ready in 8 s | **no**: `bootstrap data already found and encrypted with different token` | yes, node Ready in 15 s |
| 32 test pods with containers started **after** the restore | 32/32 in **33 s** | 0 | 32/32 in **36 s** |
| PostgreSQL 100k rows, table md5 | identical | — | identical |
| ConfigMap value / Secret hash / 8 MiB file sha256 | identical | — | identical |
| PostgreSQL log | crash recovery (`redo done`), then ready | — | crash recovery, then ready |
| Verdict | **R1 PASS** [C-LAB-k3s-footprint-restore-011] | **R2 FAIL as first written** [C-LAB-k3s-footprint-restore-012] | **R2 PASS with the documented token step** [C-LAB-k3s-footprint-restore-013] |

**Why etcd attempt 1 failed.** On a fresh host, `k3s server --cluster-reset --cluster-reset-restore-path=…` started with no certificates on disk. It generated a **new CA and a new token** and **overwrote the token file we had restored** (`logs/restore-etcd-attempt1.log`; the file differed from the backup from byte 4, inside the CA-hash part). The restored datastore's bootstrap data is encrypted with the *old* token, so the next start refused it (`pkg/cluster/storage.go#L341`). The docs do warn that on a new host "you must pass the server token that was originally used" [C-LAB-k3s-footprint-restore-004], and at startup k3s prefers a token given in the config over the file on disk (`pkg/cluster/bootstrap.go#L269-L280`) [C-LAB-k3s-footprint-restore-014]. Attempt 2 passed the original token with `--token-file` (and kept `token-file:` in `config.yaml`). The reset then rewrote the certificates on disk from the restored datastore ("Updating bootstrap data on disk from datastore"), and the final token file matched the original. Contrast: for **SQLite, restoring the token file alone was enough**.

**Other things a restore must get right (seen in this run):**
- **Same node name.** Both boxes set `node-name: omos-box`. local-path volumes are tied to a node name, so a restored box that registered under a new hostname would leave PostgreSQL's volume unbound (inference from how local-path works; a different-name restore was **not** tested).
- **Same k3s version.** Both sides ran v1.37.2+k3s1. Cross-version restore was not tested (earlier research: rollback only by downgrade plus a snapshot from the older minor; see `context/03` "k3s rollback").
- **Stale status.** Right after a restore, the datastore still claims every Deployment is ready (that status was saved at backup time). Our checks counted only containers started after the restore. A OneMind "last verified restore" check must do the same.
- **Application consistency.** PostgreSQL came back through WAL crash recovery because its files were copied live after a `CHECKPOINT`. That worked here, but it is *crash-consistent*, not *application-consistent*. Product backups should run a per-app pre-backup hook (dump or freeze).

## What competitors do (backup/restore and footprint)
Sourced from earlier VERIFIED research in this repo (`research/platform/verify-updates-rollback-backups-security.md` §1, §2, §6, §7; `context/03` rows "HAOS backups", "umbrelOS backups", "Olares backups", "Olares Kubernetes").
| Product | What it does | Constraints | Constraint fit for OneMind |
|---|---|---|---|
| Home Assistant OS | Built-in encrypted backup archives (SecureTar v3), full or partial, several destinations, offered before updates | No Kubernetes; Supervisor + Docker; appliance hardware down to Pi | **Partial.** Copy the UX (encrypted by default, pre-update backup, many destinations). It has no k3s datastore, so it offers nothing for the token/datastore problem. |
| umbrelOS | Encrypted whole-device backups every hour with GFS retention (Kopia 0.23.1) to Umbrel/NAS/USB | Docker Compose, no Kubernetes; small team; x86 + Pi | **Partial.** Copy the cadence and retention. The engine (Kopia vs restic) is interchangeable; it has no k8s state. |
| Olares | restic-based snapshots of chosen folders and the Wise app, to local/S3/COS/Olares Space; app restore only for Wise | **k3s** (closest match), x86 + GPU boxes | **Best match on stack, weak on coverage.** Confirms restic on k3s is a proven pattern. Prior research found no evidence that it backs up the k3s datastore + token and restores the whole box; OneMind should go further, as this spike shows is possible. |
| k3s upstream | `etcd-snapshot` (twice a day, keep 5, optional S3) for etcd only; SQLite = copy files + token | — | **Direct fit.** This spike shows the missing pieces: SQLite needs its own online copy, and an etcd restore on new hardware needs the token passed explicitly. |

## Recommendations (with requirement IDs)
1. **REC-K3S-1: single-box default = SQLite, backed up by a OneMind backup job.** Take an online SQLite `.backup` (not `etcd-snapshot`, which fails), add the token and app volumes, and write it to a restic repository on a schedule. *Serves R-2, R-3, P-1, N-2, M-6.* [C-LAB-k3s-footprint-restore-010, -011]
2. **REC-K3S-2: the server token is a recovery-kit item, stored separately and encrypted.** Without it neither datastore can be restored on new hardware. The restore tool must **pass it explicitly** (`--token-file`) for etcd; it must not rely on dropping the file in place. *Serves R-2, M-2, U-4.* [C-LAB-k3s-footprint-restore-012, -013]
3. **REC-K3S-3: give every box a stable node name** in `/etc/rancher/k3s/config.yaml`, kept in the recovery kit, so volumes reattach on replacement hardware (OneMind box identity ≠ hostname). *Serves R-3, P-7, N-1.*
4. **REC-K3S-4: memory budget.** Plan for ~0.8–0.95 GiB for k3s with its default add-ons at idle on arm64, and ~1.3–1.5 GiB with a light app set (30 small pods + PostgreSQL). Make **4 GB the practical floor** for a OneMind box running k3s; treat 2 GB devices as agents or a "Lite" profile with packaged add-ons disabled (still to be measured; see founder test T3). *Serves N-2, N-3, P-5, H-3.* [C-LAB-k3s-footprint-restore-007, -008, -005]
5. **REC-K3S-5: embedded etcd costs almost no extra RAM on one node.** That makes `cluster-init` from day one a cheap option for boxes that may grow into multi-server HA (it avoids the unresolved SQLite → etcd migration). Keep it off SD/eMMC: the docs call etcd write-intensive, and it used 8× more datastore disk here. *Serves M-4, N-2, UX-6.* [C-LAB-k3s-footprint-restore-009, -005]
6. **REC-K3S-6: a "verified restore" check must ignore stale status** and test real data (fresh container start times, an app-level checksum), as this spike's `guest-verify.sh` and readiness loop do. Apps get pre-backup hooks for application consistency. *Serves R-2, UX-4.*

## Founder-runnable follow-up tests (not done in this spike)
Run from the host with `scripts/` (Lima ≥ 2.3 on Apple silicon). `run-all.sh` chains the steps that were run here one at a time; **`run-all.sh` itself was not executed end to end**, but every script it calls was.
| ID | Test | How | PASS if |
|---|---|---|---|
| T1 | Whole spike again | `LAB=~/…/.lab/k3s-footprint-restore scripts/run-all.sh` | both restore logs print `IDENTICAL` and `fresh_ready_pods=32/32` |
| T2 | Real Raspberry Pi 5 (4 GB and 8 GB, NVMe) footprint | on the Pi: copy the files to `/tmp/kfr`, then `sudo /tmp/kfr/guest-measure.sh baseline 120`, `sudo /tmp/kfr/guest-install.sh sqlite start`, wait 5 min, `sudo /tmp/kfr/guest-measure.sh idle 120` | idle used memory increase ≤ 1.2 GiB and idle CPU ≤ 30 % of one core |
| T3 | "Lite" profile | add `disable: [traefik, metrics-server, servicelb]` to `config.yaml` before install, then repeat T2 | idle increase ≤ 700 MiB (hypothesis) |
| T4 | Naive SQLite copy (the docs' literal wording) | in `guest-backup.sh`, replace the `.backup` line with `cp -a /var/lib/rancher/k3s/server/db/. /var/backups/kfr/` while k3s runs, then restore | restore identical; if it fails, the product must use `.backup` or stop k3s |
| T5 | Restore under a different node name | change `node-name` on the restore VM only | expected FAIL for local-path PVC pods; this confirms REC-K3S-3 |
| T6 | x86_64 | repeat with `--arch=x86_64` on an x86 host (emulation distorts CPU) | same verdicts as above |

## Glossary
- **k3s**: a small, certified Kubernetes distribution packaged as one binary. **Server** = control plane; **agent** = worker.
- **Datastore**: where Kubernetes keeps every object. In k3s that is **SQLite** (one file, single server) or **embedded etcd** (a replicated key-value store needed for several servers).
- **etcd snapshot**: a point-in-time copy of the etcd database made by `k3s etcd-snapshot save`.
- **Cluster reset**: `k3s server --cluster-reset`, which turns a node back into a one-member etcd cluster, optionally loading a snapshot first.
- **Server token**: the shared secret that encrypts k3s's bootstrap data (certificates, keys) inside the datastore. Lose it and the backup is unreadable.
- **restic**: an open-source backup tool that encrypts and de-duplicates data into a "repository".
- **local-path**: k3s's default storage, which keeps each volume as a folder on one named node.
- **RSS**: memory a process has in RAM right now. **MemAvailable**: what Linux estimates it can give to new programs without swapping.
- **Crash-consistent vs application-consistent**: a copy that looks like the power was pulled (the app must repair itself) vs a copy the app prepared for.

## Script hashes (sha256)
```
5ca397372f529b9e275c8c0f70989a163413ffe4edef1257b5d4c3f5fb86f02f  scripts/guest-backup.sh
080fb325b4ac2a63f303871f6274ff46f145fb4a569df0185feeb3d207e7f6f3  scripts/guest-churn.sh
b2d38f253e3cdbc3aa161793c933d6fc35522d6b5820233f5bed239fa167aa1e  scripts/guest-install.sh
ab3b7eade0729f5065317cbb7900655ced042ac60217ccfb68e471d32a239088  scripts/guest-measure.sh
0517657bfc0fd960f8c210676dca31490fc20c59acb7ffee7f773a158048045d  scripts/guest-restore.sh
e05eb10942468b97ecc31dfdee221dfb76920d8d3a9e42dc18d71f70ccba51c9  scripts/guest-verify.sh
08ebf8bd08cf2df17821433f98ed4b5cb6eb4a5b2e9209718553e0c691a88cf7  scripts/guest-workload.sh
9c11402de0cff6bc39c6e5c15a9f2709c41d159621848a2c7a71368e6830eca4  scripts/host-fetch.sh
ea63dd31938927c37798aca091efcfa5bcd3f9eaa982b0df6fd6974de42fe048  scripts/host-restore.sh
86b2bc64b2588ec93896be8a6d6542837418bbaea6bdfa735c7842bf5056db04  scripts/host-source.sh
dc9076d1a843d1b23544c0edc83437af55939dcdb1e4cad504e0f7151359a495  scripts/run-all.sh
5f6541412cfc1e4f0cab420e1c48255d4257ef2a43f4741b229a3c896b23ceb4  scripts/workload.yaml
```

## Files
`scripts/` (runnable), `logs/run-{sqlite,etcd}.log` (footprint + backup), `logs/restore-sqlite.log`, `logs/restore-etcd-attempt1.log` (failure), `logs/restore-etcd-attempt2.log`, `logs/etcd-cluster-reset-attempt2-excerpt.log`, `logs/{expected,actual}-{sqlite,etcd}.txt` (state fingerprints). Private VM addresses are replaced with `<vm-ip>`. Test Secrets were random throwaway values and appear only as truncated hashes. Deviation from the plan: etcd attempt 2 ran on a brand-new VM `kfr-etcd-restore2`, not on the uninstalled attempt-1 VM, so that "fresh" stays strictly true. All four VMs (`kfr-sqlite`, `kfr-etcd`, `kfr-sqlite-restore`, `kfr-etcd-restore2`) and the failed `kfr-etcd-restore` were deleted at 20:34 local time.
