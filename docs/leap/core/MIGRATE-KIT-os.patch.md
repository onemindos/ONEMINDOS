<!-- SPDX-License-Identifier: Apache-2.0 -->
# os/ changes requested by the migration kit (feat/migrate-kit)

The image-line stream owns `os/`. The migration kit needs one pin recorded there so the OS image
can pre-pull (or airgap) the helper image and Renovate can watch it. Nothing else in `os/` changes.

**Why:** the copy step runs `docker.io/restic/restic:0.19.1` as the helper pod (old cluster) and the
restore Job (box). The gateway default (`ONEMIND_MIGRATE_HELPER_IMAGE`) is pinned by digest; the
lock file should carry the same pin so the two never drift. restic 0.19.1 matches the binary the
backup agent already pins (`internal/backup/pins.go`, BSD-2-Clause).

**Digest source:** registry-1.docker.io manifest list for `restic/restic:0.19.1`, read 2026-11-12
(platforms linux/amd64, linux/arm64, linux/arm/v7, linux/386).

```diff
--- a/os/versions.lock.yaml
+++ b/os/versions.lock.yaml
@@ tools:
     k3s_image: docker.io/rancher/k3s:v1.37.2-k3s1@sha256:21ea6e0fac4e3930c2ce8aa40ddd41a8b18cb3e9a0222c030dc005e7e88c4332   # k3d smoke cluster, same k3s as above
+  migrate:   # core/onemind_core/migrate/service.py RESTIC_IMAGE; helper pod and restore Job of CORE-DEPLOY-6
+    restic_image: docker.io/restic/restic:0.19.1@sha256:136600b6ff6843d61d355f7f71f460a166429f35de6fd11b568fece3c9a4d510   # BSD-2-Clause, same restic as internal/backup/pins.go
```

When this lands, a test in `test/unit/test_versions_lock.py` (image-line stream) can assert that
`RESTIC_IMAGE` in `core/onemind_core/migrate/service.py` equals `tools.migrate.restic_image`.
