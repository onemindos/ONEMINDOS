#!/usr/bin/env -S python3 -I
# SPDX-License-Identifier: Apache-2.0
"""GUI runtime bake-off (issue #786): open a desktop app's stream in headless Chromium and measure it.

  bakeoff.py run --runtime neko --url http://127.0.0.1:8080 --container NAME --host-label LABEL --out FILE
      Logs in, waits for the first video frame, then checks: clipboard viewer -> desktop, clipboard desktop -> viewer,
      audio packets, resize, reconnect. Records latency numbers (WebRTC round trip, jitter buffer, decode, resize,
      reconnect, desktop -> viewer clipboard). The password comes from BAKEOFF_PASSWORD, never from the command line.
  bakeoff.py pick FILE [FILE ...]
      Prints the runtime OneMind ships: the first in the order neko, selkies, xpra whose run passed every check.

test/gui/run-bakeoff.sh builds the base and the Obsidian test image on a lab box and calls `run`. Needs Python
Playwright with Chromium (`pip install playwright && playwright install chromium`) and docker for `--container`.
Exit codes: 0 pass (or a winner), 1 a check failed (or no runtime passed), 2 usage or environment error.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import secrets
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "tools"))
from factorylib.desktop import RUNTIME_ORDER, RUNTIMES  # noqa: E402

CHECKS = ("stream", "clipboard_to_desktop", "clipboard_from_desktop", "audio", "resize", "reconnect")
SCHEMA = "onemind.bakeoff/v1"

# Keeps every RTCPeerConnection and the last WebSocket messages, so the run can read WebRTC stats and see what the
# runtime's client receives (the desktop's clipboard arrives over the client's WebSocket).
HOOK = """(() => {
  const PC = window.RTCPeerConnection; window.__pcs = [];
  window.RTCPeerConnection = function (...a) { const pc = new PC(...a); window.__pcs.push(pc); return pc; };
  window.RTCPeerConnection.prototype = PC.prototype;
  const WS = window.WebSocket; window.__ws = [];
  window.WebSocket = function (...a) {
    const ws = new WS(...a);
    ws.addEventListener('message', e => { window.__ws.push([Date.now(), String(e.data).slice(0, 4000)]);
                                          if (window.__ws.length > 500) window.__ws.shift(); });
    return ws;
  };
  window.WebSocket.prototype = WS.prototype;
  Object.assign(window.WebSocket, {CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3});
})();"""
FRAME = "w => { const v = document.querySelector('video'); return !!v && v.readyState >= 2 && v.videoWidth === (w || v.videoWidth) && v.videoWidth > 0; }"
STATS = """async () => {
  const out = {};
  for (const pc of window.__pcs) {
    if (pc.connectionState === 'closed') continue;
    (await pc.getStats()).forEach(r => {
      if (r.type === 'inbound-rtp') out[r.kind] = {packets: r.packetsReceived || 0, jb: r.jitterBufferDelay || 0,
        jbn: r.jitterBufferEmittedCount || 0, dec: r.totalDecodeTime || 0, frames: r.framesDecoded || 0};
      if (r.type === 'candidate-pair' && r.nominated && r.currentRoundTripTime !== undefined) out.rtt = r.currentRoundTripTime;
    });
  }
  return out;
}"""


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100), rounded to 0.1 ms; None for no samples."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, math.ceil(q / 100 * len(vals)) - 1))
    return round(vals[k], 1)


def verdict(checks: dict) -> bool:
    """A runtime passes only when every check ran and passed; a missing or skipped check is a failure."""
    return all(checks.get(c) is True for c in CHECKS)


def pick_runtime(results: list[dict]) -> str | None:
    """The first runtime in RUNTIME_ORDER with a passing run. Never two: a later runtime counts only when every
    earlier one has a failing run on record (Selkies is not chosen because nobody tried Neko)."""
    by = {}
    for r in results:
        if r.get("schema") != SCHEMA or r.get("runtime") not in RUNTIMES:
            raise ValueError(f"not a bake-off result: {r.get('runtime')!r}")
        by.setdefault(r["runtime"], []).append(verdict(r.get("checks") or {}))
    for name in RUNTIME_ORDER:
        if name not in by:
            return None
        if any(by[name]):
            return name
    return None


class Neko:
    """Neko v3 API (server/internal/api in m1k1o/neko v3.2.0): /api/login, /api/room/control/take,
    /api/room/clipboard, /api/room/screen."""

    def __init__(self, page, url: str):
        self.page, self.url, self.headers = page, url.rstrip("/"), {}

    def login(self, user: str, password: str) -> None:
        r = self.page.context.request.post(f"{self.url}/api/login", data={"username": user, "password": password})
        if not r.ok:
            raise RuntimeError(f"login refused: HTTP {r.status}")
        body = r.json() or {}
        token, self.session_id = body.get("token"), body.get("id")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.user, self.password = user, password

    def open(self, timeout_ms: int) -> None:
        self.page.goto(self.url)
        try:
            self.page.wait_for_function(FRAME, arg=0, timeout=5000)
            return
        except Exception:  # noqa: BLE001 - the client wants its login form
            pass
        self.page.fill("input[type=text]", self.user)
        self.page.fill("input[type=password]", self.password)
        self.page.click("button[type=submit]")
        self.page.wait_for_function(FRAME, arg=0, timeout=timeout_ms)

    def take_control(self) -> None:
        """Become the host: Neko serves the clipboard to the host session only (auth.HostsOnly). Admin only."""
        r = self.page.context.request.post(f"{self.url}/api/room/control/take", headers=self.headers)
        if not r.ok:
            raise RuntimeError(f"control take: HTTP {r.status}")

    def give_host_to_viewer(self) -> None:
        """Hand host to the browser tab's own session, so the desktop's clipboard reaches the viewer.

        This API login and the tab's login are two sessions of one member; Neko pushes desktop clipboard changes
        to the host session's WebSocket only (websocket/manager.go OnClipboardUpdated).
        """
        r = self.page.context.request.get(f"{self.url}/api/sessions", headers=self.headers)
        live = [x["id"] for x in (r.json() if r.ok else []) or []
                if x.get("id") != self.session_id and (x.get("state") or {}).get("is_connected")]
        if len(live) != 1:
            raise RuntimeError(f"expected one connected viewer session, found {len(live)}")
        g = self.page.context.request.post(f"{self.url}/api/room/control/give/{live[0]}", headers=self.headers)
        if not g.ok:
            raise RuntimeError(f"control give: HTTP {g.status}")

    def set_clipboard(self, text: str) -> None:
        r = self.page.context.request.post(f"{self.url}/api/room/clipboard", data={"text": text}, headers=self.headers)
        if not r.ok:
            raise RuntimeError(f"clipboard set: HTTP {r.status}")

    def get_clipboard(self) -> str:
        r = self.page.context.request.get(f"{self.url}/api/room/clipboard", headers=self.headers)
        return (r.json() or {}).get("text", "") if r.ok else ""

    def screen(self, width: int, height: int, rate: int = 30) -> None:
        r = self.page.context.request.post(f"{self.url}/api/room/screen", headers=self.headers,
                                           data={"width": width, "height": height, "rate": rate})
        if not r.ok:
            raise RuntimeError(f"screen change: HTTP {r.status}")


def desktop_clipboard(container: str, text: str) -> None:
    """Set the clipboard on the desktop side, as an app on the desktop would (xclip ships in the Neko base)."""
    subprocess.run(["docker", "exec", "-i", container, "xclip", "-selection", "clipboard", "-i"],
                   input=text, text=True, check=True, timeout=30)


def wait_ws(page, nonce: str, since_ms: int, timeout_s: float) -> float | None:
    """Milliseconds from since_ms until the page's WebSocket carried nonce, or None."""
    end = time.time() + timeout_s
    while time.time() < end:
        hit = page.evaluate("([n, t]) => (window.__ws.find(m => m[0] >= t && m[1].includes(n)) || [null])[0]", [nonce, since_ms])
        if hit:
            return hit - since_ms
        time.sleep(0.02)
    return None


def run(args) -> dict:
    from playwright.sync_api import sync_playwright  # lab box only; not a CI dependency

    if args.runtime != "neko":
        raise SystemExit(f"{args.runtime}: no driver yet. It is tried only after a failing Neko run (see `pick`).")
    password = os.environ.get("BAKEOFF_PASSWORD", "")
    checks: dict[str, bool] = {c: False for c in CHECKS}
    lat: dict[str, list[float]] = {"rtt": [], "jitter_buffer": [], "decode": [], "clipboard_desktop_to_viewer": []}
    single: dict[str, float | None] = {"first_frame": None, "resize": None, "reconnect": None}
    notes: list[str] = []
    timeout = args.timeout * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        ctx.add_init_script(HOOK)
        page = ctx.new_page()
        rt = Neko(page, args.url)
        try:
            rt.login(args.user, password)
            t = time.monotonic()
            rt.open(timeout)
            single["first_frame"] = round((time.monotonic() - t) * 1000, 1)
            checks["stream"] = True
            page.mouse.click(640, 360)                               # some clients wait for a gesture before audio
            rt.take_control()
            nonce = "om-" + secrets.token_hex(6)
            rt.set_clipboard(nonce)
            checks["clipboard_to_desktop"] = rt.get_clipboard() == nonce
            if args.container:
                rt.give_host_to_viewer()
                for _ in range(args.samples):
                    nonce = "om-" + secrets.token_hex(6)
                    since = page.evaluate("Date.now()")
                    desktop_clipboard(args.container, nonce)
                    ms = wait_ws(page, nonce, since, 10)
                    lat["clipboard_desktop_to_viewer"].append(ms)
                checks["clipboard_from_desktop"] = all(v is not None for v in lat["clipboard_desktop_to_viewer"])
            else:
                notes.append("clipboard_from_desktop needs --container (docker exec xclip on the desktop side)")
            a0 = (page.evaluate(STATS).get("audio") or {}).get("packets", 0)
            for _ in range(args.samples):
                time.sleep(0.5)
                s = page.evaluate(STATS)
                v = s.get("video") or {}
                if s.get("rtt") is not None:
                    lat["rtt"].append(s["rtt"] * 1000)
                if v.get("jbn"):
                    lat["jitter_buffer"].append(v["jb"] / v["jbn"] * 1000)
                if v.get("frames"):
                    lat["decode"].append(v["dec"] / v["frames"] * 1000)
            checks["audio"] = (page.evaluate(STATS).get("audio") or {}).get("packets", 0) > a0
            t = time.monotonic()
            rt.screen(1920, 1080)
            page.wait_for_function(FRAME, arg=1920, timeout=timeout)
            single["resize"] = round((time.monotonic() - t) * 1000, 1)
            rt.screen(1280, 720)
            page.wait_for_function(FRAME, arg=1280, timeout=timeout)
            checks["resize"] = True
            t = time.monotonic()
            rt.open(timeout)
            single["reconnect"] = round((time.monotonic() - t) * 1000, 1)
            checks["reconnect"] = True
        except Exception as exc:  # noqa: BLE001 - recorded as the failing step
            notes.append(f"stopped: {type(exc).__name__}: {str(exc)[:300]}")
        finally:
            browser.close()
    latency = {k: v for k, v in single.items()}
    for k, vals in lat.items():
        latency[f"{k}_p50"], latency[f"{k}_p95"] = percentile(vals, 50), percentile(vals, 95)
    return {"schema": SCHEMA, "runtime": args.runtime, "runtime_licence": RUNTIMES[args.runtime]["licence"],
            "host": args.host_label, "arch": platform.machine(), "app": args.app, "samples": args.samples,
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checks": checks,
            "passed": verdict(checks), "latency_ms": latency, "notes": notes}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bakeoff.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--runtime", choices=RUNTIME_ORDER, default="neko")
    r.add_argument("--url", required=True)
    r.add_argument("--user", default="admin")
    r.add_argument("--container", help="docker container of the desktop, for the desktop -> viewer clipboard check")
    r.add_argument("--app", default="obsidian")
    r.add_argument("--host-label", required=True, help="where it ran, e.g. 'daily-use hub' (no addresses)")
    r.add_argument("--samples", type=int, default=10)
    r.add_argument("--timeout", type=int, default=60, help="seconds to wait for a frame")
    r.add_argument("--out", type=Path, required=True)
    k = sub.add_parser("pick")
    k.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "pick":
            win = pick_runtime([json.loads(f.read_text(encoding="utf-8")) for f in args.files])
            print(win or "no runtime passed: try the next one in the order " + ", ".join(RUNTIME_ORDER))
            return 0 if win else 1
        res = run(args)
    except (OSError, ValueError, ImportError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    args.out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": res["passed"], "checks": res["checks"], "latency_ms": res["latency_ms"]}, indent=2))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
