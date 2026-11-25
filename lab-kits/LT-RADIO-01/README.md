<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-RADIO-01 · USB radios get stable names and radio-found cards (issue #732)

**Status:** kit-ready (needs:device-proof) · **Time:** about 20 minutes · **Serves:** #732, the first step of the 1.0 LoRa messenger's dock mode (#854 grant comes next)
**Hardware:** a OneMind hub on an image built from this branch, the Elecrow ThinkNode-M2 flashed with MeshCore Companion (USB), and a Home Assistant Connect ZBT-2 (or another dongle from `sdk/schema/onemind.radios.json`). Optional: any other USB serial adapter (FTDI, CP2102) as the "unknown" device.

> **In plain words.** When you plug a radio stick into the hub, Linux calls it something like `ttyUSB0`, and that name can change with every plug. The image now carries rules for udev (the part of Linux that reacts to plugged-in devices) that give each known radio a name that means something, such as `/dev/onemind/lora0`, and hand it to one group, `onemind-radio`, so later only an app you approve can open it. The ThinkNode-M2 uses a cheap, common USB chip (CH340K, id `1a86:7522`), so the id alone cannot prove it is a LoRa radio: its card asks you to confirm "MeshCore companion (USB)". OneMind never talks to the radio to find out.

## Pre-registered pass / fail (frozen with this commit)
| Step | PASS if | FAIL if |
|---|---|---|
| R1 Kernel | `modinfo ch341 \| grep -i 1a86p7522` prints an alias line | No alias: the M2 would not get a `ttyUSB` line |
| R2 Names | With the M2 and the ZBT-2 plugged in: `ls -l /dev/onemind/` shows `lora0 -> ../ttyUSB<n>` and `zigbee-thread0 -> ../ttyACM<n>`; `ls -lL /dev/onemind/*` shows group `onemind-radio`, mode `crw-rw----` | A name missing, wrong kind, or group/mode differ |
| R3 Unknown | A plugged FTDI or CP2102 adapter gets no name under `/dev/onemind/` and keeps group `dialout` | It is named or regrouped |
| R4 Cards | `curl -s -H "Authorization: Bearer $TOKEN" http://<hub>:8080/v1/radios` lists the M2 (`id: <node>.lora0`, kind `lora`, `match: id`, `device: /dev/onemind/lora0`, `confirm.confirmed: false`) and the ZBT-2 (`id: <node>.zigbee-thread0`, kind `zigbee-thread`, `device: /dev/onemind/zigbee-thread0`), each with its `usb_port`; the unknown adapter has `id: null`, `kind: null`, `device: null` | A card missing, or the unknown adapter named |
| R5 Confirm | `curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"profile":"meshcore-companion-usb"}' http://<hub>:8080/v1/radios/<node>.lora0/confirm` returns the card with `confirm.confirmed: true`; the M2's display shows no new message or advert (nothing was sent) | Refused for the owner, or the radio did anything |
| R6 Unplug | Unplug both: within one heartbeat (10 s) both cards are gone from `/v1/radios` and `/dev/onemind/` is empty; plug the M2 back into the same USB port: `lora0` again with the same `id`, `confirm.confirmed: true`; plug it into another port: `confirm.confirmed: false` | A card stays, the id changes, the confirmation is lost on the same port, or kept on another port |
| R7 Reboot | With the M2 confirmed on its port, reboot the hub (`ssh admin@<hub> sudo systemctl reboot`): after boot the M2's card has the same `id` and `confirm.confirmed: true` | The id changes or the confirmation is asked again |

**Verdict:** PASS if R1 to R7 pass.

## Steps
1. Boot the hub from this branch's image (CI `image` workflow artifact, or `make image BOARD=x86_64-efi`). Get the owner token as in LT-X86-01 and `export TOKEN=...` in your own shell (never paste it into a result file).
2. R1: `ssh admin@<hub> modinfo ch341 | grep -i 1a86p7522`.
3. Plug in the M2, then the ZBT-2. R2: `ssh admin@<hub> 'ls -l /dev/onemind/; ls -lL /dev/onemind/*; sudo cat /run/onemind-radio/*'` (the last command shows which line holds each name).
4. R3: plug the other adapter; `ls -l /dev/onemind/ /dev/ttyUSB*`.
5. R4 to R7 with the `curl` commands above. Your node id is in `curl -s -H "Authorization: Bearer $TOKEN" http://<hub>:8080/v1/nodes`.
6. Record each step's output in `RESULT.md` beside this file, passing the raw output through `sh lab-kits/common/redact.sh < raw.txt` (no serial numbers, radio public keys, tokens or addresses in the public repo).
