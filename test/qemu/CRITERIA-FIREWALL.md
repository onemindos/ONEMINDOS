# QEMU battery, host firewall: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-21 before the test that judges it (`test/qemu/firewall.py`) existed. Its sha256 at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here.

**Serves:** finish audit 07 item 2 (default-deny host firewall, `os/rootfs/layers/onemind/usr/lib/onemind/host.nft`), D-007. **Does not replace** `CRITERIA.md` or `CRITERIA-FIRSTBOOT.md`. A port scan from network namespaces with real nftables (`test/net/host_firewall_scan.py`) covers the same rules without a VM; this file covers the shipped image.

## 1. Setup and rules

- Two VMs boot the `x86_64-efi` fixture image (with the QEMU test overlay). The **box** has the first-boot hub seed (`role: hub`); the **scanner** has no seed, so it has no role and runs the setup wizard. They are joined by a second NIC on a QEMU socket link, apart from the user-mode NIC the harness drives them through.
- On that link each side gets two addresses: a LAN pair (`192.168.77.1` box, `192.168.77.2` scanner) and a public-looking pair (`198.51.100.1`, `198.51.100.2`, a documentation range, outside every private range in `host.nft`).
- **Scan:** from each scanner address, TCP connects and UDP datagrams are sent to the box's matching address for these ports. TCP: 22, 80, 443, 445, 4222, 6443, 7422, 7443, 8080, 8443, 8444, 10250. UDP: 3478, 5353, 8472, 9999, 41641, 51820.
- **Dropped** is judged on the box, not from the scanner's silence: before the scan the harness appends one counting rule per source, protocol and port at the end of the `input` chain (they are reached only by packets no earlier rule accepted). A port is dropped when its counter is above zero after the scan, reachable when it is zero. A scan that dropped nothing at all (link down) is a FAIL, never a pass.
- The box is scanned only after the gateway answers `/healthz` with 200, so the real services are listening.
- Timeouts (wall clock): box first-boot line 900 s, gateway `/healthz` 900 s, scanner shell 600 s, scan 300 s.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such. Every verdict records the board, KVM or TCG, and the host CPU count.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| FW1 | LAN source sees only the LAN list | From the LAN address the reachable set is exactly TCP 443, 7443, 8443, 8444 and UDP 3478, 5353, 41641; every other scanned port is dropped | Any other port reachable, or any of those unreachable |
| FW2 | Public source sees nothing | From the public address no scanned port is reachable | Any port reachable |
| FW3 | The cluster is listening and unreachable | On the box `ss` shows TCP 6443 and 10250 listening on a non-loopback wildcard address (k3s is up) and FW1 and FW2 report both dropped | A port not listening (the test would prove nothing), or reachable |
| FW4 | Wizard only on the LAN, only without a role | With the scanner's wizard active (`onemind-setup.service`, answering 200 on its loopback), the box's connection to the scanner's 8080 succeeds from the LAN address and fails from the public address. On the box (role hub, no wizard) 8080 is dropped from the LAN (FW1) | Wizard reachable from the public address, unreachable from the LAN, or not running |

## 3. Not covered (reported, never claimed)

- Pod-to-host traffic and the forward path (H-04), IPv6, and rules loaded from `/etc/onemind/host.local.nft` by an owner.
- Cloud boards' own `host.d` rule (22, 443, 8443 from anywhere): covered by `CRITERIA-CLOUD.md` C2/C3, which need SSH and HTTPS to answer.
- Real hardware NICs.

## 4. Amendment (2026-11-25): FWP1, printing (CUPS, TCP 631) is LAN-only (Step 3, claude/s3-printing)

**Status:** PRE-REGISTERED before FWP1 was implemented in `firewall.py` or run, in the commit before the code that adds it. FW2, FW3 and FW4 above are unchanged. **FW1 changes in exactly one way:** the scan list gains TCP **631**, and the LAN-reachable TCP set becomes 443, **631**, 7443, 8443, 8444 (UDP unchanged). Every other port must still be dropped from the LAN, and nothing is reachable from the public address (FW2, unchanged). The sha256 of this file with this section is appended to `PREREGISTRATION.sha256`. **Serves:** the Step 3 printing lane: CUPS with driverless printing; the web admin and IPP port 631 open to the LAN and the mesh in `host.nft`, never to the internet; remote administration off by default.

The box's `cupsd` listens on every address (`Listen *:631`), so the firewall and CUPS's own access rules are both in play. FWP1 runs after FW4, from the scanner, against the box's real `cupsd` (the first-boot hub seed is the same as for FW1).

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| FWP1 | CUPS answers the LAN, never the public address, and never lets the LAN administer | From the LAN address `GET http://<box>:631/` returns HTTP 200 (a LAN client can reach the print service); from the LAN address `GET /admin`, `/admin/conf` and `/admin/log` each return HTTP 403 (remote administration is off); from the public address a connect to 631 does not open (no HTTP status, curl code 000); and the box's counters show 631 accepted from the LAN address and dropped from the public address (FW1 and FW2 judge the same counters) | 631 unreachable from the LAN, an admin page other than 403 from the LAN, any answer from the public address |

Required for this task's "done": FW1 to FWP1 PASS on x86_64-efi. It is written without having run QEMU on this lane's machine; a harness bug found on the first run may be fixed and re-run once, named as such, under section 1's rule.
