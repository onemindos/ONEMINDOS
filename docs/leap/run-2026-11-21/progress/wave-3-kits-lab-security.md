<!-- SPDX-License-Identifier: Apache-2.0 -->
# Wave 3: hardware kits, lab cycle, security re-review

**Parts:** real hardware, OS and image, security. **State:** kits approved; lab cycle ran; security fixes in progress.

## Hardware kits (nothing has run on real metal yet)

| PR | Kit | Review |
|---|---|---|
| #466 | LT-DO-01: cloud firewall script before first boot, hub role, closed cluster ports | CHANGES, then APPROVE |
| #467 | LT-X86-01: install on the mini PC from the installer stick | CHANGES, then APPROVE |
| #468 | LT-PI5-02: bootc on a Pi 5 (D-013) | CHANGES twice, then APPROVE |
| #469 | Dell 5540 client kit | CHANGES twice, then APPROVE |
| #471 | G1 power-pull harness (manual, Redfish, IPMI, smart plug) | CHANGES, then APPROVE |
| #477 | API acceptance suite against a live hub | APPROVE |

Unverified until the founder runs them: boot keys and BIOS menus, the first-boot URL scheme, the cloud CLI flags, and power-pull timings.

## Lab cycle on the lab server (VMs from the shipped image)

- **Smoke: PASS.** Image import about 1 minute, login prompt about 25 seconds, gateway healthy about 2 minutes after power on. Problems: node API reports k3s as agent and not ready on a healthy hub (medium); 41 of 66 Market apps are tier blocked on the shipped catalog (medium); three low items (kubectl on the box, ports closed for a minute after boot, little root headroom).
- **Fabric: PARTIAL.** Join works, but the joined node never shows on the hub because the node id in `onemindd.env` does not match the fabric identity (high; `internal/fabric/install.go`). No store-and-forward across a link outage (medium; #472 is the first slice).
- **Restore: BLOCKED.** The image ships with backups off and no restic, so no backup or restore works on a booted hub (high). The 60-minute drill (#163) cannot run on an image-built hub until the wiring lands in `os/`. Files area is also unavailable on the image (medium).

## Security re-review (find, then a second agent tries to reproduce)

Verified (could not be refuted):

| Finding | Severity after check |
|---|---|
| DigitalOcean image serves the first-boot wizard on the public internet (`os/boards/vm-do/board.yaml`) | high |
| Backups `approve: true` shortcut skips the passkey guards (`core/onemind_core/routers/backups.py`) | high |
| TUF client re-anchors to the image root on every check, so rotation never sticks (`internal/update/tuf.go`) | medium |
| Standing approvals made without passkey step-up (`core/onemind_core/automation/policies.py`) | medium |
| A static-file adult can mint an unowned 90-day agent token (`core/onemind_core/identity/service.py`) | medium |
| App roles can give an app's own pods write access at runtime (`core/onemind_core/policy.py`) | medium |
| Failed `rauc install` is followed by a reboot and the release marked bad (`internal/update/engine.go`) | low |
| App agent token not revoked when an update removes `spec.agent` (`core/onemind_core/actions.py`) | low |
| First-boot owner token stays a permanent owner bearer | low |
| Jetson OTA has no anti-downgrade check | low (parked) |

Refuted or lowered to design notes: host executor trusts any action id from the gateway (low, a documented boundary); no target binding for `os.update.install` (low, not built yet); restart and shutdown ignore the mission-safe inhibit (informational); k3s default ports and flannel (medium, not shown exploitable); overlapping community source prefixes (low).

## What is left

- Fixes for the verified findings (wave 4).
- Lab: node id fix, backup wiring in the image, then a re-run of fabric and restore.
- Founder runs the kits on hardware at G1.
