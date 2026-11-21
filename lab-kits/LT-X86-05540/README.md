# LT-X86-05540 · Dell Latitude 5540 as a OneMind client (laptop tester)

**Status:** kit-ready (blocked: founder-hardware; nothing here has run on the laptop yet) · **Time:** about 2 hours · **Serves:** D-004 (the Dell is existing hardware), the clients plan `docs/umbrel2/clients.md` (CLIENT-8 desktop app, CLIENT-10 approvals), the dashboard.
**Id note:** `LT-X86-02` is already taken in `research-output/22-HARDWARE-LAB-TEST-PLAN.md` (ten power pulls), and no planned id exists for a client test, so this kit uses the sprint id `LT-X86-05540`. Rename it if Zeus prefers another.
**Criteria:** this kit has no row in 22, so the pass rules are in this file ([§ Pass / fail](#pass--fail)), written before the run.

> **Explain it like I'm the founder.** Until now the Dell was only a test *server* (RAUC, Secure Boot, power pulls). But most people will meet OneMind from a **laptop**: pair it with the hub, open the dashboard, approve a request, close the lid, plug in a dock, lose the internet. This kit checks that laptop life. The laptop is the client; the hub is any OneMind box already running (the Beelink, a VM). The kit **never installs anything on the Dell's internal disk**: Windows stays for the desktop-app leg, and a Debian 13 live USB (D-007) covers the Linux leg. AI never actuates here: the only thing you do to the hub is look at it and approve a request yourself.

## What you need
- The Dell 5540 with its charger, a dock or USB-C monitor adapter plus one external monitor, headphones, and a phone hotspot or a router you can unplug from the internet.
- A running hub on the same LAN with the owner token (the owner mints it; paste it into the app, never into this repo).
- Leg W (Windows, existing install): the desktop installer from CI (`ci-desktop` artifact, `OneMind_0.1.0_x64-setup.exe`; build steps in `desktop/README.md`).
- Leg L (Linux): a Debian 13 live USB (the installer stick from `os/boards/installer-x86_64/README.md` also boots live). Secure Boot may stay on.
- Placeholders below: `<hub-ip>` is the hub's LAN address. Never paste real addresses, MACs or tokens into the result.

## Steps
Set `export HUB=http://<hub-ip>:8080` on Leg L. Take a snapshot at every stage: `sh lab-kits/LT-X86-05540/client-probe.sh snapshot NAME`. It is read-only, redacted, and written to `./snap-NAME.txt`. Compare two with `... compare A B`.

### 1. Pair with the hub (both legs)
1. Leg W: install and open the tray app, let it find the hub (mDNS) or type `<hub-ip>:8080`, paste the owner token. Expect the status card to show nodes online and "Live".
2. Leg L: `curl -s $HUB/healthz` prints ok. Then in Firefox or Chromium open `$HUB` and sign in.
3. Fail if: pairing needs a retry, the token ends up in a plain file (Leg W stores it in Windows Credential Manager), or the status card shows green for something marked "not reported yet".

### 2. Dashboard and desktop app
- Dashboard (both legs): open it, visit Home, Apps, Backups and Nodes. Note the load time of the first screen and any layout break at the 1920x1080 and 1366x768 sizes (resize the window).
- Desktop app (Leg W): open a pending approval (ask the owner to file one, for example an app restart), read its plan, press **Approve** only if you mean it, or **Deny** with a reason. The banner must never approve by itself. **Open dashboard** must open the system browser.

### 3. Wi-Fi and Bluetooth toggle, then reboot
1. `snapshot wifi-on`. Turn Wi-Fi off with the keyboard key, then `snapshot wifi-off`: `compare wifi-on wifi-off` must show the change. Same for Bluetooth. Turn both on. The hub must read UP again within 30 seconds of Wi-Fi returning.
2. Turn Bluetooth **off**, reboot, `snapshot after-reboot-bt-off`: it must stay off (state remembered). Turn it on, reboot, check again.
3. Pair one Bluetooth headset, reboot, confirm it reconnects without re-pairing.

### 4. Audio and webcam
Play a sound on speakers, then on headphones (the speakers must mute on plug-in). Record 5 seconds on the built-in microphone and play it back. Open the webcam (Cheese or the browser camera test). `snapshot media` must list a sink, a source and `/dev/video0`.

### 5. Sleep and wake
1. `snapshot pre-sleep`. Close the lid on battery for 2 minutes, open it. Repeat on the charger.
2. `snapshot post-sleep`. `suspend_success` must go up by 2 and `suspend_fail` must not change. Wi-Fi must reconnect and the hub read UP within 30 seconds, with no sign-in prompt. Leg W: the tray status must refresh by itself within a minute.
3. Note the wake time (lid open to usable screen) and any lost audio, camera or Bluetooth.

### 6. Dock and displays
1. `snapshot undocked`. Plug in the dock (power, monitor, Ethernet, keyboard). `snapshot docked`: the external display must read `connected`, the charger `online=1`.
2. Mirror, extend, then close the lid with the external monitor on: the session must stay up. Unplug the dock with the lid closed: the laptop must sleep or stay locked, not crash.
3. Wi-Fi and Ethernet both up: unplug Ethernet, the hub must stay reachable (watch with step 7's command).

### 7. WAN loss
The point: the hub on the LAN must stay usable when the internet goes away. On Leg L run `COUNT=60 INTERVAL=5 sh lab-kits/LT-X86-05540/client-probe.sh wan-watch | tee wan.txt` and, from the router, cut the hub's internet (not the LAN) for 3 minutes, then restore it.
- Expect: `hub UP` the whole time (the client talks to the hub over the LAN), the dashboard Home still loads, the desktop app card says old data honestly (the "how old" label) instead of green-for-everything. After restore, the app returns to normal within 60 seconds with no re-pairing.
- Then also cut the **laptop's** link to the hub for 60 seconds (Wi-Fi off): the app must show "unreachable", not crash, and recover on its own.

### 8. Record
Run any pasted log through `sh lab-kits/common/redact.sh`, then fill [RESULT.template.md](RESULT.template.md) (based on `../common/RESULT-TEMPLATE.md`) and save it as `research-output/evidence/lab/founder-hardware/LT-X86-05540.md`. Do not record serial numbers.

## Pass / fail
PASS needs every line below true:
1. Pairing works first time on both legs and the token is not stored in a plain file.
2. The dashboard renders on both screen sizes; the app never approves or actuates without your click.
3. Radio state changes show in snapshots; Bluetooth state survives a reboot; a paired headset reconnects.
4. Speakers, headphones, microphone and webcam all work; they are listed in `snapshot media`.
5. Two sleep and wake cycles: success count +2, fail count unchanged, hub UP again within 30 s.
6. Docking, mirroring, extending and undocking leave no crash; external display and charger states match.
7. With the hub's WAN cut, hub stays UP for 100 percent of the polls and the app recovers on its own.
FAIL on any line: write the exact step and message in the result. A FAIL files a client issue, it does not reopen any founder decision.

## Files
| File | What it is |
|---|---|
| `client-probe.sh` | Read-only snapshot, compare and `wan-watch` helper. Tested by `test/unit/test_lt_dell_5540_client.py` with stub tools. |
| `RESULT.template.md` | Result sheet with one line per step above. |
