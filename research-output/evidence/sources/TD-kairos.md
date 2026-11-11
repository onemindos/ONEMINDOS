# Sources: TD-kairos (Kairos Tier B teardown)

**Accessed:** 2026-11-11 · **Claims:** `evidence/claims/TD-kairos.csv` (C-TD-kairos-001…051) · **Saved copies:** `evidence/sources/TD-kairos/` with `SHA256SUMS` (email addresses, adopter contact names and one user hostname were masked after download; the hashes are of the masked copies; see `NOTE.txt`). No Wayback captures were requested (denied in this environment).

## Code (pinned)

| Repo | Commit | What it is | Local clone |
|---|---|---|---|
| kairos-io/kairos | `6f33334a6a6c88a4a38c0b7ec4df1ab0334b830d` (tag v4.4.0, 2026-10-26) | Monorepo: agent, immucore, kcrypt, sdk, kairos-init, installer, provider | `<lab-dir>/src/kairos-io_kairos-v4.4.0` |
| kairos-io/kairos | `fa6801435880cdb4fd0c7c3e42577cb5974a3555` (master, 2026-11-10) | Used only to check that `images/Dockerfile` moved its default kairos-init to v4.4.0 after the tag | `<lab-dir>/src/kairos-io_kairos` |
| kairos-io/kairos-docs | `b1bf8bedc43697ce552b988a74f0f4e76afaeddf` (2026-11-06) | Documentation source for kairos.io | `<lab-dir>/src/kairos-io_kairos-docs` |
| kairos-io/kairos-operator | `7317f4c1ae6ea7e063b8e20ca362aa17f4e33ad4` (2026-11-10) | NodeOp / NodeOpUpgrade CRDs | `<lab-dir>/src/kairos-io_kairos-operator` |
| kairos-io/community | `66ce4dd173f71a968b0a37ac8ec02843927d625a` (2026-10-19) | MAINTAINERS, ADOPTERS, GOVERNANCE | `<lab-dir>/src/kairos-io_community` |
| kairos-io/AuroraBoot | `c99b1ac6aefad724a73df2cf6054097514358def` (2026-11-10) | Image/ISO/UKI builder and netboot server (cloned; licence checked via API only) | `<lab-dir>/src/kairos-io_AuroraBoot` |

## Code files cited (all at kairos-io/kairos@6f33334a unless noted)

| Path | Topic | Claims |
|---|---|---|
| `images/Dockerfile#L1-L37` | Image build | 007 |
| `kairos-init/pkg/values/values.go#L30-L46, #L68-L78` | Distros, models | 008, 009 |
| `kairos-init/pkg/values/packagemaps.go#L957-L976` | Debian Pi kernels | 010 |
| `kairos-init/pkg/bundled/jetson_qspi.go#L3-L18` | Jetson bootloader / capsule | 017 |
| `kairos-init/pkg/bundled/cloudconfigs/13_nvidia_qspi.yaml#L1-L37` | Jetson firmware on upgrade | 018 |
| `agent/pkg/action/upgrade.go#L80-L97, #L186-L240` | A/B rotation | 020 |
| `kairos-init/pkg/bundled/cloudconfigs/08_grub.yaml#L5-L44, #L79-L131` | GRUB boot assessment | 021 |
| `agent/pkg/utils/common.go#L648-L673`, `kairos-init/.../08_efi_assessment.yaml#L1-L35` | UKI boot counting | 023 |
| `agent/pkg/elemental/elemental.go#L451-L462`, `sdk/types/config/config.go#L48-L50` | Opt-in cosign | 026 |
| `agent/pkg/uki/upgrade.go#L220-L256` | Same-signer rule | 027 |
| `sdk/bundles/bundles.go#L25, #L182-L282` | Bundles | 037 |
| `agent/pkg/action/sysext.go#L17-L50` | System extensions | 038 |
| `kairos-init/pkg/bundled/cloudconfigs/99_sysext.yaml#L47-L110` | sysext image policy | 039 |
| `sdk/extensions/catalog.go#L14-L92` | Extension catalog | 040 |
| `provider/README.md#L7-L27` | Provider plugin contract | 042 |
| `immucore/README.md#L253-L275` | Blocked-boot reboot, TPM | 044 |
| kairos-operator@7317f4c1 `api/v1alpha1/nodeopupgrade_types.go#L9-L120` | Fleet upgrade CRD | 029 |

## Web and docs sources

| URL | Type | Saved copy | Claims |
|---|---|---|---|
| https://api.github.com/repos/kairos-io/kairos/releases | PRIMARY-METADATA | (API, not saved) | 001 |
| https://github.com/kairos-io/kairos/releases/tag/v4.4.0 | PRIMARY | `kairos-v4.4.0-release-notes.md` | 034 |
| https://www.cncf.io/projects/kairos/ | PRIMARY | `cncf-projects-kairos-2026-11-11.txt` | 004 |
| https://www.spectrocloud.com/solutions/kairos-support | PRIMARY (vendor pricing page) | `spectrocloud-kairos-support-2026-11-11.txt` | 049 |
| kairos-docs `docs/upgrade/boot_assessment.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_upgrade_boot_assessment.md` | 022, 024 |
| kairos-docs `docs/examples/boot_assessment_trusted_boot.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_examples_boot_assessment_trusted_boot.md` | 025 |
| kairos-docs `docs/installation/edge-devices/raspberry.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_installation_edge-devices_raspberry.md` | 011 |
| kairos-docs `docs/installation/edge-devices/nvidia-jetson-images.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_installation_edge-devices_nvidia-jetson-images.md` | 015 |
| kairos-docs `docs/installation/edge-devices/nvidia_orin_nx.md` | PRIMARY | (git SHA only) | 016 |
| kairos-docs `docs/reference/featuresets.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_reference_featuresets.md` | 013, 014 |
| kairos-docs `docs/architecture/immutable.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_architecture_immutable.md` | 019, 051 |
| kairos-docs `docs/installation/check-the-signatures.md` | PRIMARY | `kairos-docs@b1bf8bed__docs_installation_check-the-signatures.md` | 028 |
| kairos-docs `operator-docs/nodeop-upgrade.md` | PRIMARY | `kairos-docs@b1bf8bed__operator-docs_nodeop-upgrade.md` | 029 |
| kairos-docs `docs/examples/kubeadm-provider.md` | PRIMARY | (git SHA only) | 043 |
| kairos-docs `docs/installation/` (index of install pages) | PRIMARY | (git SHA only) | 045 |
| kairos-docs `quickstart/index.md#L77-L83` | PRIMARY | (git SHA only) | 046 |
| kairos-docs `docs/integrations/localai.md` | PRIMARY | (git SHA only) | 050 |
| kairos-docs blog 2025-08-08 commercial support | PRIMARY | `kairos-docs@b1bf8bed__blog_2025-08-08-commercial-support-by-spectro-cloud.md` | 048 |
| kairos-docs blog 2025-12-17 Hadron | PRIMARY | `kairos-docs@b1bf8bed__blog_2025-12-17-introducing-hadron-...md` | 047 |
| community `MAINTAINERS.md`, `ADOPTERS.md` | PRIMARY | `community@66ce4dd1__ADOPTERS.md` (contacts masked) | 005, 006 |
| GitHub issues #2010, #2864, #4345, #4969, #5032, #5923, #5965, #6018, #6027 | PRIMARY | `issue-<n>.md` (all saved) | 012, 024, 030–033, 035, 041 |
