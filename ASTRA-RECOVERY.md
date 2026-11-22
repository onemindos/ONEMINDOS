# Astra-1 source recovery

The linked GitHub branches retain the source code and tests from the Atlas close-out. Each pull request carries its own acceptance results and current CI status. Claude reviews and merges the individual drafts into `release/next`.

| Issue | Source |
| --- | --- |
| #241 scheduled snapshots | [Claude-owned PR #833](https://github.com/onemindos/ONEMINDOS/pull/833) and the [original signed commit](https://github.com/onemindos/ONEMINDOS/commit/0fd4bafe03431bfcb62a519d1e993fd97ada88ae), retained by [the recovery branch](https://github.com/onemindos/ONEMINDOS/tree/codex/recovery-241-history-20261122) |
| #757 Atlas design | [PR #834](https://github.com/onemindos/ONEMINDOS/pull/834). The requested ten-pack verification and design guide updates are on the branch. |
| #651 geo data model | [Sites PR #848](https://github.com/onemindos/ONEMINDOS/pull/848) and the [separate signed asset-position implementation](https://github.com/onemindos/ONEMINDOS/tree/feat/geo-position-stream). The position slice follows the sites merge. |
| #684 notification catalogue | [PR #850](https://github.com/onemindos/ONEMINDOS/pull/850) |
| #505 Settings Care | [PR #851](https://github.com/onemindos/ONEMINDOS/pull/851) |
| #500 Home widgets | [PR #852](https://github.com/onemindos/ONEMINDOS/pull/852) |
| #515 default apps | [PR #866](https://github.com/onemindos/ONEMINDOS/pull/866) |
| #638 App SDK | [Dev-loop PR #903](https://github.com/onemindos/ONEMINDOS/pull/903) and the [signed module generator](https://github.com/onemindos/ONEMINDOS/tree/feat/app-module-cli). The generator awaits [shared permission-test registration](https://github.com/onemindos/ONEMINDOS/issues/638#issuecomment-7080554392). |

Sprint 1 landed through [#793](https://github.com/onemindos/ONEMINDOS/pull/793), [#796](https://github.com/onemindos/ONEMINDOS/pull/796), [#797](https://github.com/onemindos/ONEMINDOS/pull/797), [#800](https://github.com/onemindos/ONEMINDOS/pull/800), [#803](https://github.com/onemindos/ONEMINDOS/pull/803), [#804](https://github.com/onemindos/ONEMINDOS/pull/804), [#807](https://github.com/onemindos/ONEMINDOS/pull/807) and [#812](https://github.com/onemindos/ONEMINDOS/pull/812).

## Integration and verification copies

[The exact combined Home, Care and Default Apps checkout](https://github.com/onemindos/ONEMINDOS/commit/d610c33b42c9097e612903110d204b901e7d101e) preserves the three-way integration used for verification. Its OpenAPI document was regenerated after combining the gateway changes. Use the individual PRs to continue development.

The archival patches below recreate source versions from earlier test exports. Each was applied to its listed base in an isolated Git index and the resulting source blobs were checked byte for byte. To inspect one in a disposable checkout of its base, use `git apply --check` with the patch file.

| Archive | Base commit | Contents |
| --- | --- | --- |
| [Home command bar](recovery/verification/home-command-bar.patch) | `f77fc628` | Combined Home widgets and command-bar components. |
| [Default apps gateway proof](recovery/verification/default-apps-core.patch) | `023677d1` | Earlier gateway, schema and test snapshot. |
| [Default apps web proof](recovery/verification/default-apps-web.patch) | `023677d1` | Earlier web verification snapshot. |
| [Scaffold smoke proof](recovery/verification/generator-smoke.patch) | `8fdaaf05` | The generated module, its tests and its generated OpenAPI route from the clean-checkout smoke test. |

## Outstanding dependencies

The issue threads carry the evidence for [#608 node liveness](https://github.com/onemindos/ONEMINDOS/issues/608#issuecomment-7078183187), [#682 private notification events](https://github.com/onemindos/ONEMINDOS/issues/682#issuecomment-7078778857), [#504 rescue Help](https://github.com/onemindos/ONEMINDOS/issues/504#issuecomment-7078509994), [#650 Notes search](https://github.com/onemindos/ONEMINDOS/issues/650#issuecomment-7078801568), [#725 verdict requirements](https://github.com/onemindos/ONEMINDOS/issues/725#issuecomment-7080339489), [#728 device permissions](https://github.com/onemindos/ONEMINDOS/issues/728#issuecomment-7080370776) and [#758 Atlas stack readiness](https://github.com/onemindos/ONEMINDOS/issues/758#issuecomment-7080300081). The shared gateway CI reproductions are on [#505](https://github.com/onemindos/ONEMINDOS/issues/505#issuecomment-7080319179).
