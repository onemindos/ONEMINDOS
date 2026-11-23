<!-- SPDX-License-Identifier: Apache-2.0 -->
# LoRa link check results (#853)

Fill this in from one run of `link-check.sh` on the hub. Mark each check **works / fails / partial**.
Never paste the radio's public key, name, serial number or Bluetooth PIN here (the kit already replaced them in
its files).

## The run

| Field | Value |
|---|---|
| Date | |
| Hub (model, or VM on which host) | |
| Kernel (`uname -r`) and OS | |
| Radio | Elecrow ThinkNode-M2 |
| Flashed build | Companion (USB) |
| Firmware version (`report.json` radio.firmware) | |
| Firmware build date (radio.fw_build) | |
| Protocol version (radio.protocol_ver) | |
| Frequency / bandwidth / SF / CR | MHz / kHz / SF / 4/ |
| Transmit power (set in MeshCore's client) | dBm |

## Checks (works / fails / partial)

| # | Check | works / fails / partial | Notes |
|---|---|---|---|
| U1 | `modinfo ch341` on the shipped Debian 13 kernel, alias for `1a86:7522` | | |
| U2 | Plugging the M2 gives `/dev/ttyUSB*` bound to `ch341` | | port: |
| U3 | `APP_START` answered with `SELF_INFO` | | |
| U4 | `DEVICE_QUERY` answered with `DEVICE_INFO` | | |
| U5 | US preset read back: channel inside 902-928 MHz, power at most 19 dBm | | |
| U6 | No transmit: `GET_STATS` sent count equal before, after and at 10 min idle | | |
| U7 | `link_check.py decode captured-frames.json` says `decode: ok` | | |
| V1 | If the hub is a VM: USB passthrough of `1a86:7522` works | | how: |

## GET_STATS (from `report.json` stats)

| Read | Uptime (s) | sent | flood_tx | direct_tx | recv |
|---|---|---|---|---|---|
| before (port just opened) | | | | | |
| after (handshake done) | | | | | |
| 10 min idle | | | | | |

Push frames seen while idle (`push_frames_seen`):

## Bluetooth, optional (Companion (Bluetooth) build, on the second radio or after a reflash)

From an Android phone with a generic BLE scanner app. Passive: scan and pair only, send nothing.

| # | Check | works / fails / partial | Notes |
|---|---|---|---|
| B1 | The scanner sees service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` | | |
| B2 | Pairing works with the radio's PIN | | |
| B3 | Negotiated MTU | | bytes: |

## Frames for #855

- [ ] `captured-frames.json` attached to #853 (redacted by the kit; check by eye that no real name is in it).
- [ ] After #855 merges: its entries added to `sdk/contracts/meshcore/frames.json` as captured vectors.

## Anything odd
