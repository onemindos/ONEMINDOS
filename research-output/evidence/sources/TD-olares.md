# Sources: TD-olares (Olares Tier A teardown)

Used in: `research-output/02-competitors/olares.md`. Claims: `evidence/claims/TD-olares.csv`.

**Archiving.** Code sources are pinned to commit SHAs, which serve as their archive. A Wayback Machine save request was refused by this environment's permission policy, so load-bearing web and doc sources were saved as text in `evidence/sources/TD-olares/` with sha256 hashes in `TD-olares/SHA256SUMS`. In the saved GitHub issue copies, user handles are replaced with `@[user]`, one in-cluster private IP is redacted, and one example email-style Olares ID in `network.md` is rewritten as `[at]` (public-repo rule). Hashes are of the redacted copies; the originals are at the URLs below.

## Code (pinned)

| Source | Pin | Accessed | Type | Archive |
|---|---|---|---|---|
| https://github.com/beclab/Olares | `e7fe1c9634f26530386c2033a33be7a9495704f3` (main, 2026-11-10) | 2026-11-10 | PRIMARY (source) | SHA pin; shallow clone outside repo |
| Olares release 1.12.7 | tag object `6ac3df1e…` → commit `e4a353dfe737d1dd924b609b7576c047153a85b9` | 2026-11-10 | PRIMARY-METADATA | SHA pin |
| https://github.com/beclab/Olares/releases (1.12.5/1.12.6/1.12.7 dates, 1.12.8-rc.1, daily builds) | GitHub API | 2026-11-10 | PRIMARY-METADATA | n/a (API) |
| https://github.com/beclab/apps (lares, router, n8n, homeassistant, ollamav2) | `37a1fb4f44b2428feb7978b25fdc798d6d6310ed` | 2026-11-10 | PRIMARY (source) | SHA pin |
| https://github.com/beclab/lares (repo metadata, license null) | GitHub API | 2026-11-10 | PRIMARY-METADATA | n/a |
| https://github.com/kubernetes/website/blob/4c77b36edb121506e7eb2983777e7c4b49f98ab1/data/releases/eol.yaml | `4c77b36e` | 2026-11-10 | PRIMARY | SHA pin |

Files read in `beclab/Olares@e7fe1c96` (all cited with line ranges in the teardown): `build/build.sh`; `.github/workflows/release.yaml`; `cli/pkg/terminus/tasks.go`; `cli/pkg/upgrade/{base.go,stage.go,plan.go,version.go,deenvy_edge_recreate.go}`; `cli/pkg/core/rollback/{base.go,interface.go}`; `cli/pkg/core/task/remote_task.go`; `cli/pkg/utils/lvm/tools.go`; `cli/pkg/common/common.go`; `cli/pkg/k3s/templates/{k3sServiceEnv.go,k3sService.go,hostMemoryProtection.go}`; `cli/pkg/etcd/templates/{backup_script.go,backup_service.go}`; `cli/apis/kubekey/v1alpha2/default.go`; `cli/pkg/web5/jws/checkjws.go`; `daemon/pkg/commands/upgrade/{upgrade.go,download_component.go}`; `daemon/pkg/commands/constants.go`; `daemon/pkg/cluster/clusterop/{upgrade.go,module_upgrade.go,signature_requirement.go}`; `daemon/internel/watcher/upgrade/upgrade_watcher.go`; `daemon/internel/apiserver/handlers/{middlewares.go,handler_did.go}`; `framework/oac/{chart.go,go.mod}`; `framework/oac/internal/resources/{hostnetwork.go,securitycontext.go}`; `framework/app-service/pkg/security/templates.go`; `framework/app-service/pkg/appwatchers/suspend.go`; `framework/app-service/.olares/config/cluster/deploy/appservice_deploy.yaml`; `framework/backup-server/pkg/{constant/constant.go,handlers/handler_app.go,handlers/helper.go,apis/sys.bytetrade.io/v1/backup_types.go}`; `framework/authelia/.olares/config/cluster/deploy/auth_backend_deploy.yaml`; `platform/tapr/.olares/config/cluster/deploy/lldap-deployment.yaml`; `framework/market/.olares/config/cluster/deploy/market_deploy.yaml`; `infrastructure/gpu/.olares/config/gpu/hami/{Chart.yaml,values.yaml}`; `framework/upgrade/README.md`; `README.md`; `LICENSE.md`.

## Docs (in-repo, pinned at the same SHA, saved copies)

| Source | Accessed | Type | Archive (saved copy) |
|---|---|---|---|
| `docs/developer/install/versioning.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_developer_install_versioning.md` |
| `docs/manual/olares/settings/update.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_manual_olares_settings_update.md` |
| `docs/manual/get-started/install-linux-iso.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_manual_get-started_install-linux-iso.md` |
| `docs/one/connect-two-olares-one.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_one_connect-two-olares-one.md` |
| `docs/one/upgrade-multi-node-cluster.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_one_upgrade-multi-node-cluster.md` |
| `docs/one/spec.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_one_spec.md` |
| `docs/developer/concepts/network.md` | 2026-11-10 | PRIMARY | `TD-olares/docs_developer_concepts_network.md` (redacted) |
| `LICENSE.md` (legacy "Olares License") | 2026-11-10 | PRIMARY | `TD-olares/LICENSE.md` |
| `docs/developer/concepts/system-architecture.md`, `docs/manual/get-started/install-olares.md`, `install-raspberry-pi.md`, `docs/manual/olares/settings/gpu-resource.md`, `docs/manual/update-guides/1.12.8.md`, `docs/one/update-firmware.md` | 2026-11-10 | PRIMARY | SHA pin only |

## Web

| Source | Accessed | Type | Archive (saved copy) |
|---|---|---|---|
| https://shop.olares.com/products/olares-one (Shopify `.js` product JSON: price, available, published_at) | 2026-11-10 | PRIMARY | `TD-olares/shop-olares-one.json` |
| https://github.com/beclab/Olares/issues/4268 | 2026-11-10 | PRIMARY (issue tracker) | `TD-olares/issue-4268.json` |
| https://github.com/beclab/Olares/issues/4171 | 2026-11-10 | PRIMARY (issue tracker) | `TD-olares/issue-4171.json` |
| https://github.com/beclab/Olares/issues/1716 | 2026-11-10 | PRIMARY (issue tracker) | `TD-olares/issue-1716.json` (redacted) |
| https://github.com/beclab/Olares/issues/4185 | 2026-11-10 | PRIMARY (issue tracker) | `TD-olares/issue-4185.json` (redacted) |
| https://github.com/beclab/Olares/issues/2350 | 2026-11-10 | PRIMARY (issue tracker) | `TD-olares/issue-2350.json` (redacted) |
| https://github.com/beclab/Olares (stars, forks, created date, contributors API) | 2026-11-10 | PRIMARY-METADATA | n/a (API) |

## Internal (reused, not re-derived)

| Source | Use |
|---|---|
| `research/competitors/olares.md` (OLA) | Built-in apps table, OAC field list, market contents, company/funding (VENDOR), Olares One pricing history, website stack |
| `context/03-repo-findings-index.md` | Verified Olares rows; HAOS/umbrelOS update and image facts used in the §7 comparison table |
