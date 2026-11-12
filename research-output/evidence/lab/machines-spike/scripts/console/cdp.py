#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LAB-machines-spike M2: open the console page in headless Chromium, driven over DevTools on a pipe
(stdlib only). Waits for RFB connect and a non-blank canvas, types "root" + Enter as real key events,
measures how many canvas pixels changed, and saves screenshots and a result JSON.

  cdp.py <page url> <out dir> <label>
"""
import base64, json, os, subprocess, sys, time

CONNECT_S, TYPE_S, MIN_NONBLACK, MIN_CHANGED = 60, 10, 1000, 100

class CDP:
    def __init__(self, wfd, rfd):
        self.w, self.r, self.buf, self.n = wfd, rfd, b"", 0

    def call(self, method, params=None, session=None):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        while True:
            reply = self._recv()
            if reply.get("id") == self.n:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def _recv(self):
        while b"\0" not in self.buf:
            chunk = os.read(self.r, 1 << 20)
            if not chunk:
                raise EOFError("chromium closed the DevTools pipe")
            self.buf += chunk
        raw, self.buf = self.buf.split(b"\0", 1)
        return json.loads(raw)

def main():
    url, out, label = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    to_child_r, to_child_w = os.pipe()
    from_child_r, from_child_w = os.pipe()
    # The pipes hold the lowest free fds (3..6), so Popen's own error pipe lands above 4. Park copies at
    # high fds and map them to 3 (commands in) and 4 (replies out) in the child, as Chromium expects.
    os.dup2(to_child_r, 100); os.dup2(from_child_w, 101)

    def child_fds():
        os.dup2(100, 3); os.dup2(101, 4)

    proc = subprocess.Popen(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
                             "--remote-debugging-pipe", "--window-size=1400,1000",
                             f"--user-data-dir=/tmp/machlab-chrome-{label}", "about:blank"],
                            preexec_fn=child_fds, pass_fds=(3, 4), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for fd in (100, 101, to_child_r, from_child_w):
        os.close(fd)
    cdp = CDP(to_child_w, from_child_r)
    res = {"label": label, "url": url, "pass": False}
    try:
        tid = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = cdp.call("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        cdp.call("Page.enable", session=s); cdp.call("Runtime.enable", session=s)
        cdp.call("Emulation.setFocusEmulationEnabled", {"enabled": True}, session=s)

        def ev(expr):
            r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, session=s)
            return r.get("result", {}).get("value")

        def shot(name):
            png = base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png"}, session=s)["data"])
            with open(os.path.join(out, f"{label}-{name}.png"), "wb") as f:
                f.write(png)

        t0 = time.time(); cdp.call("Page.navigate", {"url": url}, session=s)
        stats = None
        while time.time() - t0 < CONNECT_S:
            state = ev("window.__st && window.__st.state")
            stats = ev("window.__stats ? window.__stats() : null")
            if state == "connected" and stats and stats["w"] >= 640 and stats["h"] >= 480 and stats["nonblack"] >= MIN_NONBLACK:
                break
            time.sleep(1)
        res.update(connect_s=round(time.time() - t0, 1), state=ev("window.__st && window.__st.state"),
                   events=ev("window.__st && window.__st.events"), before=stats)
        shot("before")
        ok_connect = bool(stats) and res["state"] == "connected" and stats["w"] >= 640 and stats["h"] >= 480 \
            and stats["nonblack"] >= MIN_NONBLACK
        ev("window.__keep()")
        cdp.call("Page.bringToFront", session=s); ev("window.__rfb.focus()")
        keys = [(c, f"Key{c.upper()}", ord(c.upper()), c) for c in "root"] + [("Enter", "Enter", 13, "\r")]
        for key, code, vk, text in keys:
            cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code, "text": text,
                                                "windowsVirtualKeyCode": vk}, session=s)
            cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code,
                                                "windowsVirtualKeyCode": vk}, session=s)
            time.sleep(0.15)
        t1 = time.time(); changed = 0
        while time.time() - t1 < TYPE_S:
            changed = ev("window.__diff()")
            if changed >= MIN_CHANGED:
                break
            time.sleep(0.5)
        time.sleep(1); shot("after")
        res.update(changed_pixels=changed, change_s=round(time.time() - t1, 1),
                   after=ev("window.__stats()"), pass_connect=ok_connect, pass_input=changed >= MIN_CHANGED)
        res["pass"] = ok_connect and changed >= MIN_CHANGED
    except Exception as e:                                  # recorded, never hidden
        res["error"] = repr(e)
    finally:
        try:
            cdp.call("Browser.close")
        except Exception:
            proc.kill()
        proc.wait(timeout=30)
    with open(os.path.join(out, f"{label}-m2.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res.get(k) for k in ("label", "pass", "connect_s", "before", "changed_pixels", "error")}))

if __name__ == "__main__":
    main()
