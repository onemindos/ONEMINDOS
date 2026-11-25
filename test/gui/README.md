<!-- SPDX-License-Identifier: Apache-2.0 -->
# GUI runtime bake-off (issue #786)

**What this is.** Some apps only exist as desktop programs (Obsidian, LibreOffice, a browser). The box has no screen,
so such an app runs inside a container with a virtual screen, and a *streaming runtime* sends that screen to a
browser tab and sends the mouse, keyboard and clipboard back. OneMind ships **one** runtime. That way there is one
image to patch, one security review and one client. This folder holds the test that picks it.

**The order.** Neko (Apache-2.0) is tried first, because the Browsers row (#593) already uses it. Selkies (MPL-2.0)
is tried only if Neko fails, and Xpra (GPL-2.0-or-later) only if both fail. `bakeoff.py pick` enforces this order:
a later runtime never wins unless every earlier one has a failing run on record.

## Files

| File | What it does |
|---|---|
| `../../apps/_bases/desktop/` | The shared base: Neko 3.2.0 on Debian 13, pinned by digest, uid 1000, no setuid files, no Widevine, licence notices inside. Checked by `sdk/tools/app-factory base-check` (CI), built by `app-factory base-build desktop` (Trivy scan, CycloneDX SBOM, plus BuildKit SBOM and provenance when pushed). |
| `obsidian/` | A test image only: Obsidian on the base. Obsidian's licence does not allow us to pass it on, so the build downloads the `.deb` from GitHub and checks it against GitHub's sha256. The file is never committed and the image is never pushed. |
| `bakeoff.py run` | Opens the stream in headless Chromium and checks: first video frame, clipboard viewer to desktop, clipboard desktop to viewer, audio packets arriving, resize, reconnect. Records latency. |
| `bakeoff.py pick` | Reads result files and prints the runtime OneMind ships. |
| `run-bakeoff.sh` | The lab kit: builds both images locally, starts the desktop as uid 1000 with every capability dropped and ports on 127.0.0.1 only, runs `bakeoff.py`, removes the container. |

Run it on a Linux box with docker, Trivy and Python Playwright (`pip install playwright pyyaml jsonschema &&
playwright install --with-deps chromium`), from the repo root:

```sh
test/gui/run-bakeoff.sh "daily-use hub" bakeoff-neko.json
python3 -I test/gui/bakeoff.py pick bakeoff-neko.json
```

## Measured numbers

**Run 1, 2026-11-22 03:50 UTC.** Neko 3.2.0 with Obsidian 1.15.1, 1280x720 at 30 fps, on an 8 vCPU x86_64 cloud build
VM (one of the project's build workers). This is **not** the daily-use hub. The viewer was on the same machine, so the
network round trip is close to zero. Every check passed, so `pick` chooses **Neko**.

| Check | Result |
|---|---|
| Stream (first video frame) | pass, 6505 ms from opening the page (includes the client's login) |
| Clipboard viewer to desktop | pass |
| Clipboard desktop to viewer | pass, p50 129 ms, p95 152 ms (10 samples) |
| Audio (WebRTC audio packets arriving) | pass |
| Resize 1280x720 to 1920x1080 | pass, 268 ms until a frame of the new size |
| Reconnect (page reload) | pass, 1217 ms until the first frame |
| WebRTC round trip | p50 1.0 ms, p95 1.0 ms (same machine) |
| Jitter buffer delay | p50 23.9 ms, p95 24.0 ms |
| Video decode time per frame | p50 2.3 ms, p95 2.3 ms |

The base image scan (Trivy 0.76.2, CRITICAL and HIGH only, same day): 0 CRITICAL with a fix available, 6 CRITICAL
with no fix yet, 23 HIGH with a fix available, 318 HIGH with no fix. The image reports Debian 13 and uid 1000, and has
no setuid or setgid file.

**Still to do:** run the same kit on the daily-use hub (Dell AIO) and add its numbers here. The audio check only shows
that audio packets arrive; it does not prove that you can hear the sound. Nobody looked at the screen to confirm that
the window in the stream was Obsidian (UNVERIFIED).

## Turning the runtime's own login off

Each desktop app normally has its own Neko password. A later session broker may switch that login off (Neko's
`noauth` member provider) so the gateway's sign-in is the only one. `sdk/tools/validate-apps` check 12 allows this only
if the NetworkPolicies the gateway writes for the app let in the gateway and nothing else. That means the gateway's
proxy namespace, and the gateway host on the web port. The app's own namespace also counts, but only when the desktop
is the app's single pod. The check also refuses the switch when another app depends on this one, when the app has host
ports, or when the app ships its own NetworkPolicy or Ingress.
