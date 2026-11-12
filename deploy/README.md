# deploy/: put OneMind on real machines today (developer install, P6)

**Serves:** contract [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §6 (and the §3 checks in `verify/`), brief 30 **D-B2.4** (developer install P6, REC-DEC-30) and B10 (seed apps run on the hub), lesson [06](../docs/learning/06-image-building-on-our-hardware.md) (hardware bring-up, BD-DO-1), milestones BM0/BM1 (hardware proof before the image is ready).

> **UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK.** `install.sh` adds the OneMind stack on top of a normal OS. If something breaks, nothing rolls back. The real product is the read-only A/B image built from `os/` (another stream). Use spare machines or spare disks.

## The picture
```
              your Mac (browser)                      Beelink = hub
                    │  http://<hub>:8080        ┌────────────────────────────────┐
                    └──────────────────────────▶│ gateway + dashboard  (:8080)   │  (a pod in k3s)
                                                │ NATS                 (:4222)   │◀── heartbeats every 10 s
                                                │ k3s server           (:6443)   │◀── k3s agents join
                                                │ onemindd             (:7480)   │
                                                └────────────────────────────────┘
       Pi 5 = node          Jetson = node          DigitalOcean droplet = node
   k3s agent + onemindd  k3s agent + onemindd     k3s agent + onemindd
```
- **Hub:** the one machine that holds the cluster's database (k3s **server**), the message bus (**NATS**), the **gateway** (the API every request goes through, including the owner-approval step) and the **dashboard**.
- **Node:** a machine that runs workloads (k3s **agent**) and reports its health (**onemindd**, the node agent, publishes a heartbeat to the hub's NATS every 10 s).
- **Bundle:** the three things we build on the Mac and copy to a machine: the `onemindd` program, the gateway container image and the built dashboard. `./deploy/bundle.sh --arch amd64|arm64` makes one per CPU type, with a `SHA256SUMS` file that `install.sh` checks before using anything.
- **Join token:** the hub prints it **once**, as `omj1.<nats-token>.<k3s-token>`. It is a password for joining your cluster: never paste it into git, chat or issues. If you lose it, read it on the hub: `sudo cat /etc/onemind/nats.token /var/lib/rancher/k3s/server/node-token`.
- **API tokens:** the hub also prints an **owner** token (sign in to the dashboard, approve actions) and a **dev-agent** token (for AI agents: they can *request* actions, never approve them). Only their sha256 hashes are stored on the hub, so they cannot be read back: save them in your password manager. To issue new ones, delete `/etc/onemind/tokens.yaml` and run the hub install again.

## What `install.sh` does (and how it stays safe)
| Step | Hub | Node | Why |
|---|---|---|---|
| Prerequisites (`curl`, `iptables`, `python3`, …) | ✓ | ✓ | k3s and the checks need them |
| Pi 5 only: memory cgroup on | ✓ | ✓ | k3s refuses to run pods without it; asks you to reboot once |
| Secrets: NATS token, owner + agent API tokens | ✓ | | Generated **on the machine** from `/dev/urandom`, root-only in `/etc/onemind/`; API tokens stored as sha256 hashes only |
| NATS v2.15.2 (`onemind-nats.service`) | ✓ | | Tarball checked against a pinned sha256; token auth on |
| k3s v1.37.2+k3s1 (server / agent) | ✓ | ✓ | Binary **and** installer checked against pinned sha256s; SQLite datastore (BD-11), `--secrets-encryption`, kubeconfig root-only |
| onemindd (`deploy/systemd/onemindd.service`) | ✓ | ✓ | The hardened unit from `deploy/systemd/`; settings in `/etc/onemind/onemindd.env` (`ONEMIND_NATS_URL`, `ONEMIND_NODE_ROLE`) |
| Gateway + dashboard on k3s (`onemind-system`) | ✓ | | Image imported into k3s from the bundle; `kubernetes` executor, so an approved install really runs `kubectl apply -k apps/<id>/manifests` into `app-<id>` |

**Pinned versions** come from brief 30 §4.1 and B6 (k3s v1.37.2+k3s1, NATS v2.15.2). The hashes were re-checked on 2026-11-12 against the upstream checksum files (k3s `sha256sum-amd64.txt` / `sha256sum-arm64.txt`, the `install.sh` at tag `v1.37.2+k3s1`, NATS `SHA256SUMS`). A mismatch stops the install.

**Every run is safe to repeat (idempotent):** a second run skips what is already right and never regenerates existing secrets. Add `--dry-run` to print every step without changing anything (no root needed). Add `--target debian13|rpi5|jetson|do` to preview another machine's plan from your Mac.

## Step 0, on the Mac: build the bundles
```sh
./deploy/bundle.sh --arch amd64      # Beelink and DigitalOcean (x86_64)
./deploy/bundle.sh --arch arm64      # Raspberry Pi 5 and Jetson (arm64)
```
Each writes `out/bundle-<arch>/` (git-ignored): `onemindd-linux-<arch>`, `onemind-gateway-linux-<arch>.tar`, `dashboard/`, `SHA256SUMS`. Nodes only need onemindd (`--node-only` builds just that). The amd64 gateway image is built under emulation on an Apple-silicon Mac, which takes a few minutes.

Then put a clone of the repo and the bundle on each machine:
```sh
ssh <machine> 'git clone https://github.com/onemindos/ONEMINDOS.git onemind'
rsync -a out/bundle-amd64/ <machine>:onemind-bundle/
```

---

## Target 1: Beelink mini PC = the hub (Debian 13, x86_64)
1. Install **Debian 13 "trixie"** from the netinst USB. Choose "SSH server" and "standard system utilities", no desktop. Use the whole disk (a spare one).
2. Log in, then give your user sudo once: `su -c 'apt install -y sudo && adduser <you> sudo'`. Log out and in again.
3. Preview the install, then run it:
   ```sh
   cd ~/onemind
   ./deploy/install.sh --role hub --bundle ~/onemind-bundle --dry-run     # read the plan
   sudo ./deploy/install.sh --role hub --bundle ~/onemind-bundle
   ```
4. Save what it prints **once**: the dashboard URL, the node join command and the owner/agent tokens. Password manager, never the repo.
5. Check it:
   ```sh
   sudo ./deploy/verify/node-check.sh                                      # on the Beelink
   ./deploy/verify/verify.sh http://<beelink>:8080 <owner-token> <agent-token>   # from the Mac
   ```
   On a hub with the `kubernetes` executor, verify.sh really installs a seed app (Uptime Kuma by default) and then removes it again. Add `VERIFY_KEEP=1` to keep it and open it from the dashboard.

## Target 2: Raspberry Pi 5 = a node (Raspberry Pi OS Lite 64-bit, trixie)
1. Flash **Raspberry Pi OS Lite (64-bit)**, the trixie release, with Raspberry Pi Imager. Set the hostname (`pi5`), your user and your SSH key in the Imager settings. It must be a **Pi 5**; a Pi 4 is not a v0 board.
2. Boot it, clone the repo and copy `out/bundle-arm64/` (`--node-only` is enough).
3. Run the join command the hub printed:
   ```sh
   sudo ./deploy/install.sh --role node --hub <beelink> --token 'omj1.…' --bundle ~/onemind-bundle
   ```
   The **first** run may stop with "memory cgroup is enabled on the next boot" (exit code 3). That is expected: `sudo reboot`, then run the **same** command again.
4. Check: `sudo ./deploy/verify/node-check.sh`. The Pi appears in the dashboard's Nodes screen within about 10 s.

## Target 3: Jetson (Orin) = a node (NVIDIA L4T Ubuntu 22.04/24.04)
1. Keep the JetPack/L4T install NVIDIA's tools put on it. Record `cat /etc/nv_tegra_release` (lesson 06 §3). Reflashing needs an x86 Linux host, so it is not done here.
2. Clone the repo, copy `out/bundle-arm64/`, then run the join command:
   ```sh
   sudo ./deploy/install.sh --role node --hub <beelink> --token 'omj1.…' --bundle ~/onemind-bundle
   ```
3. `sudo ./deploy/verify/node-check.sh`.

**Gap:** k3s runs normal pods here, but **GPU pods** need the NVIDIA container runtime wired into k3s's containerd, plus the device plugin. That is not done in v0 (B6 / LT-JET kits). The node shows `board: jetson-orin`, and onemindd reports `gpu.nvidia`.

## Target 4: DigitalOcean droplet = a node or a cloud hub (Debian 13)
Today we use a **stock Debian 13 droplet** (lesson 06 §4, option 2). Our own image needs the BIOS variant first (BD-DO-1), because DigitalOcean cannot boot UEFI custom images.
1. Create a droplet: **Debian 13 x64**, at least 2 GB RAM, with your SSH key, in a **VPC**.
2. **Firewall first.** Create a DigitalOcean Cloud Firewall for the droplet: inbound SSH (22) from your own address only, nothing else from the internet. If the droplet is a **hub**, allow 4222, 6443 and 8080 only from your VPC range or your Tailscale range. NATS and the k3s API must never face the public internet. (The hub install prints this reminder on a droplet.)
3. A droplet must reach the hub's 4222 (NATS) and 6443 (k3s API), and the machines must reach each other on 8472/udp (flannel VXLAN, the pod network) and 10250 (kubelet). A home hub behind NAT is **not** reachable from DigitalOcean. Either run Tailscale on both and use `--hub <hub-tailscale-name>`, or make one droplet the hub for your cloud machines.
4. Run the join command with the amd64 bundle:
   ```sh
   sudo ./deploy/install.sh --role node --hub <hub-address> --token 'omj1.…' --bundle ~/onemind-bundle
   ```
   The board shows as `vm-do`. Secure Boot and measured boot do not exist here (BIOS only).
5. **Droplets made from a snapshot** share the snapshot's `/etc/machine-id`, so they would show up as **one** machine (the node id is derived from it). Run `sudo rm /etc/machine-id && sudo systemd-machine-id-setup && sudo systemctl restart onemindd` on each clone. The same holds for any cloned VM or SD card.

## Target 5: the Mac (Docker Compose demo, no hardware)
For working on the dashboard and gateway without any box. It runs NATS, the gateway with the **noop** executor (an approved install is marked done but nothing is started), the dashboard, the **real onemindd** as the hub's own machine (built from `cmd/onemindd`), and **two simulated machines** (`sim-pi5` rpi5, `sim-jetson` jetson-orin) that send fake heartbeats, so the Nodes screen shows three machines.
```sh
cd deploy/compose
./up.sh            # makes local tokens in .secrets/ (git-ignored), builds, starts, prints the URL and owner token
open http://127.0.0.1:8080
../verify/verify.sh http://127.0.0.1:8080 "$(cat .secrets/owner.token)" "$(cat .secrets/agent.token)"
./down.sh          # stop; ./down.sh -v also forgets the ledger and NATS data
```
Plain `docker compose up --build` works too, once `up.sh` has made `.secrets/tokens.yaml`. Change ports with `ONEMIND_HUB_PORT=8081 ./up.sh`. Use `127.0.0.1`, not `localhost`: on a Mac, `localhost` can resolve to `::1` first and reach a different program on the same port. Inside Docker, onemindd sees the Docker VM, so the hub card shows board `unknown`, OS "Distroless" and no k3s: that is the honest reading, not a bug.

---

## Checking it works: `deploy/verify/`
| Tool | Run where | What it proves |
|---|---|---|
| `verify.sh <hub-url> <owner-token> [agent-token]` | anywhere | Contract §3, end to end: health, auth (401s), instance, ≥ 1 node online, **the hub's own node online**, no serial/MAC/IP fields, a complete app catalog, install action → `awaiting_approval`, idempotency, **agent approve → 403** and the action still waiting, agent request + deny → 403, owner deny → `cancelled`, approve after `expires_at` → 409 `expired`, owner approve → `succeeded`, the catalog shows it installed, a second install → 409 `stale_precondition`, then the app is removed again through an approved `app.remove`, `/openapi.json`, dashboard at `/`. Prints a results table. Exit codes: 0 pass, 1 fail, 2 usage, 3 a check was skipped (no agent token). |
| `node-check.sh` | on each machine (sudo) | onemindd is active, its `:7480/api/v1/node` matches contract §2, k3s version and service, on the hub `/readyz`, nodes Ready, NATS and gateway up, NATS accepts our token, **this node's own heartbeat seen on NATS**, clock in sync |
| `natscheck.py ping/watch` | anywhere with Python 3 | NATS reachability and live heartbeats, standard library only |
| `tests/test_verify.py` | Mac/CI | verify.sh passes a correct imitation hub (twice in a row) and catches 7 kinds of broken hub; NATS token auth; simulated heartbeat shape |
| `tests/e2e-systemd/run.sh` | Mac/CI with Docker | the **real** install.sh with the **real** bundle on two Debian 13 systemd containers: hub install, hub re-run, a node joins, both node-checks, 2 k3s nodes Ready, 2 onemindd heartbeats, verify.sh with the `kubernetes` executor, and the approved seed app (ntfy) becomes Available in k3s |

## Remove it again
```sh
sudo /usr/local/bin/k3s-uninstall.sh        # hub   (k3s-agent-uninstall.sh on a node)
sudo systemctl disable --now onemindd onemind-nats 2>/dev/null
sudo rm -rf /etc/onemind /opt/onemind /var/lib/onemind /etc/systemd/system/onemindd.service /etc/systemd/system/onemind-nats.service
```

## v0 shortcuts (from the contract and this PR)
- **Auth** is static bearer tokens from a file (Kanidm, BD-03, comes later). The hub makes one owner and one `dev-agent` token, stored as hashes.
- **NATS:** nodes publish straight to the hub's NATS (no leaf nodes yet), protected by one shared token in the join token. Per-node credentials and accounts (D-B6.5) come later. NATS in the Mac compose has no auth and listens on localhost only.
- **Gateway pod:** it uses `hostNetwork`, and its service account can manage the app resource kinds in every namespace (RBAC cannot scope to `app-*`). The capability broker replaces this.
- **No OS rollback,** no RAUC, no read-only root: this is P6, not the image.
- **k3s defaults:** not hardened yet (the B6 CIS profile, Pod Security admission, audit policy and NetworkPolicies come with `platform/k3s/`). The kubeconfig is root-only (`--write-kubeconfig-mode 0600`).
- **Release URLs:** onemindd and the gateway come from local builds (`bundle.sh`). `--onemindd-url` with `--onemindd-sha256` is ready for when releases exist.
- **Ledger:** SQLite in the gateway's PVC (PostgreSQL, BD-04, later).
- **App catalog and dashboard** are copied from the repo clone to `/opt/onemind/` at install time; re-run the hub install to update them.

## Known gaps
- Not yet run on the physical Beelink, Pi 5, Jetson or a droplet. Those runs are for Zeus, with the commands above, and they become the LT kit results. Everything above them was run in Debian 13 systemd containers on a Mac (arm64), so the **amd64** path (Beelink, droplet) has only been dry-run.
- The Jetson GPU runtime is not configured (see Target 3).
- Raspberry Pi OS's `cmdline.txt` change is written for the Pi 5 path `/boot/firmware/cmdline.txt` and was only dry-run.
