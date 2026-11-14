<!-- SPDX-License-Identifier: Apache-2.0 -->
# NET-P2: changes the image line (`os/`) needs

**From:** branch `feat/net-part2` (networking part 2: CORE-NET-11, CORE-NET-12, CORE-NET-13). That
stream may not edit `os/`, so the exact changes are written here for the image-line stream to apply.
**Proven on:** the developer install (`deploy/install.sh`) in lab `research-output/evidence/lab/net-p2/`.

> **In plain words.** The installer now sets up the private mesh, the encrypted node links and HTTPS
> on a stock Debian. The OneMind image must carry the same pieces, at the same pinned versions, so
> an image-installed box and a developer-installed box behave the same. Nothing here changes a
> founder decision.

## 1. `os/versions.lock.yaml`: new keys

Values are the ones in `deploy/pins.env` (FB-3 lab T0 checked the arm64 pins inside a VM; the
amd64 values come from the same release files). `deploy/check-pins.py` should then compare them the
way it compares k3s.

```yaml
mesh:
  headscale:
    version: 0.29.7
    commit: c9cf210b8bc84d13177e18b91f555788a44b47b6
    url: https://github.com/juanfont/headscale/releases/download/v0.29.7/
    amd64: {headscale_0.29.7_linux_amd64: e827fc9b12d958bc95b081c4401dd63f8e0471d025b45b508535a920532150a8}
    arm64: {headscale_0.29.7_linux_arm64: 4357b38ac63c1e425f190819fd2ee078f13e01a6d7559b15811154e2475df5e4}
    licence: BSD-3-Clause
    source: release checksums.txt, read 2026-11-12; research-output/evidence/lab/fb3-mesh-nat/versions.md
  tailscale:
    version: 1.104.6
    url: https://pkgs.tailscale.com/stable/
    amd64: {tailscale_1.104.6_amd64.tgz: 82a85429f733e52fd1a95dedb2c8dd8cd46d6603504e566a56b1779c9a7a4809}
    arm64: {tailscale_1.104.6_arm64.tgz: d0e4f297da3c428d02162c6235b9948e4ddc245c64502b7b05647da9b96a0971}
    licence: BSD-3-Clause
    source: tailscale_1.104.6_<arch>.tgz.sha256, read 2026-11-12
```

NATS stays at the `deploy/pins.env` value (v2.15.2); it is not in the lock yet either.

## 2. `os/rootfs/packages/debian-common.txt` (and `ubuntu-common.txt`)

Add one line:

```
avahi-daemon avahi-utils libnss-mdns sqlite3
```

`avahi-utils` gives `avahi-publish`, which the gateway runs for `onemind.local` and
`<app>.<box>.local`; `sqlite3` makes the consistent Headscale database copy for backups
(NETWORKING.md §4.5). `iptables` is already in the list (tailscaled and kube-proxy use it).

## 3. Units and drop-ins the image installs (copy from `deploy/systemd/` and `deploy/install.sh`)

| File | Machine | Source |
|---|---|---|
| `onemind-headscale.service` | hub | `deploy/systemd/` |
| `onemind-nats-accounts.path`, `onemind-nats-reload.service` | hub | `deploy/systemd/` |
| `onemind-nats-leaf.service` + system user `onemind-nats` | node | `deploy/systemd/`; `install.sh` `nats_leaf_install` |
| `tailscaled.service` from the Tailscale tarball, `/etc/default/tailscaled` (`FLAGS="--no-logs-no-support"`), drop-in `tailscaled.service.d/onemind.conf` (`SSL_CERT_FILE=/etc/onemind/identity/ca.pem`, `TS_NO_LOGS_NO_SUPPORT=true`) | every machine | `install.sh` `tailscale_install` |
| `k3s.service.d/onemind-mesh.conf`, `k3s-agent.service.d/onemind-mesh.conf` (`After=tailscaled`, `ExecStartPre=onemindd mesh wait-ip --timeout 120s`) | hub, worker | `install.sh` `k3s_mesh_dropin` |
| `onemind-nats.service.d/onemind-mesh.conf` (wait-ip, `LoadCredential` of the NATS TLS files) | hub | `install.sh` `nats_install` |

The gateway unit gains `CAP_NET_BIND_SERVICE` (HTTPS on 443, redirect on 80) and
`StateDirectoryMode=0751` (the hub NATS reads `nats/accounts.conf` inside it).

## 4. First boot on the hub (the order matters)

The image's first-boot service should run the same order as `install.sh --role hub`, because k3s
node IP and flannel backend are cluster-creation settings (NETWORKING.md §8):

1. box CA and certificates: `python -m onemind_core.ca --dir /var/lib/onemind/tls --box <box> --control` (as `onemind`);
2. Headscale config (`install.sh` `headscale_install` heredoc), start it;
3. hub enrolls itself (`mesh_hub`), Headscale API key for the gateway (0600, `onemind`);
4. NATS leaf certificate for the mesh IP (`... --nats-ip <mesh ip>`);
5. k3s server with `node-ip`/`advertise-address` = mesh IP, `flannel-backend: wireguard-native`,
   `flannel-iface: tailscale0`, `disable: [traefik, servicelb]`;
6. hub NATS (`nats.conf` from `nats_install`), then the gateway with the `ONEMIND_NET_*`,
   `ONEMIND_MESH_*`, `ONEMIND_FABRIC_*` settings of `gateway_service`.

## 5. Image tests to add

- `ss -ltn`: `4222` only on `127.0.0.1`, `7422` only on the mesh IP; no Traefik Service.
- `ip -d link`: `flannel-wg` present, no VXLAN link (H-17).
- `tailscaled` has `--no-logs-no-support` and the box CA as `SSL_CERT_FILE`.
