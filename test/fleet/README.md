<!-- SPDX-License-Identifier: Apache-2.0 -->
# Virtual fleet test (#864)

**Serves:** issue #864 (wave E, release gate), the "same image on every machine" rule, and the virtual-fleet row of the 1.0 plan: a hub and three nodes prove join, one system, failover and update-and-rollback on every release, until the real-hardware proofs run (and after, as a gate).

> **In plain words.** OneMind 1.0 is one image for every machine: one becomes the hub, the others join it and the whole family of machines acts as one system. Real devices arrive at different times, so each release is first proven on four virtual machines made from that release's image. The hub starts a new OneMind; each node joins with the same QR code a person would scan; then the test checks that the hub sees everyone, the message bus reaches everyone, one dashboard shows all four, an app lands on a node, a node can die and come back, and an update rolls out one machine at a time, with a deliberately broken update that must undo itself.

```sh
# on a machine that can ssh to the Proxmox host (or on the host itself, with ONEMIND_FLEET_PVE unset)
export ONEMIND_FLEET_PVE=<ssh target of the Proxmox host>
export ONEMIND_FLEET_BRIDGE=<bridge>  ONEMIND_FLEET_GW=<gateway>
export ONEMIND_FLEET_ADDRS=<hub/24>,<node1/24>,<node2/24>,<node3/24>
export ONEMIND_FLEET_STORAGE=<VM disk storage>  ONEMIND_FLEET_SNIPPETS=<snippets storage>  ONEMIND_FLEET_SNIPPETS_DIR=<its folder>
python3 -I test/fleet/fleet.py --release <dev-or-release tag> --results <dir outside the repo>
python3 -I test/fleet/fleet.py --release <tag> --results <dir> --broken-node-image    # must end NEGATIVE-OK
```

Nothing about the lab is in this folder: host names, addresses and storages come from the runner's environment, and every line printed or saved goes through a redactor (addresses, lab names, join codes, 64-hex values are masked). The hub's owner token is copied to a root-only file inside the disposable hub VM and never leaves it.

## What it may touch (fleetcore.py guards)

| Rule | Why |
|---|---|
| VM ids 500-503 (range 500-509), names `onemind-fleet-*`; an id held by a VM with another name stops the run | the lab's own machines (hub, build worker, CI runners, gateway container) are never touched |
| 4 GiB hub + 3 × 2 GiB nodes = 10 GiB, within a three-4-GiB-VM budget (12 GiB) | the lab runs CI and build VMs at the same time |
| before each VM starts, the host must keep at least 8 GiB available after it | stops before the host runs short |
| the four addresses must not answer a ping before the run | never takes an address someone uses |
| teardown destroys only `onemind-fleet-*` VMs in 500-509 and their snippets | |

## Checks

| Id | Check | How |
|---|---|---|
| F0 | preflight | guards above; the release's `SHA256SUMS` verifies the vm-do qcow2 on the host |
| F1 | first boot | hub user-data `onemind: role: hub`; nodes get none (they join later); hub gate `committed-boot`, gateway healthy, nodes reachable |
| F2 | join | per node: the hub mints a ticket (`POST /v1/fabric/join-tickets`: `qr_payload_v2`, else `qr_payload` v1; the report names which); the node joins through the image's own enrolment flow, `onemind-firstboot configure --role worker --join-code ... --hub-addr ...` (what the setup wizard runs; it starts `onemind fabric join --code-file` with its files on /data); the match code the node prints must equal the hub's; `onemind fabric approve` on the hub; the node logs `joined the hub` |
| F3 | nodes | `/v1/nodes` lists four, all `online` |
| F4 | bus | `/v1/fabric`: every node's `leaf_link` is `up` |
| F5 | one dashboard | the hub's HTTPS dashboard answers on 8443 and its `/v1/nodes` over HTTPS shows four |
| F6 | placement | needs k3s on the workers; else BLOCKED with the reason. With `ONEMIND_FLEET_APP`: install it, the pod runs on the node the placement chose |
| F7 | failover | `qm stop` node 3: offline within 120 s + 45 s slack (`core/onemind_core/nodes.py`), the others stay online, `qm start`: online again |
| F8 | staged update | the release's `-next.raucb` on node 1, 2, 3, then the hub, one at a time; each must log `RESULT mark-good` on the new version and the fleet must be online before the next; the wave stops at the first failure |
| F9 | forced-bad rollback | node 2 installs the bundle again, then the slot just written gets the battery's broken init (test/qemu/bad-boot-init, T6); it must log `RESULT fell-back` by itself while the other three stay `mark-good` and online |

**Verdicts.** GREEN only when F0-F9 all PASS (BLOCKED is not green). `history.jsonl` in the results folder counts green runs in a row on the same image sha256; the acceptance is three. A `--broken-node-image` run zeroes the start of each node's disk (its partition table and boot code): it is NEGATIVE-OK only when F2 FAILS.

## Status

| Date | Run | Result |
|---|---|---|
| 2026-11-22 | lab, release dev-20261122-96333e9 (vm-do 0.1.0-dev.954), 4 full runs + single steps | **RED, as it should be today.** F0 and F1 pass (first boot about 4 min). F2: node 1 joins (QR v1, match codes agree, mesh and NATS leaf up); nodes 2 and 3 are refused `409 duplicate_node_id`, because every machine from one image has the same machine-id (#943). Single steps on the joined node: F7 PASS (offline after 113 s, back online), the F8 update PASS (`mark-good slot=B version=...-next`), the F9 forced-bad PASS (`fell-back slot=B`, slot A `verdict=image-bad` after 3 tries). F6 BLOCKED (k3s sees only the hub). |

**What blocks three green runs (found by this test, outside test/fleet).**
- #943: one machine-id for every machine from an image, so only the first node can join.
- A node sometimes has no network on its first boot: `rauc.service` fails and cloud-init never runs (#391, the data-extend race on a disk bigger than the image; the fleet grows each disk by 8 GiB, so it hits often: 1 to 2 of 3 nodes in 3 of 5 runs). The fix (#868) is on release/next but not in the dev releases, which are built from `main`. The test does not power-cycle: F1 fails and shows that node's console.
- Image workers have no k3s agent yet (os firstboot keeps `ONEMIND_FABRIC_K3S` off), so F6 cannot pass and failover has no workload to move.
- The dev releases are built from `main`: their hub mints QR v1 only, and first boot on `release/next` still accepts only v1 join codes (`JOIN_CODE_RE` in onemind_firstboot.py). The join uses the image's own enrolment flow (`onemind-firstboot configure --join-code`, which runs `onemind fabric join`), so it tries v2 first and the report names the version used.

**Other limits.** The release ships no signed "bad" bundle, so F9 breaks the freshly written slot instead (same effect as the battery's T6 bundle: PID 1 exits, the kernel panics, GRUB's try counter falls back). The vm-do image is the one the release carries with update bundles; a cloud-proxmox image with bundles would boot UEFI instead. Every node's hostname is the image default (`onemind`); join requests carry the name given at configure time.
