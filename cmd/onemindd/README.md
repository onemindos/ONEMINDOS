# onemindd: the OneMind node agent

**Serves:** contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §1–§2 (binding), brief 30 B9 (node side of the slice, D-B9.8 subset) and the first step of B4.2 (`onemindd` is the program the update service will grow inside). Gate G6 (brief 30 §7): `/healthz` reports this boot's `boot_id`.
**Language:** Go, per BD-02 (one static binary per arch, no interpreter on the host).

## What it does, in plain words
Every OneMind machine (Beelink, Pi 5, Jetson, droplet, a VM) runs one small program, `onemindd`. Its job in v0 is to say **"I am here, and this is what I am"**:

1. It looks at the machine: which board it is, OS, kernel, CPU, memory, disk, whether it has a TPM 2.0 chip, whether Secure Boot is on, whether k3s is installed and ready, which RAUC A/B slot it booted, whether it has an NVIDIA GPU.
2. It puts that into one JSON object, the **heartbeat** (contract §2).
3. Every 10 seconds it sends the heartbeat to the hub over **NATS** (a message bus: programs publish messages on a *subject*, here `onemind.node.<node_id>.status`, and anyone subscribed gets them). The gateway listens there and builds the Nodes screen of the dashboard.
4. It answers the same JSON on a local web API, `GET :7480/api/v1/node`, plus `GET :7480/healthz`.

**Why a heartbeat and not a "register once" call?** Because the hub must know when a node is *gone*. If heartbeats stop, the gateway marks the node `stale` after 30 s and `offline` after 120 s (contract §3). A registration would say a dead node is still there.

**Why it never queues heartbeats while the hub is down.** If the agent stored them and sent them later, the hub would receive a burst of old "I'm alive" messages and could show a dead period as healthy. So while NATS is down it skips; when the link comes back it publishes at once. The local API keeps working the whole time, so someone at the box can still see its state.

## Privacy rules (contract §2), and how they are kept
- `node_id` is the first 12 hex characters of **sha256(`/etc/machine-id`)**. The raw machine-id never leaves the box; a hash cannot be turned back into it. `ONEMIND_NODE_ID` overrides it; the override must be 1-64 characters of `A-Z a-z 0-9 _ -` (one NATS subject token, the same rule the gateway applies), or onemindd exits with code 2. A machine with no machine-id (a Mac, a bare container) hashes `hostname:<name>` instead, so the id is stable but says nothing about the hardware.
- No serial numbers, MAC addresses, IP addresses or user names. Concretely: the RAUC slot **device path** is dropped (it is often `/dev/disk/by-id/…` which contains the disk serial), and only the `Model:` line of the NVIDIA info file is read (the same file holds the GPU UUID). A test (`TestJSONShapeAndPrivacy`) fails if a MAC, IPv4, raw machine-id, `serial`, `by-id` or GPU UUID shows up in any fixture's JSON.

## How each field is detected
| Field | Source |
|---|---|
| `board` | In this order: `/etc/nv_tegra_release` → `jetson-orin`; `/proc/device-tree/model` contains "Raspberry Pi 5" → `rpi5`; DMI vendor `DigitalOcean` → `vm-do` (it is BIOS-only, learning 06 §4); DMI vendor/product names a hypervisor, or `systemd-detect-virt --vm` says so → `vm`; `/sys/firmware/efi` exists → `x86_64-efi` / `arm64-efi`; else `unknown` |
| `os` | `/etc/os-release` (fallback `/usr/lib/os-release`) |
| `kernel`, `uptime_s` | `/proc/sys/kernel/osrelease`, `/proc/uptime` |
| `cpu_model`, `cpus` | `/proc/cpuinfo` (`model name`, or `Model` on ARM, or the device-tree model) |
| `mem_*` | `/proc/meminfo` (MiB) |
| `disk_*` | `statfs` of `ONEMIND_DISK_PATH` (default `/`), GB = 10⁹ bytes |
| `tpm2` | `/sys/class/tpm/tpm0/tpm_version_major` = 2, or `tpmrm0` exists |
| `secure_boot` | efivar `SecureBoot-8be4df61-…` byte 5: 1 → `enabled`, 0 → `disabled`; no `/sys/firmware/efi` → `unsupported`; UEFI but variable unreadable → `unknown` |
| `k3s` | present: k3s binary or `/etc/rancher/k3s`; role `server` if `/var/lib/rancher/k3s/server` or `k3s.yaml` exists, else `agent`; ready: server runs `k3s kubectl get --raw /readyz` (= `ok`), agent uses `systemctl is-active k3s-agent` |
| `rauc` | `rauc status --output-format=json` when `rauc` is installed |
| `gpu` | `/proc/driver/nvidia/gpus/*/information` (Model line), else `nvidia-smi --query-gpu=name`; Jetson: integrated GPU, model from the device tree |

All file reads go through a **root prefix** (`internal/detect.Collector.Root`). On a real node it is `/`. Tests point it at fake machines in [`internal/detect/testdata/`](../../internal/detect/testdata) (`rpi5`, `jetson`, `droplet`, `x86vm`, `x86efi`), so one laptop tests every board. Commands (k3s, rauc, nvidia-smi, systemd-detect-virt) only run on a live system; tests replace them with canned output.

## Run it
```sh
# Tests (from the repo root)
go vet ./... && go test -race ./...

# Static Linux binaries -> cmd/onemindd/dist/
make -C cmd/onemindd build

# On a Mac or Linux box, against a local NATS
docker run -d --rm --name nats -p 4222:4222 nats:2.12     # or: nats-server
ONEMIND_NATS_URL=nats://127.0.0.1:4222 go run ./cmd/onemindd
nats sub 'onemind.node.*.status'                           # see heartbeats
curl -s localhost:7480/api/v1/node
```
On a Mac most Linux fields are empty (`board: unknown`, no `/proc`); that is expected. For real values run the Linux binary in a Debian 13 container or on the hardware.

Environment: `ONEMIND_NATS_URL` (empty = local API only), `ONEMIND_NODE_ROLE` (`hub`/`node`), `ONEMIND_NODE_ID`, `ONEMIND_AGENT_ADDR` (default `127.0.0.1:7480`, loopback only; `:7480` for every interface), `ONEMIND_DISK_PATH`, `ONEMIND_LOG_LEVEL`. Flags `-listen`, `-nats`, `-role`, `-interval`, `-version` override them.

Install as a service: see [`deploy/systemd/`](../../deploy/systemd/README.md).

## v0 shortcuts (from the contract, plus this component's own)
- **Nodes publish straight to the hub's NATS.** NATS leaf nodes (buffering on the node) come later (contract v0 shortcut; brief 30 BM4).
- **NATS auth:** what fits in `ONEMIND_NATS_URL` (e.g. `nats://user:pass@hub:4222`), or on a hub its own service nkey: `ONEMIND_NATS_NKEY_SEED` (flag `-nats-nkey`) names the seed file `deploy/install.sh` makes (CORE-SEC-4, #161). On a joined node, `ONEMIND_NATS_NKEY_SEED` and `ONEMIND_NATS_INBOX_PREFIX` (flag `-nats-inbox-prefix`) are written by `onemind fabric join`: the local leaf has no passwordless user (G1), so onemindd signs in with its own key and may use only its own subjects and replies. No JWT/creds file.
- **The local API has no authentication**, so it listens on `127.0.0.1:7480` (loopback only, hardening H-24); the hub learns the same data from heartbeats. It is read-only and the heartbeat holds no secrets or personal data by design. Actions that change the box live in the separate, authenticated rescue console below, not in this API.
- **k3s agent readiness** is "the `k3s-agent` unit is active", which is weaker than the server's `/readyz`. The gate's fresh-health check (REC-DEC-07) is a separate job.
- **RAUC slots** carry `name, class, bootname, state, boot_status, bundle_version`; the contract only says `slots: []`. The JSON field names read from `rauc status` follow RAUC's JSON output as used in our lab work; **UNVERIFIED against RAUC v1.15.2 on hardware** until LT-X86-01 runs it.
- **OS updates** (B4.2) run in the same binary as a separate process, `onemindd update`, under its own unit; see [`internal/update/`](../../internal/update/README.md). When `/etc/onemind/update.conf` exists (`ONEMIND_UPDATE_CONF` overrides the path), the heartbeat carries an optional `update` object read from the update service's status file: `{channel, current_version, available_version|null, state, last_check|null, last_result}`. Without the file the object is omitted, so heartbeats stay valid under contract §2.

## Rescue console
`onemindd rescue` (CORE-UPDATE-8, brief 30 B11, [UPDATES §3.5](../../docs/leap/core/UPDATES.md)) is the owner's way back when Kubernetes or the gateway is broken. It runs as its own process and unit ([`onemind-rescue.service`](../../deploy/systemd/onemind-rescue.service)) and needs only `rauc`, `systemctl` and `journalctl`, so it works with k3s stopped. Code: [`internal/rescue/`](../../internal/rescue/).

| Path | What it does |
|---|---|
| `GET /` | Page: booted slot, each slot's state, boot status and bundle version (`rauc status --output-format=json`), the `k3s`/`k3s-agent` unit states, the onemindd version, the rollback form and the log link |
| `GET /status.json` | The same as JSON (with the CSRF token, for `curl`) |
| `POST /rollback` | Form fields `csrf` (from the page) and `confirm=rollback`: runs `rauc status mark-active other`, answers, then `systemctl reboot`. A GET is refused (405) |
| `GET /logs` | `journalctl -n 5000` for onemindd, update, rescue, health gate, rauc and k3s, as a text file, at most 4 MiB |

**Who may use it.** Every path needs the **owner token**, the one `deploy/install.sh` printed once. The browser asks for it as a password (HTTP Basic, any user name); `curl` can send `Authorization: Bearer <token>`. It is checked against the owner `sha256:` entry in the gateway's tokens file (`-tokens`, `ONEMIND_TOKENS_FILE`, default `/etc/onemind/tokens.yaml`), in constant time, without the gateway running. Agent principals never pass (AI never actuates). With no owner entry the console answers 503 to everyone. 5 wrong tries from one address block that address for a minute. Only loopback, private (RFC 1918, `fc00::/7`) and link-local clients are served.

**Why this way.** The tokens file already exists on every install and stores only hashes, so no new secret has to be made or stored. A CSRF token (a random value only the real page knows) plus the typed `rollback` stops another website open in the same browser from triggering a rollback with the cached password.

**HTTPS.** It serves the box CA's certificate (`-tls-dir`, `ONEMIND_NET_TLS_DIR`, default `/var/lib/onemind/tls`, files `https.crt` and `https.key`, written by `core/onemind_core/ca.py`) on `-listen` (`ONEMIND_RESCUE_ADDR`, default `:7443`). Without those files it refuses to start, unless `-listen` is a loopback address (`127.0.0.1:7443`), where plain HTTP is allowed for an SSH tunnel.

```sh
curl --cacert ca.crt -H "Authorization: Bearer $OWNER_TOKEN" https://onemind.local:7443/status.json
```

### Owner terminal (SEC-TERM-01, #273)
The console can carry an owner-only web terminal ([threat model](../../docs/security/rescue-terminal.md)). It is **off by default and opens a shell only after a fresh owner passkey assertion that the gateway on this box verifies** (`-gateway`, `ONEMIND_RESCUE_GATEWAY`, default `http://127.0.0.1:8080`, loopback only; D-014: never behind the plain owner token). `onemindd rescue terminal enable|disable|status` flips the switch file (`-terminal-switch`, `ONEMIND_RESCUE_TERMINAL_SWITCH`, default `/etc/onemind/rescue-terminal.on`); each change, and every session start and end, is written to the console's own audit chain (`-audit`, `ONEMIND_RESCUE_AUDIT`, default `/var/lib/onemind/rescue-audit.jsonl`). A valid agent or non-owner token gets 403 on `/terminal`.

### Owner lost every passkey (D-028)
With no owner passkey on the box the terminal no longer dead-ends. If an emergency kit was issued, the terminal page asks for the **owner recovery key from the printed kit**. The console forwards it to the gateway (`POST /v1/auth/rescue/kit`, not in the OpenAPI), which compares a fingerprint in constant time; after 5 wrong tries it waits 15 minutes, doubling per further wrong try up to 24 hours, and never deletes anything. The console takes the kit key **only from a browser on the box itself** (loopback client, or an SSH tunnel to it), on top of the owner token, so standing at the box without the kit, or holding only the owner token on the LAN, is never enough. The kit does not read, show or remove any disk or backup key. The kit's credential id on the audit chain is `kit:<fingerprint>`. Not built yet: the local text-console menu on the box's own screen, and password and passkey reset after a kit session (the design's PR 25c).

## Known gaps
- **Rescue console:** owner token, not the owner passkey that UPDATES §3.5 plans (passkeys arrive with Kanidm, BD-03). The CA directory lives on `/data`, so when `/data` itself is lost the console has no certificate and only loopback works; recovery mode's read-only page on :8080 covers that case (`os/recovery/README.md`). Restore and gate-log views are not built yet. The lockout is per address, so a LAN device can keep the owner locked out while it keeps guessing. Not yet run on hardware with real RAUC (`mark-active other` under this unit is UNVERIFIED until an LT-X86 kit runs it).
- `vm` detection inside a container needs `systemd-detect-virt` or readable DMI; a plain Docker container on a VM may report `unknown`.
- Not yet run on the real Beelink, Pi 5, Jetson or droplet. Fixture trees were written from the documented file formats, not copied from those machines. First hardware run: `onemind node info` on each box, and compare.
