# QEMU battery, NetworkManager on the hardware boards: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-24 before the step it judges (`netcheck.py`, run by `firstboot.py`, and FW5 in `firewall.py`) was implemented or run. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness output and CI logs).

**Serves:** "Step 2: the Debian bones", PR 3 (founder-approved 2026-11-24): the boards that are not cloud boards use NetworkManager, so a person can save a Wi-Fi or static profile and it survives a reboot. D-007 (Debian 13 base). The cloud boards, the installer and the recovery target keep systemd-networkd (recovery is covered by TD1-TD3, which run on this same image). **Does not replace** `CRITERIA.md` or `CRITERIA-FIRSTBOOT.md`.

## 1. Starting state and rules

- NW1-NW4 run on the slot-A boot of the first-boot battery (`firstboot.py`, board x86_64-efi), after F12 and before the F3 reboot; NW4 has a second half right after the F3 reboot. FW5 runs on the box of the firewall battery (`firewall.py`), which has a second NIC with a link and no DHCP server.
- QEMU's user-mode network (slirp) is the wired network: its DHCP server answers on the first NIC. **Wi-Fi cannot be tested in QEMU** (the guest has no radio). What is proved for Wi-Fi is only that the tools and the profile storage exist: `wpa_supplicant`, `iw`, `rfkill` are on the box, `wireless-regdb` is installed, and a saved profile survives a reboot (NW4). Association with an access point is for the hardware kit.
- The profile NW4 saves is a wired profile bound to a made-up interface name that does not exist, with autoconnect off, so it never takes part in the box's networking.
- Dummy network devices made by the harness are removed again at the end of NW3.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| NW1 | NetworkManager is the network, wired DHCP works, DNS goes through resolved | `/usr/lib/onemind/network-stack` says `networkmanager`; `systemctl is-enabled` prints `enabled` for `NetworkManager.service` and `NetworkManager-wait-online.service`; `systemd-networkd.service` is not `active`; `nmcli -t -f DEVICE,TYPE,STATE device` lists an ethernet device in state `connected`; that device has an IPv4 address and the box has a default route through it; `NetworkManager --print-config` shows `dns=systemd-resolved`; `resolvectl status` lists a DNS server on that device; `/etc/resolv.conf` is a link to the resolved stub; `wpa_supplicant`, `iw` and `rfkill` run (`--version`, `--version`, `list`) and `/lib/firmware/regulatory.db` exists | Any of these missing, networkd active, no address, or DNS not learned |
| NW2 | k3s waits for NetworkManager-wait-online | `systemctl show k3s -p After` contains `NetworkManager-wait-online.service` and `systemctl show k3s -p Wants` contains it; `NetworkManager-wait-online.service` became active at a monotonic time at or before the time k3s was started (`InactiveExitTimestampMonotonic` of k3s) | Not in `After=`, or k3s was started before wait-online finished |
| NW3 | The cluster's and the mesh's interfaces are left alone | `NetworkManager --print-config` shows `unmanaged-devices` naming `flannel*`, `cni0`, `veth*` and `tailscale0`; four dummy devices named `flannelnw0`, `cni0` (made only if k3s has not made it), `vethnw0` and `tailscale0` (only if absent) are each reported by `nmcli -g GENERAL.STATE device show <name>` as `unmanaged` after five seconds | A name missing from the config, or any of the four managed |
| NW4 | A saved profile survives a reboot | A profile `onemind-nw-probe` is added with `nmcli connection add`; its file exists under `/data/state/etc-NetworkManager-system-connections/` with mode 600, and `findmnt` shows `/etc/NetworkManager/system-connections` and `/var/lib/NetworkManager` as bind mounts from `/data`; after the F3 reboot (no input) `nmcli -g NAME connection show` lists `onemind-nw-probe`, its file's sha256 is unchanged, and the first-boot wired profile is up again. The profile is deleted at the end | Profile or file missing after the reboot, a different hash, a mode other than 600, or either folder not a bind mount from `/data` |
| FW5 | A second NIC with a link and no DHCP server does not delay "online" | On the firewall battery's box (a second NIC with a link, nothing answering DHCP on it) the time from the start of `NetworkManager.service` to the end of `NetworkManager-wait-online.service` (both `ActiveEnterTimestampMonotonic`) is at most 30 s, and k3s's `InactiveExitTimestampMonotonic` is not later than that end plus 10 s | The span is over 30 s (a card with no DHCP held the boot back: with `nm-online -s` or networkd it is 45 s or more), wait-online never became active, or k3s starts more than 10 s after wait-online |

## 3. Not covered (reported, never claimed)

- Wi-Fi association, WPA2/WPA3 handshakes, regulatory domain behaviour and Wi-Fi reconnect after a reboot: no radio in QEMU. Saved-profile persistence (NW4) is the part that can be proved.
- Real NICs, link-down and link-up events, VLANs, bonds, bridges.
- The cloud boards (cloud-init renders to networkd) and the installer stick: unchanged, so not part of this run.

## 4. Known harness reds this change must not be judged by

F3/B2 hang after a reboot (read-position race), B1 `hash_in_grub_cfg=1` and FW3 (k3s not yet listening at the scan) were red on fast hosts before this change (a local run on release/next at 8ae9db84). They are another workflow's fixes. FW3's cause includes the second NIC delaying k3s, which FW5 now judges directly.
