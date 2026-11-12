<!-- SPDX-License-Identifier: Apache-2.0 -->
# Images: every deployment boots straight into OneMind (CORE-IMAGE)

**Date:** 2026-11-12 · **Status:** built (x86_64-efi, arm64-efi, vm, vm-do from one Containerfile); rpi5 and Jetson not yet · **Founder request:** 2026-11-12, "images for every deployment that boot straight into OneMind" · **Serves:** D-007, brief 30 B2.1/B2.2 (layers "… → gate → `onemindd` → …"), B4.2 (updater in the image), BD-DO-1, BD-08; contract `sdk/contracts/poc-v0.md` §1–§3 · **Tests:** `test/qemu/CRITERIA-FIRSTBOOT.md` (F0–F4, pre-registered) on top of `test/qemu/CRITERIA.md` (T0–T11)

> **Explain it like I am the founder**
> Before this change the image was a bare, safe Linux: read-only, A/B updates, k3s and the health gate, but no OneMind on it. Now the same image carries OneMind itself: the node agent, the bus (NATS), the gateway with the dashboard, and the updater.
> Nothing runs until the box knows **what it is**: a **hub** (dashboard + bus), a **worker** (joins a hub) or a **leaf** (an edge device that forwards to a hub). It learns that at first boot from a cloud seed, from a small text file you edit on the flashed disk, or from a setup page at `http://onemind.local:8080/`.
> Everything the box creates (its secrets, database, tokens) lives on the data partition, so an OS update or a rollback never touches it.

## 1. Where each deployment stands

| Deployment | Board | Built by CI | Boots OneMind (QEMU) | Real hardware | Next step |
|---|---|---|---|---|---|
| Beelink / any UEFI x86 PC | `x86_64-efi` | yes (`image.yml`) | F0–F4 (§6) | kit LT-X86-01, not yet run | founder runs LT-X86-01 with this image |
| Generic arm64 UEFI (servers, VMs, Ampere) | `arm64-efi` | yes | F0–F4 (§6) | none | — |
| Local VMs (UTM, Proxmox, VirtualBox; qcow2/vhdx/vmdk/vdi/ova) | `vm` | yes | same tree as x86_64-efi; battery not run on `vm` | n/a | — |
| DigitalOcean droplet (BIOS, cloud-init) | `vm-do` | yes | T0–T5 + TC1; first-boot test not run on it yet (cloud-init's user-data path is supported, §3) | kit LT-DO-01, not yet run | founder runs LT-DO-01; put `onemind: {role: hub}` in the droplet's user-data |
| Raspberry Pi 5 | `rpi5` | **no**: board not written (`tryboot` A/B, BD-07) | — | LT-PI5-01 uses the research scripts | write `os/boards/rpi5` |
| Jetson Orin (dev kit) | `jetson-orin` | **no**: NVIDIA L4T + `ROOTFS_AB`, never published (D-007, Z-01) | — | LT-JET-01 steps 1, 4, 5 | B4.7 Jetson backend; until then OneMind installs on L4T with `deploy/install.sh` (developer install) |
| Machines OneMind does not own | none | — | — | — | developer install (`deploy/install.sh`, branch `feat/deploy-v0`) |

## 2. What is in the image (the OneMind layer)

Built by `os/rootfs/Containerfile` in builder stages; every download is pinned (version + sha256) in `os/versions.lock.yaml` → `onemind_layer` and fetched by `os/rootfs/fetch-onemind.sh`.

| Path in the slot (read-only) | What | Built from |
|---|---|---|
| `/usr/bin/onemindd`, `/usr/bin/onemind` | node agent (+ `onemindd update`) and CLI, static | `cmd/`, `internal/` with Go 1.26.11 (`go mod verify`, `-trimpath`) |
| `/usr/bin/nats-server` | NATS v2.15.2 | release tarball, tarball **and** binary sha256 checked |
| `/usr/lib/onemind/gateway/{python,venv}` | gateway (`onemind_core`) in a venv on Python 3.12.16 (python-build-standalone, fetched and hash-checked by uv 0.13.7) | `core/uv.lock` exported with hashes by uv on the build machine, installed by the target's own pip with `--require-hashes --only-binary :all:` (uv crashes under qemu-user, so it never runs emulated) |
| `/usr/lib/onemind/dashboard/` | built dashboard, served by the gateway at `/` | `dashboard/` with Node v24.22.3, `npm ci` from `package-lock.json` |
| `/usr/lib/onemind/apps/`, `/usr/lib/onemind/sdk/schema/` | Market seed catalog and app manifest schema | `apps/`, `sdk/schema/` |
| `/usr/lib/onemind/tuf/<channel>/root.json` | the update channel's trust root (os/update/CHANNEL.md §2) | placed by the release pipeline; **empty in dev images**, so the updater stays inert |
| `/usr/lib/onemind/onemind-firstboot`, `onemind-setup` | first boot and setup wizard (Python, stdlib + PyYAML) | `os/rootfs/layers/onemind/` |
| `/usr/lib/onemind/manifests/onemind-gateway.yaml` | the gateway's Kubernetes identity (admin role + namespaces, not cluster-admin) | applied by k3s |
| `/etc/avahi/services/onemind.service` + `avahi-daemon` | the box answers as `onemind.local`, announces :8080 | Debian package |
| units: `onemind-firstboot` (enabled), `onemind-nats`, `onemindd`, `onemind-gateway`, `onemind-gateway-kube`, `onemind-update`, `onemind-setup` (all **disabled**) | | `os/rootfs/layers/onemind/usr/lib/systemd/system/` |
| health gate: `onemind-health-gate`, `onemind-local-api` (enabled, unchanged) | | `os/gate/` |

The image units are the developer-install units (`deploy/systemd/`) adapted to a read-only root: binaries in `/usr/bin`, no `StateDirectory` (it would write to `/var/lib` on the read-only slot), settings and state on `/data`.

## 3. First boot

`onemind-firstboot.service` runs on **every** boot (after `/data` is mounted):

1. **Already configured** (`/data/onemind/firstboot/state.json` exists): print `ONEMIND-FIRSTBOOT: already configured role=…` and start the role's units. Nothing is regenerated.
2. Otherwise read the settings, first match wins:
   1. **cloud-init / NoCloud seed:** the `onemind:` mapping of the `#cloud-config` user-data. On cloud boards cloud-init's copy (`/var/lib/cloud/instance/user-data.txt`); elsewhere a filesystem labelled `CIDATA`/`cidata` is mounted read-only and read directly.
      ```yaml
      #cloud-config
      onemind:
        role: hub          # hub | worker | leaf
        name: Home         # optional
      ```
   2. **`/boot/efi/onemind.conf`:** every image ships this file on its FAT partition (any computer can open it after flashing), all lines commented out. Set `role = hub` (and for a worker or leaf `hub = …` and `join_token = …`). After use it is renamed `onemind.conf.applied`.
   3. **Nothing:** start the setup wizard on `:8080` (`http://onemind.local:8080/`): pick the role, and for a hub the page shows the owner token once. The wizard then exits and the gateway takes the port.
3. **Configure** (writes, in this order, `state.json` last so a power cut just reruns it):
   - a node id (`/data/onemind/etc/node-id`; the read-only root has no persistent machine-id, so the agent and the gateway are told this id),
   - NATS credentials (per-service passwords; hub: a `node` join token for workers and leaves),
   - the per-box CA in `/data/onemind/identity/` (EC P-256, 10 years; kept if a CA module created it first, NETWORKING.md §8),
   - hub: the owner token (only its sha256 is stored, `core/onemind_core/auth.py`), `gateway.env`, the gateway's data directory,
   - prints `ONEMIND OWNER TOKEN: …` and the join token **on the console only** (never in the journal); the wizard gets it through `/run` (tmpfs, deleted when shown).
4. **Start the role's units** (runtime `systemctl start`; enabling would write to the read-only `/etc`):

| Role | Units | NATS |
|---|---|---|
| hub | `onemind-nats`, `onemindd`, `onemind-gateway`, `onemind-gateway-kube` | server on :4222 (clients) and :7422 (leaf nodes), user/password per service |
| worker | `onemindd` | publishes to the hub's NATS (`nats://node:<join token>@<hub>:4222`) |
| leaf | `onemind-nats` (leaf mode), `onemindd` | local NATS on 127.0.0.1:4222, forwards to `nats-leaf://<hub>:7422` |

## 4. State on /data (read-only root)

| Path | Contents | Mode |
|---|---|---|
| `/data/onemind/firstboot/state.json` | role, source, node id, when | 0644 |
| `/data/onemind/etc/` | `role`, `node-id`, `onemindd.env`, `gateway.env`, `nats.conf` | dir 0700, secrets 0600 |
| `/data/onemind/secrets/join-token` | hub's join token | 0600 |
| `/data/onemind/identity/` | `ca.pem`, `ca.key` | 0700 / key 0600 |
| `/data/onemind/gateway/` | `tokens.yaml` (hashes only), `onemind.db`, `audit.jsonl`, `kubeconfig` | owned by `onemind` (uid/gid 961, fixed so updates keep ownership) |

An A/B update replaces only the slot; F4 proves `/data` and the owner token survive it.

## 5. v0 shortcuts (known, tracked)

- **NATS:** user/password, no TLS, no per-subject permissions; one shared `node` join secret for all workers and leaves. NETWORKING.md N-R6 (TLS with the box CA, per-node credentials) replaces it.
- **Workers still run their own k3s server** (the base image's k3s unit and the health gate's G1–G3 assume a server). Joining the hub's cluster as a k3s agent needs a gate variant for agents.
- **Wizard:** plain HTTP, first come first served on the LAN (the HAOS onboarding model) until the owner passkey flow (D-B9.1, BM2).
- **mDNS names:** every box is `onemind`; a second box on the same LAN gets avahi's `onemind-2.local`.
- **Health gate G6** still uses the stand-in local API (`onemind-local-api`); switching it to `onemindd`'s `/healthz` is a separate gate change with its own battery run.
- **Updater:** inert until the release pipeline ships a channel's `root.json`.

## 6. Test results (2026-11-12, local Lima VM on an Apple-silicon Mac)

Criteria `test/qemu/CRITERIA-FIRSTBOOT.md` (sha256 `4a312852…5a`, committed before the code). Raw results: `test/qemu/results/`. Build: Debian 13 leg, snapshot `20261111T000000Z`, rootfs built in the VM (amd64 through qemu-user), QEMU from the arm64 tools image.

| Board | Accel | F0 contents | F1 first boot as hub | F2 dashboard | F3 reboot keeps state | F4 A/B update keeps /data | Minutes |
|---|---|---|---|---|---|---|---|
| arm64-efi | KVM (nested) | PASS | PASS (gateway up 31 s after boot start) | PASS | PASS | PASS (`mark-good slot=B version=2`) | 3 |
| x86_64-efi | TCG | PASS | PASS (58 s) | PASS | PASS | PASS (gate committed B after 123 s, inside the 300 s budget) | 7 |

The existing battery on the same image, T0, T1, T2, T11, T3, T4, T4v, T5, T5v: **all PASS on arm64-efi** (KVM, 16 min) and **all PASS on x86_64-efi** (TCG, 30 min; T4/T5 decided at about 350 s after the reboot, as designed). The OneMind layer does not disturb the gate. CI (`image.yml`) runs F0–F4 on x86_64-efi (KVM) and arm64-efi on every change to `os/`, `core/`, `dashboard/`, `cmd/` or `internal/`.

**Not tested yet:** worker and leaf roles end to end (unit tests only: `test/unit/test_firstboot.py`); the setup wizard in a booted image (unit-tested over HTTP); `/boot/efi/onemind.conf` in a booted image (unit-tested); `vm-do` first boot through cloud-init's user-data path; the gateway's kubeconfig and an app install from the image.
