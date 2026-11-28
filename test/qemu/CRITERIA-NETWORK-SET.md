# QEMU battery, wired network change with automatic rollback: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 before the step it judges (`netset.py`, run by `firstboot.py` after NW4) was implemented or run. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness output and CI logs).

**Serves:** wave 2 setting P-08 (founder-approved 2026-11-25): an owner sets a static IPv4 address and DNS on a wired interface, or goes back to DHCP, and the box applies it through a NetworkManager checkpoint with an automatic rollback timer; D-027/D-028 (every OS-changing write is an owner action; state lives on /data and survives reboot and A/B update). **Builds on** `CRITERIA-NETWORK.md` (NetworkManager on the boards). Does not replace it.

## 1. Starting state and rules

- The tests run on the slot-A boot of the first-boot battery (`firstboot.py`, board x86_64-efi), after NW4's profile is saved and before the F3 reboot; NS2 has a second half right after the F3 reboot.
- They call the **host service** (`onemindd host serve`, the process that runs NetworkManager changes) on its socket `/run/onemind/host.sock` from the guest's root shell, with `curl --unix-socket`. The owner approval, the gateway routes, the dashboard form and the CLI are judged by their own unit tests, not here: the approval needs a passkey or a person, which a headless battery does not have.
- The harness talks to the guest over the serial console, so an address change on the wired NIC never cuts the harness off. What is judged is the box's own state: addresses, profile files, `nmcli`.
- QEMU's user-mode network (slirp, `restrict=on`) hands out one DHCP address and no router. The static addresses used here are made up inside that subnet or in 192.0.2.0/24; nothing outside the guest is reached with them.
- The interface is the first ethernet device `nmcli` lists as connected. Its DHCP address before the tests is called ADDR0.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| NS1 | A change nobody confirms rolls back by itself | `PUT /v1/network/<dev>` with `mode=static`, `address=192.0.2.50/24`, `gateway=192.0.2.1`, `dns=[192.0.2.53]`, `rollback_seconds=20` answers 200 with `pending` set; at once the device has 192.0.2.50/24 and ADDR0 is gone, and `GET /v1/network/changes` shows `pending` for that device; no confirm is sent; within 20 s plus 25 s of slack the device has ADDR0 again and not 192.0.2.50, the profile's `ipv4.method` is `auto` and `ipv4.addresses` is empty, `changes` shows no `pending` and `last.result` is `rolled_back` | The call is refused, the address was never applied, nothing is pending, or after the window the static address or a non-`auto` method is still there, or `last.result` is not `rolled_back` |
| NS2 | A confirmed change sticks and survives a reboot | `PUT` with `mode=static`, `address=ADDR0's address plus 30 in the last octet (same prefix)`, `gateway=ADDR0's network address plus 2`, `dns=[192.0.2.53]`, `rollback_seconds=20` answers 200; `POST /v1/network/<dev>/confirm` answers 200 and `changes` shows no `pending` and `last.result` is `confirmed`; after waiting 30 s (longer than the window) the device still has the static address and the profile's `ipv4.method` is `manual`; the profile file under `/data/state/etc-NetworkManager-system-connections/` has mode 600; after the F3 reboot (no input) the device has the static address and `ipv4.method` is still `manual`. Then `PUT` with `mode=dhcp` and `rollback_seconds=20`, `confirm`, and the device has a DHCP address again with `ipv4.method` `auto`, `ipv4.addresses` and `ipv4.dns` empty | The static address is lost after the window or the reboot, confirm is refused, the profile is not `manual`, the file mode is not 600, or going back to DHCP leaves a static address or DNS in the profile |
| NS3 | Refusals change nothing | Each of these answers 4xx and leaves the device's addresses and the profile's `ipv4.method` as they were: a `PUT` on `lo`; a `PUT` on a name that does not exist; a `PUT` with `mode=static` and no gateway; a `PUT` with a gateway outside the address's subnet; `POST confirm` with nothing pending (409 `no_pending_change`) | Any answer is 2xx, or any address or method differs afterwards |

## 3. Not covered (reported, never claimed)

- The owner approval, passkey step-up, the gateway routes, the dashboard form and `onemind network`: unit tests. A person approving at the new address, in a browser, is for the hardware kit.
- A real second subnet, a real router and a real DNS server: slirp has none. That the new gateway and DNS work is for the hardware kit.
- A power cut or reboot **during** the confirm window: covered by a Go unit test of the recovery step (`netset.Recover`), not by this battery.
- Wi-Fi, VLANs, bonds, bridges, IPv6 settings (this change sets IPv4 only).

## 4. Amendment (2026-11-25): NS2 keeps the address k3s bound to

**Status:** written before `netset.py` was first run; NS1, NS3 and the rest of NS2 above are unchanged. **Why:** NS2 as first written moved the box to ADDR0's network address plus 30 and kept it through the F3 reboot. k3s and the hub's mesh bind to the address the box had at first boot, and the rest of the first-boot battery (F3 onwards) judges them; a changed address across that reboot would make those tests judge this change instead of their own subject. **What changes:** in NS2 the static address is **ADDR0 itself** (the same address and prefix, so nothing that bound to it notices), the gateway is the network address plus 2, and the DNS list is `[192.0.2.53]`. Everything that makes the profile static is still checked: `ipv4.method` is `manual` (not `auto`) and `ipv4.dns` holds 192.0.2.53, both after the window and after the F3 reboot, and the profile file has mode 600. NS1 still moves the box to 192.0.2.50 for 20 s and back; the first-boot tests after it judge that the box came back unharmed.
