<!-- SPDX-License-Identifier: Apache-2.0 -->
# LoRa link check: ThinkNode-M2 on MeshCore (#853)

This kit checks, on the real hub and the real radio, what the LoRa messenger plan assumes before the hub driver
(#740) is built. It is **passive**: it reads, it never transmits and never sets frequency or power.

What it checks:
1. The hub's kernel has the `ch341` driver and it claims the radio's USB chip (CH340K, USB id `1a86:7522`).
2. Plugging in the M2 gives a `/dev/ttyUSB*` serial port from the `ch341` module: the USB interface is bound to `ch341` and the port to `ch341-uart`.
3. The radio answers MeshCore's documented handshake at 115200 baud: `APP_START` gets `SELF_INFO` (frequency,
   bandwidth, spreading factor, coding rate, transmit power) and `DEVICE_QUERY` gets `DEVICE_INFO` (firmware).
4. The no-transmit check: the radio's own packet counters (`GET_STATS`) are read right after the port opens,
   after the handshake and after 10 minutes idle. The sent count must not rise.
5. The reply frames are saved, with the radio's public key, name, advert location and Bluetooth PIN replaced
   by fixed test values, as test vectors for the messages contract (#855, `sdk/contracts/meshcore/frames.json`).

Words used here:
- **MeshCore:** the open (MIT) LoRa mesh firmware OneMind 1.0 is built on (founder decision, 2026-11-22).
- **Companion (USB):** the MeshCore build a computer drives over a USB cable. **Companion (Bluetooth)** is the
  build a phone drives. One radio runs one of them at a time.
- **Frame:** one message on the serial cable. The app sends `<`, a 2-byte length and the bytes; the radio
  answers with `>`, a 2-byte length and the bytes.
- **Preset:** the set of radio settings (frequency, bandwidth, spreading factor, coding rate) every radio in
  one mesh must share.

## Founder steps first (the kit never does these)

1. **Flash MeshCore.** Open MeshCore's official flasher, https://flasher.meshcore.io, in Chrome. Pick
   **Elecrow ThinkNode M2** and flash **Companion (USB)**. From a Mac, install WCH's CH34x driver first (the
   M2 showed no serial port on the Mac without it), or flash from a Linux PC.
2. **Set the US preset and power in MeshCore's own client** (for example the MeshCore web or phone app),
   before anything else:
   - preset **USA/Canada**: **910.525 MHz**, **SF7**, bandwidth **62.5 kHz**, coding rate **4/5**
     (MeshCore `docs/radio_presets.md`);
   - transmit power **19 dBm** or lower. The M2's FCC grant (FCC ID 2BDNA-CL06) is 0.08123 W, about
     19.1 dBm, and the M2's MeshCore build starts at 22 dBm on an EU frequency (869.618 MHz).
   - Do not send a message or an advert from that client during setup if you can avoid it; if you do, it does
     not spoil this check (the counters are compared within one run).
3. **Plug the M2 into the hub's USB.** If the hub is a virtual machine, pass the USB device `1a86:7522`
   through to it (for example Proxmox: VM > Hardware > Add > USB Device > "Use USB Vendor/Device ID") and
   write down how in `RESULTS.md`.

## Run it

On the hub (Debian 13), from a copy of the repo:

```bash
test/lora/link-check/link-check.sh --preflight-only   # driver and port only, a few seconds
test/lora/link-check/link-check.sh                     # the full check, about 11 minutes
```

Options by environment: `PORT=/dev/ttyUSB1` picks a port, `IDLE_SECONDS=600` sets the idle wait, `OUT=dir`
sets where results go (default `./link-check-results/<time>/`). Read access to the port needs root or the
`dialout` group. If ModemManager is running, stop it for the check (it can probe new serial ports).

It writes, in the results folder:
- `preflight.txt`: kernel, driver and port lines, each marked works / fails / partial;
- `report.json`: firmware, radio settings, each check's state, the stats read three times, and which commands
  were sent (only `01`, `16` and `38`);
- `captured-frames.json`: the reply frames, redacted, with their decoded fields.

Then fill in `RESULTS.md` (copy it next to the results first) and attach the three files to #853.
`python3 -I test/lora/link-check/link_check.py decode <dir>/captured-frames.json` re-decodes the saved frames
and must say `decode: ok`.

## Why it is safe

- `link_check.py` has an allowlist encoder: it can only build `APP_START` (0x01), `DEVICE_QUERY` (0x16) and
  `GET_STATS` (0x38). Every other command, including send, advert, radio settings, key export and reboot, is
  refused before a byte is written (unit test: `test/unit/test_lora_link_check.py`).
- While idle it only listens. Push frames (adverts heard from others, "message waiting") are counted by type
  and never saved, because they carry other people's keys.
- A MeshCore companion only advertises when asked (MeshCore FAQ 2.4). If the sent count still rises, the
  check says `fails` and lists the push frames seen. One known cause outside the kit: the firmware answers a
  direct message from another radio with an acknowledgement, which is a transmission; a freshly flashed radio
  that never advertised has no contacts to receive one from.
- Opening a serial port can restart an ESP32 board. The kit reads the radio's uptime with each count; if it
  went down, the counters were reset and the check says `partial` (run it again).
- Python standard library only. The MeshCore Python packages (`meshcore`, `meshcore-cli`, MIT) were used as
  references for the frame layouts but are not installed: their API can set radio settings and send in one
  call, and the allowlist encoder is the stronger guarantee. Nothing from this kit goes into the OS image.

## Not covered here

- **Companion (Bluetooth)** (optional, needs a reflash or the second radio): checked by hand from an Android
  phone with a generic BLE scanner; the steps are in `RESULTS.md`.
- Sending and receiving messages: that is the two-radio proof (#860), after the driver (#740) and the guard
  (#857).

## Test vectors

`testdata/doc-frames.json` holds frames built from the documented layouts with example values. They are not a
capture. The kit's unit test decodes them and drives the whole run against a simulated radio on a
pseudo-terminal. After #855 merges, the founder's `captured-frames.json` entries are added to
`sdk/contracts/meshcore/frames.json`.
