# Pinned versions and hashes (LAB-fb3-mesh-nat)

Every download was made **inside** the disposable Lima VM by `scripts/fetch.sh` and checked against the pin below **and**, where upstream publishes one, the release's checksum file (`logs/fetch.log`). Nothing was installed on the Mac except the Lima VM itself.

| Item | Version / pin | sha256 (download) | Upstream check | Licence |
|---|---|---|---|---|
| Host | Apple M5 Max, Lima 2.3.0, `vz` | n/a | n/a | n/a |
| Lab VM | Lima `fb3lab`, `template:debian-13` (Debian 13.7 cloud image, aarch64), **4 vCPU / 4 GiB** (Pi 5 4 GB sizing), 20 GiB disk; kernel `6.12.115+deb13.1-cloud-arm64` | n/a | n/a | n/a |
| Headscale | **v0.29.7** (2026-10-30), commit `c9cf210b8bc84d13177e18b91f555788a44b47b6`, `headscale_0.29.7_linux_arm64` | `4357b38ac63c1e425f190819fd2ee078f13e01a6d7559b15811154e2475df5e4` | matches release `checksums.txt` and the GitHub asset digest | BSD-3-Clause |
| Tailscale client (`tailscale`, `tailscaled`) | **v1.104.6** (2026-11-11), `tailscale_1.104.6_arm64.tgz` from pkgs.tailscale.com/stable | `d0e4f297da3c428d02162c6235b9948e4ddc245c64502b7b05647da9b96a0971` | matches `tailscale_1.104.6_arm64.tgz.sha256` | BSD-3-Clause |
| DERP relay (`derper`) | built from module `tailscale.com@v1.104.6` (`h1:VjIuSsyFQ2Bp+HOtgbZCCJ7ZFTL+fULop5gmUF2bBIA=`, verified by the Go checksum database) with `CGO_ENABLED=0 GOTOOLCHAIN=local` | built binary `12ab8be0740e98645412926e33fe521a605af4f63f84054c586680dbbfc28fca` | `go install` verifies every module against `sum.golang.org` | BSD-3-Clause |
| Go toolchain (build only) | **go1.27.4** `linux-arm64` (Tailscale v1.104.6 `go.mod` needs ≥ 1.27.3) | `3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92` | equals the hash in `go.dev/dl/?mode=json` (go.dev publishes no separate checksum file) | BSD-3-Clause |
| nats-server | **v2.15.2** (the w8 pin), `nats-server-v2.15.2-linux-arm64.tar.gz` | `bc2c788dcbf2849af749564e06a0d48c19bced851f2d68a2e21c54d078949b28` | matches release `SHA256SUMS` | Apache-2.0 |
| natscli | **v0.5.1** (the w8 pin), `nats-0.5.1-linux-arm64.zip` | `91c661f1173ee9bfe07514eef55a29d25ac7757a0868c179e825eba976073adc` | matches release `SHA256SUMS` | Apache-2.0 |
| Debian tools in the VM | nftables 1.1.3-1, conntrack 1:1.4.8-2+b1, iproute2 6.15.0-1, tcpdump 4.99.5-2, nmap/ncat 7.95+dfsg-3, socat 1.8.0.3-1+deb13u1, openssl 3.5.7-1~deb13u3, jq 1.7.1-6+deb13u4, Python 3.13.5 | Debian archive (apt-verified) | n/a | various (tools only, not shipped) |

Installed binaries (sha256 after install): `headscale 4357b38a…`, `tailscale 2e547c5e8acb4e9dc7c3ae576c302346044bd2f30958515cca5b7a91fb5cd636`, `tailscaled 904044a58d6b22426fa2ff2307f774dc69c0edda0c5053bc3de53fb11a0b8e40`, `nats-server 9f03b5f7b53b1d3dd3474dce5744b4b55149ceafd8bbeded0ae4c27695c4aeb4`, `nats 11a53f1a178726c8be9730cf18db15c79e1acc0a635864b58db567504d7cd3f0`, `derper 12ab8be0…`.

`derper --version` prints `1.104.6-ERR-BuildInfo` because a binary built with `go install module@version` has no VCS stamp; `go version -m` shows the module version and hash above.

No secrets are in this folder: the lab CA, all TLS keys, the Headscale noise key, pre-auth keys and NATS passwords were generated inside the VM at run time and deleted with it.
