<!-- SPDX-License-Identifier: Apache-2.0 -->
# Printing on OneMind OS (Step 3): what ships, where it lives, what a VM cannot prove

**Build step:** Step 3, Linux-native features, printing lane (`claude/s3-printing`). Tests: `test/qemu/CRITERIA-FIRSTBOOT.md` section 20 (FP1 to FP3) and `test/qemu/CRITERIA-FIREWALL.md` section 4 (FWP1).

## In plain words

**CUPS** is the print server every Linux desktop uses. It keeps a list of printers ("queues"), takes a print job from an app, turns it into what the printer understands, and sends it. **Driverless printing** (IPP Everywhere) means a modern printer describes itself over the network, so no vendor driver is needed: CUPS just asks the printer what it can do. **IPP** (Internet Printing Protocol) is the language for that, on port 631. **ipp-usb** lets a printer that is plugged in with a USB cable also speak IPP, so a USB printer is treated like a network one. **avahi** (already in the image for `onemind.local`) is what announces and finds printers on the home network (mDNS).

## What the image has

- Debian 13 packages from the pinned snapshot: `cups`, `cups-client`, `cups-daemon`, `cups-filters`, `cups-ipp-utils`, `ipp-usb`. **Not** `cups-browsed`: it would create a queue for every printer it hears on the network. On OneMind, adding a printer is an owner action. (Even without it, `cupsd` itself can make a temporary driverless queue for a printer it sees over DNS-SD when a local app prints. That queue is not permanent and nothing is shared; but "only the owner adds a printer" means no permanent queue appears by itself.)
- `cupsd` starts at boot (`cups.service`, Debian's unit plus `10-onemind.conf`).
- **Everything it writes is on `/data`**, because the root filesystem is read-only. Four bind mounts (in `/etc/fstab`): `/etc/cups` (settings and the printer list), `/var/spool/cups` (jobs waiting), `/var/cache/cups`, and `/var/lib/ipp-usb`, each from `/data/state/<name>`. Logs go to `/var/log/cups`, and `/var/log` is already on `/data`. So printers and settings survive a reboot and an A/B update.
- `/etc/cups` is seeded once, on the first boot of a data disk, from the image's copy (`/usr/lib/onemind/cups-default`, with OneMind's `cupsd.conf` on top). After that the `/data` copy is the owner's, and an update never overwrites it.
- **Cloud boards do not print.** `cloud` (AWS, Azure, GCP, Hetzner, Proxmox) and `vm-do` mask `cups.service`, `cups.socket`, `cups.path` and `ipp-usb.service` in their `post-install.sh`: a cloud server has no printer, and the private ranges `host.nft` trusts for 631 are the provider's network there.
- **Mesh clients:** CUPS's `@LOCAL` leaves out point-to-point interfaces, and `tailscale0` is one, so `<Location />` also says `Allow @IF(tailscale0)` (never on `/admin`). UNVERIFIED in a VM: check from a mesh peer on the Dell.

### Changing CUPS settings in a later image (migration)

The `/data` copy of `cupsd.conf` and `cups-files.conf` is frozen after the first boot, so a new image cannot change it by itself. If a later image must ship a CUPS security fix or a directive a CUPS upgrade needs, it adds a one-shot unit (ordered after `onemind-data-layout`, guarded by a version stamp such as `/data/state/etc-cups/.onemind-config-version`) that applies the specific edit to the `/data` copy (or, for a full reset, replaces it with the new seed and keeps a `.bak`), then writes the stamp. Printers (`printers.conf`) and PPDs are never touched. No such migration exists yet.

## Who can do what

| Who | What |
|---|---|
| Anyone on the LAN or the mesh | Reach port 631 and print to a queue the owner has shared. Nothing is shared by default (`DefaultShared No`, `Browsing No`). |
| Anyone on the LAN | **Cannot** open `/admin`: it answers 403. Remote administration is off by default. |
| The owner, on the box (localhost) | Opens `http://localhost:631/admin`, signs in as a member of `lpadmin` (root's password is locked), adds a printer. |
| The internet | Nothing: `host.nft` opens 631 from the private LAN ranges and the mesh interface only. |

The owner's shell user must be in the `lpadmin` group to administer (the owner-shell lane of Step 2 creates that user; add the group there). Turning on sharing is an owner step too: `cupsctl --share-printers`.

## How the tests prove it (QEMU)

- **FP1** (first boot): packages and tools present, no `cups-browsed`, `cupsd` active and listening on 631, the four mounts come from `/data/state`, remote admin and sharing off, `/` answers 200 and `/admin` answers 401, a non-owner user cannot add a queue, then the test (as the owner) adds a queue whose device is a file, prints CUPS's test page to it, and reads back `%PDF`. A `file:` device is refused by CUPS unless `FileDevice Yes` is set; `cupsctl` will not set it, so the test edits `cups-files.conf` and restarts `cups.service` for the add and the print only, then sets it back.
- **FP2** and **FP3**: after the reboot (F3) and after the A/B update (F4) the queue, its description and the defaults are still there and a second page prints.
- **FWP1** (second VM as scanner): from the LAN address, `/` answers 200 and `/admin`, `/admin/conf`, `/admin/log` answer 403; from the public address 631 does not answer; the firewall counters show 631 accepted from the LAN and dropped from the public address.

## What a VM cannot prove (do it on the Dell all-in-one)

1. A **real USB printer** is found by `ipp-usb` and shows up as a driverless queue (QEMU has no printer).
2. A **real network printer** is discovered over mDNS and prints.
3. **Paper, toner, print quality**, duplex, colour.
4. The dashboard's "add a printer" step end to end (this PR ships no dashboard screen: the engine is CUPS's own admin page on localhost).
5. **Sharing** the queue to a phone or laptop on the LAN, after the owner turns it on.
6. **`ipp-usb` runs as root on USB hot-plug** for any device that offers the IPP-over-USB interface (it listens on loopback only by default). Plug in the printer and check `systemctl status ipp-usb` and `ss -ltn` show only 127.0.0.1 sockets for it; try a non-printer USB stick and confirm nothing starts.
7. That a mesh peer (tailscale0) can print and still gets 403 on `/admin`.
8. That AppArmor's `cupsd` profile (Debian ships one) does not block a real backend: the VM test uses the `file:` device under `/run/cups`, which the profile allows; USB (`/dev/bus/usb`) and network backends are allowed by the same profile but are not exercised.
