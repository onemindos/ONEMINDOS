# Sources: LAB-k3s-footprint-restore

Saved copies and checksums live in `evidence/sources/LAB-k3s-footprint-restore/` (`SHA256SUMS.txt` lists every file).

| Source | Accessed | Type | Archive |
|---|---|---|---|
| https://docs.k3s.io/datastore/backup-restore | 2026-11-10 | PRIMARY (docs) | https://web.archive.org/web/20261111011629/https://docs.k3s.io/datastore/backup-restore ; saved `datastore_backup-restore.html` sha256 3301a5d8b03ff12a004323c22d0724c6444aa5e54615acd12b8451d7b3bd3a90 |
| https://docs.k3s.io/cli/etcd-snapshot | 2026-11-10 | PRIMARY (docs) | https://web.archive.org/web/20261111011648/https://docs.k3s.io/cli/etcd-snapshot ; saved `cli_etcd-snapshot.html` sha256 97dfe3c8f2359710e52ea27a0cbdb41a027ed9156dcfe482f31fc9d983dba9ab |
| https://docs.k3s.io/reference/resource-profiling | 2026-11-10 | PRIMARY (docs) | https://web.archive.org/web/20261111011706/https://docs.k3s.io/reference/resource-profiling ; saved `reference_resource-profiling.html` sha256 0e5f2fed99f9e145c33c62687d82a62e4d5016ac0097ebdf277a8f0a5d5a98d4 |
| https://docs.k3s.io/installation/requirements | 2026-11-10 | PRIMARY (docs) | Wayback save not made (the request was denied by this session's permission system); saved `installation_requirements.html` sha256 34a53f14763b344756cc52f7165fbddac23180210b500993516fbb6fd2ea2c29 |
| https://github.com/k3s-io/k3s/releases/tag/v1.37.2%2Bk3s1 (via `gh api`) | 2026-11-10 | PRIMARY-METADATA | release checksum file saved as `k3s-v1.37.2+k3s1-sha256sum-arm64.txt` sha256 b017cfc151c92e30530c7d1830048ee5afabe53a4520ae513d584b7b2c2ee564 |
| https://raw.githubusercontent.com/k3s-io/k3s/v1.37.2%2Bk3s1/install.sh | 2026-11-10 | PRIMARY (code, read before running in VM) | sha256 ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b (pinned in `scripts/host-fetch.sh`) |
| https://github.com/restic/restic/releases/tag/v0.19.1 (via `gh api`) | 2026-11-10 | PRIMARY-METADATA | `restic-0.19.1-SHA256SUMS` sha256 fb520966ee01d2a3d4219c66762c66efa56300833b6f639f36082b7462f91cb8 |
| k3s-io/k3s@f6973cb850e9b245585363d15bde80904ac862fd: `pkg/cluster/managed.go#L151`, `pkg/cluster/storage.go#L341`, `pkg/cluster/bootstrap.go#L269-L280`, `pkg/cluster/bootstrap.go#L378-L390`, `pkg/util/token.go#L25-L39`, `pkg/etcd/etcd.go#L1540` | 2026-11-10 | PRIMARY (code at tag v1.37.2+k3s1) | permalinks pinned to SHA; shallow clone in `.lab/src/k3s` (outside repo) |
| Lab logs `evidence/lab/k3s-footprint-restore/logs/*` | 2026-11-10 | PRIMARY (own measurement) | in repo |
| `context/03-repo-findings-index.md`, `research/platform/verify-updates-rollback-backups-security.md` §1, §2, §6, §7 | 2026-11-10 | Internal (prior VERIFIED research, used only for the competitor table) | in repo |
