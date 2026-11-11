# W5 lab spike: k3s datastore + app-volume restore onto a fresh VM

Written 2026-11-10 BEFORE running (brief §7 item 5; DC-11 / Q129 / Q136).

## Goal
Show whether a single-node k3s box on the default SQLite datastore can be backed up and restored
onto a different, freshly installed machine, together with its app volumes (restic), and whether
the same box can later be converted in place to embedded etcd and restored from `k3s etcd-snapshot`.

## Setup
- Two disposable Lima VMs (vz, aarch64, Debian 13 cloud image, 2 vCPU / 4 GiB / 20 GiB),
  `w5a` and `w5b`. Only one host directory is mounted (`shared/`, writable). No host home mount.
- k3s pinned to v1.37.2+k3s1 (install script hashed before use, binary checked by the script's
  own sha256 check). restic from Debian 13 (`apt`), version recorded in the log.
- Workload: namespace `demo` with a ConfigMap, a Secret (k3s started with `--secrets-encryption`,
  so the Secret is only readable if the token/encryption config is restored), and a Pod writing a
  random marker to a local-path PVC.

## Hypotheses
- H1: `k3s etcd-snapshot save` fails on a SQLite server ("etcd datastore disabled").
- H2: An online `sqlite3 .backup` of `server/db/state.db` + `server/token` + restic of
  `/var/lib/rancher/k3s/storage` restores onto a fresh VM, and the Pod comes back with the same
  marker, PROVIDED the node name is kept (local-path PVs carry node affinity to the old hostname).
- H3: Restarting the restored SQLite server with `--cluster-init` migrates all objects to etcd
  in place (log line "Migrating content from sqlite to etcd", `state.db.migrated` left behind).
- H4: After conversion, `k3s etcd-snapshot save` works, and `--cluster-reset
  --cluster-reset-restore-path` + `--token` restores it onto the other (wiped) VM, with app data
  from restic.

## Pass / fail criteria
- PASS H1: the save command exits non-zero and logs the datastore-disabled error.
- PASS H2/H4: after restore, `kubectl -n demo get cm,secret` returns the objects, the Secret value
  decodes to the original, and the restored Pod reads back the original marker. FAIL if any is missing.
- PASS H3: all `demo` objects are present after the restart, and the migration log line exists.
- Also recorded (not pass/fail): wall-clock time of each backup/restore step; block-device sectors
  written during 10 minutes of idle on SQLite vs etcd (indicative only, VM virtio disk, not flash).
