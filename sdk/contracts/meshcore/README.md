# MeshCore shared test vectors (issue #855)

One truth for every piece of code that talks to a MeshCore radio or decides whether it may send:

| File | Who must pass it |
|---|---|
| `frames.json` | the Go codec in `onemindd` (#740) and the TypeScript codec on the phone (#865): decode every `from_radio` frame to its `decoded` fields, encode every `to_radio` frame byte for byte, and have **no encoder** for an opcode on `deny` (radio settings, power, keys, reboot, raw data) |
| `guard.json` | the hub send guard (#857, Python) and the phone send guard (#865, TypeScript): return `expect` for every case |
| `vectors.schema.json` | the shape of both files; `sdk/tools/tests/test_meshcore_vectors.py` checks it and re-computes every guard case |

The message, radio, job, event and import shapes are JSON Schemas in `sdk/schema/` and the action specs and the built-in descriptor are in `core/onemind_core/messages/` (#855 part 1).

Rules the vectors encode:
- **OneMind never writes radio settings in 1.0.** It reads frequency, bandwidth, spreading factor, coding rate and power from `SELF_INFO` and refuses to send outside 902-928 MHz (the whole channel, not just its centre) or above the radio's FCC-granted power.
- **Every transmission is a person's tap.** Sends and adverts reach the radio only as signed jobs for an approved action; adverts are zero-hop.
- **Budget:** 60 s of airtime and 30 sends per rolling hour per radio, every retry counted.
- Frames from the founder's own radio are added by #853 (link check); key bytes here are made-up examples.

## Licence

The frame layouts and the example frames `app_start`, `device_query`, `get_channel`, `send_channel_txt_msg` and the parsing rules come from MeshCore's companion protocol documentation and firmware sources (https://github.com/meshcore-dev/MeshCore, `docs/companion_protocol.md`, `examples/companion_radio/MyMesh.cpp`, v1.18.0) and meshcore.js (https://github.com/meshcore-dev/meshcore.js), used under the MIT licence:

> MIT License. Copyright (c) 2025 Scott Powell / rippleradios.com (MeshCore). Copyright (c) 2025-2026 Liam Cottle (meshcore.js).
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

No Meshtastic code, protobufs or tables are used here or anywhere in this repository (`sdk/tools/tests/test_meshtastic_licence_guard.py`).
