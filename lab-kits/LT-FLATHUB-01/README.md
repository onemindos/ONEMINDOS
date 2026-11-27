<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-FLATHUB-01 · Desktop apps from Flathub: Obsidian in a browser tab

**Status:** kit-ready (needs a running OneMind box built with this change, internet access to Flathub, and a laptop) · **Serves:** #1097 acceptance (an owner finds Obsidian, approves the install, opens it in a browser tab; it is sandboxed; it survives a reboot and an A/B update; update and remove are approvals) · D-007, D-026, D-027

> **Explain it like I'm the founder.** The tests in the repo prove that the gateway files each request and only an owner approves it, that the host service sandboxes every app with one folder of its own, and that the image keeps Flatpak on `/data`. They use a stand-in for Flathub, because CI may have no network. They cannot prove that the real Flathub app (Obsidian, about 400 MB with its runtime) installs, runs and is shown on a screen you can reach. This kit does that: about 30 minutes and one reboot.

## Before you start
- A OneMind box running an image that includes this change. Open **Desktop apps** (Your box). If it says "not available yet", read the reason; the rest cannot start.
- The desktop session app (`desktop-apps`, the Neko runtime) must be installed for the last step of A. It is a separate change: until it lands, step A6 can only show that the launch file was written.

## A. Install and open (owner)
1. Desktop apps, search `obsidian`. **Expect:** `md.obsidian.Obsidian` is listed.
2. **Ask to install Obsidian**, then open the request in **Approvals** and approve it. **Expect:** nothing is installed before the approval; after it the action ends `succeeded` (a few minutes; the runtime downloads).
3. On the box: `sudo flatpak --installation=onemind list --app` shows Obsidian.
4. **Sandbox check, on the box:** `sudo flatpak --installation=onemind info --show-permissions md.obsidian.Obsidian` and `sudo flatpak --installation=onemind override --show md.obsidian.Obsidian`. **Expect:** `filesystem=` lists only `/data/onemind/desktop-apps/md.obsidian.Obsidian/files:rw` (no `host`, no `home`), and `org.freedesktop.Flatpak` is not in `[Session Bus Policy]`.
5. Desktop apps, **Open Obsidian**. **Expect:** `cat /data/onemind/desktop-session/launch` prints `md.obsidian.Obsidian`.
6. Open the desktop session from the page on a laptop. **Expect:** Obsidian in a browser tab; create a vault inside its granted folder, and a note.

## B. Survives a reboot and an A/B update
1. Reboot the box. Desktop apps still lists Obsidian; the note from A6 is still in `/data/onemind/desktop-apps/md.obsidian.Obsidian/files`.
2. Install an OS update to the other slot (Updates screen), reboot into it. **Expect:** the same list, the same note, and **Open Obsidian** works.

## C. Update and remove (owner approvals)
1. When Flathub has a newer Obsidian the row says "update waiting". **Ask to update**, approve it. **Expect:** the sandbox check from A4 gives the same answer afterwards.
2. `onemind desktop-app remove md.obsidian.Obsidian` prints an approval id and nothing else happens until an owner approves it in the dashboard. After the approval Obsidian is gone from the list; the note is still in its folder (removing an app keeps the owner's files).

## Result
Write the date, the box, the Obsidian version, and PASS or FAIL for A to C in the PR that updates the status table.
