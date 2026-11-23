# QEMU battery, setup wizard on the booted image: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-22 before the test that judges it (`test/qemu/wizard.py`) existed. Its sha256 at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here.

**Serves:** #578 (the wizard's web part runs unprivileged, a root helper applies the form), the image-security review 07 lockdown, and the review of PR 921, which asked for a run on real systemd before merge: the `DynamicUser` web part, the `-+` Exec lines, socket activation with `Accept=yes`, the `/proc` cgroup peer check, and a LAN flood. **Does not replace** `CRITERIA-FIRSTBOOT.md` (seeded first boot) or `CRITERIA-FIREWALL.md` FW4 (the wizard's port on the LAN and the public address).

## 1. Setup and rules

- Two VMs boot the `x86_64-efi` fixture image (with the QEMU test overlay), both **without a seed**, so both have no role and run the setup wizard. **A** becomes the hub, **B** the worker. They are joined by a second NIC on a QEMU socket link (the LAN pair of `CRITERIA-FIREWALL.md` §1: A takes the box's address, B the scanner's), apart from the user-mode NIC the harness drives them through.
- The wizard is "up" on a VM when its loopback `/healthz` answers 200 with the body `setup`.
- **LAN requests** go from B's LAN address to port 8080 of A's LAN address. **Box-screen requests** are made on the VM itself to `http://127.0.0.1:8080`.
- Timeouts (wall clock): wizard up 900 s after boot, hub gateway `/healthz` 900 s after the form, the hub listing the worker's join request 600 s.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such. Every verdict records the board, KVM or TCG, and the host CPU count.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| WZ1 | Web part unprivileged, helper door up | On A with the wizard up: the main process of `onemind-setup.service` has real and effective uid not 0 and `CapEff` all zero; `onemind-setup-helper.socket` is active and listening on `/run/onemind-setup-helper.sock`; the setup code file `/run/onemind/setup-code` exists, mode 0600, owner root, 10 symbols | Any of these not so |
| WZ2 | The LAN needs the code | From B: `GET /` answers 200 and the page asks for the code (`name="code"`); `POST /setup` with `role=hub` and no code answers 403; A has no `state.json` afterwards | Any other answer, or A configured |
| WZ3 | A flood does not wear out the helper | From B, 2000 `GET /` requests (16 at a time) to A, then on A 300 connections opened and closed on the helper socket by root. Afterwards: the socket is still active with result `success`; the helper connections the LAN flood caused (the socket's `NAccepted` before and after) are at most `ceil(flood seconds / 5) + 3`; every LAN answer during the flood was 200 or 403 (no 5xx, no reset); the wizard still answers 200 on A's loopback and to a `GET /` from B | The socket failed or stopped, more helper connections than the bound, a 5xx or reset, or the wizard no longer answering |
| WZ4 | Wizard to hub, from the LAN with the code | B posts `role=hub&name=Lab` with the code read from A's screen file. The answer is 200 with a 64-hex owner token; on A `state.json` has `role: hub` and `source: wizard`; the setup code file is gone; `onemind-setup.service` is inactive; the gateway answers `/healthz` 200 and `GET /v1/fabric` with that token answers 200 | Any of these not so |
| WZ5 | Wizard to worker, on the box screen | With a join code made on A (`POST /v1/fabric/join-tickets`, role worker, owner token), B posts `role=worker`, the join code and `hub_addr` set to A's LAN address to its own loopback wizard. The answer is 200 and names Approvals; on B `state.json` has `role: worker`, `source: wizard` and that `hub_addr`; and A's `GET /v1/fabric` lists a join request from B (`joining` not empty) | Any of these not so |

## 3. Not covered (reported, never claimed)

- The owner approving the join and the worker's k3s agent coming up (covered by the fabric tests, not the wizard).
- Leaf role through the wizard (same helper path as worker; covered by the unit tests).
- IPv6, real hardware, and a box screen (kiosk) other than loopback `curl`.
