# QEMU battery, owner firewall allow rules with automatic revert: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 before the test that judges it (FW5 to FW7 in `test/qemu/firewall.py`) existed. Its sha256 is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here.

**Serves:** P-09 part 2 (firewall allow rules with automatic revert), D-027/D-028. Follows `CRITERIA-FIREWALL.md`: same two VMs, same link, same addresses, run in the same `make firewall` session after FW4. It does not change FW1 to FW4.

## 1. Setup and rules

- The box (hub, `onemindd host serve` running) gets a systemd drop-in that sets `ONEMIND_HOST_FIREWALL_TTL=25s`, then the host service is restarted. Production waits 5 minutes; the test waits 25 seconds. Nothing else is changed.
- The harness talks to the host service's own socket as root on the box (`/run/onemind/host.sock`), the same calls the gateway makes after an owner's passkey approval. The gateway's approval path has its own tests (`core/tests/test_firewall_allow.py`); this file judges what the box does with an approved rule.
- Three TCP listeners (9091, 9092, 9093) run on the box on every address. The scanner connects from the LAN address and from the public address (documentation range) and reads `open` or not. A connect that does not complete in 1.5 s counts as not open.
- Rules: A = tcp 9091 scope lan (never confirmed), B = tcp 9092 scope lan (confirmed at once), C = tcp 9093 scope mesh (never confirmed), D = tcp 9091 scope lan (added just before a host service restart).
- Timeouts (wall clock): host service back after restart 60 s, each probe 120 s.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. Every verdict records the board, KVM or TCG, and the host CPU count.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| FW5 | An unconfirmed rule reverts | `GET /v1/firewall` on the host socket says `allow.supported` is true. A and B answer 200 with state `pending`. Right after, from the LAN address 9091 and 9092 are open. After the 25 s deadline plus 10 s, with B confirmed and A not: from the LAN address 9091 is not open and 9092 is still open; `nft list chain inet onemind_host owner_lan` names 9092 and not 9091; confirming A answers 404 | A not open at first, A still open after the deadline, B closed by the deadline, A still in the chain, or A confirmable after it reverted |
| FW6 | Confirmed stays, pending does not survive a restart, remove closes | After the host service restarts, B is still open from the LAN address and still in `owner_lan`. D, added just before that restart and never confirmed, is not open and not in the chain. Removing B answers 200 and 9092 is then not open | B lost by the restart, D present after it, or B still open after removal |
| FW7 | The scope is the LAN or the mesh, never the internet | While A and B are open, from the public address none of 9091, 9092, 9093 is open. C (mesh) is not open from the LAN address or the public address (the mesh interface is absent). A request with scope `wan`, `any` or `0.0.0.0/0` answers 409 and adds nothing to the chain | Any of the three ports open from the public address, C open from either address, or a non-LAN, non-mesh scope accepted |

## 3. Not covered (reported, never claimed)

- The mesh interface itself (no tailscale in the VM): C proves only that a mesh rule is not reachable from LAN or public addresses.
- The gateway, passkey approval and the dashboard: covered by `core/tests/test_firewall_allow.py` and the dashboard tests.
- Reboot persistence of a confirmed rule (the host service restart in FW6 runs the same load path; a full reboot is not repeated here).
- Real hardware NICs.
