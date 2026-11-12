# Pinned versions and hashes (LAB-debian-rugix)

## Host and build VM

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2 (Darwin), 128 GB RAM |
| Lima | 2.3.0 (`vz`, arm64 guest) |
| QEMU (host, runs the test VMs) | 11.1.3 (Homebrew); firmware `edk2-x86_64-code.fd`, `edk2-aarch64-code.fd` from the same package |
| Build VM image | `debian-13-genericcloud-arm64-20261103-2651.qcow2`, sha512 `5d3ecec4…adc0c2` (full value in `scripts/lima-builder.yaml`) |
| Build VM kernel | 6.12.115+deb13.1-cloud-arm64 |
| Docker in build VM | Debian `docker.io` 26.1.5+dfsg1-9+deb13u1 (+ `docker-cli`) |
| amd64 emulation for the build | Debian `qemu-user-binfmt` (binfmt flags `POF`) |

## Image inputs

| Item | Version / pin | Source |
|---|---|---|
| Rugix Bakery | v0.9.4, image `ghcr.io/rugix/rugix-bakery:v0.9.4@sha256:abd9f86531f004d76ba73783e4e2d4f8046857c28a8786a435f67d45fc87a58b` | [C-LAB-debian-rugix-002] |
| `run-bakery` | upstream `container/run-bakery` at rugix-bakery@c43fdc1 (sha256 `b6afa99f…a7479`), default version changed to `v0.9.4` (ours: sha256 `35de11e9…0316a`) | S2 |
| Rugix Ctrl (in the image) | v1.4.0 (`core/rugix-ctrl` parameter `version = "v1.4.0"`, musl build from the GitHub release) | [C-LAB-debian-rugix-001] |
| Debian | 13 "trixie", from `snapshot.debian.org/archive/debian/20261109T000000Z/` | [C-LAB-debian-rugix-015], [C-LAB-debian-rugix-016] |
| Kernel in image | Debian `linux-image-{amd64,arm64}` 6.12.107+deb13 | observed (`uname -r`) |
| k3s | v1.37.2+k3s1 (f6973cb8) | [C-LAB-debian-rugix-014] |

k3s artifacts, verified at build time against the release's own `sha256sum-*.txt`:

| File | sha256 |
|---|---|
| `k3s` (amd64) | 265b3ee6a3198ef14033c63ef46cbb32370d83795199fb6d1b01f21575eddbda |
| `k3s-arm64` | a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b |
| `k3s-airgap-images-amd64.tar.zst` | 35a5af1e69b57b8b627a4f6b1c29ea104209b661067b8c97fd40dc3f860bfcd2 |
| `k3s-airgap-images-arm64.tar.zst` | ca384f1a77aa83024bd82ad26fa4774971adb038e656a3b5b9af926be445a442 |

## Build outputs (run 4, the passing run; sha256)

| Artifact | amd64 | arm64 |
|---|---|---|
| `v1/system.img` (factory image) | 36845df190abcb5af20297736a8b2d64b6f44bf3ef5237e6c1df3ee7e2b492a1 | c106c409280e55e5cde11ab0016a23e10320d0feb5d76abdb5fe202b3b22f51d |
| `v1/system.rugixb` | 6d0e3a6a5bab9b09f03d1c61a6ea64b11219a564c12e2297274d0b14b1606020 | c91747823d2a7a7c3d58196d49e43c0b4165651e3a1e5f653d97c1b4eaf79e00 |
| `v2good/system.rugixb` | cfe9663c226823ca377d4a165cc3dd2cea22a8744fd09198746303d3a17d6e7b | 0a9d53a43a9aa5ca8727f2668051a5e7f64455aa76a354cd4206a37ced803d3a |
| `v2bad/system.rugixb` | 2aab309daa03d749396c3342c30dcf90d25ffad5b85e9af00362cc384da041a2 | 08362b63054e25e38b93a89ba683fd1a1e9c1722823bf0d8ad5dc231876585a1 |
| `v2noagent/system.rugixb` | 5dbb59e0b775bdbc42ca7ef047ae3f8e94c870b4c42a5e01821f062dab6b062a | ec8e452bb917a7e500fe50b331d6ce5b5a1d6d8d3872baaa27a990a439a40e1b |
| `v2noagentnaive/system.rugixb` | c876012e1ec8cf3afd707c3868577535ef7e4b9067a0e9dd9183367f92a24c11 | 248984b914de864419ba7e61723a7643d7be722193b7a0584f5a85afe9c65773 |

Earlier runs' hashes are in `logs/build/*.trimmed.log`. The artifacts themselves are not committed (about 6 GB); rebuild them with `scripts/10-build.sh`.

Sizes: factory image about 2.0–2.2 GB raw (sparse), each full bundle about 600–640 MB.
**Reproducibility was not tested.** Every rebuild in this spike changed the shared base layer, so differing hashes between builds say nothing either way. Bakery documents a reproducible-builds mode (`docs-bakery/0.9/advanced/reproducible-builds.md`) that this spike did not enable. Note that `release.version` in `system-build-info.json` is a build timestamp (e.g. `20261111011135`).
