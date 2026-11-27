# SPDX-License-Identifier: Apache-2.0
"""Kiosk mode of the box's own screen (UX-07, #242 part 2): the dashboard full screen on the box's monitor.

Owner-enabled: nothing happens until the owner runs `onemind kiosk enable` on the box, which creates the
flag file below. Read-only by design: the kiosk browser opens only the local gateway address, in a private
profile on tmpfs that is gone at stop, and never holds the owner token (nobody types one in on the box, and
the setup page's one-time token is never drawn here). Whoever wants to use the dashboard signs in from a
phone or computer as before. If the compositor (cage) or a browser is not in the image, the launcher
falls back to the text screen (onemind_screen.py), so enabling kiosk never leaves a blank monitor.
Run by onemind-kiosk.service.
"""
import os, re, shutil, sys, time, urllib.request

PORT = 8080
FLAG = "/data/onemind/kiosk/enabled"
URL = f"http://127.0.0.1:{PORT}/"
PROFILE = "/run/onemind-kiosk/profile"
# The owner's keyboard layout (P-11), the file onemind-console-keyboard also reads: /etc/default/keyboard format.
KEYBOARD = "/data/onemind/console/keyboard"
XKB = {"XKBMODEL": "XKB_DEFAULT_MODEL", "XKBLAYOUT": "XKB_DEFAULT_LAYOUT", "XKBVARIANT": "XKB_DEFAULT_VARIANT",
       "XKBOPTIONS": "XKB_DEFAULT_OPTIONS"}
# (executable, flags that put it full screen with no chrome and no saved state), first one found wins.
BROWSERS = [
    ("chromium", ["--kiosk", "--incognito", "--no-first-run", "--disable-infobars", "--noerrdialogs",
                  "--user-data-dir=" + PROFILE]),
    ("firefox-esr", ["--kiosk", "--private-window", "--profile", PROFILE]),
    ("firefox", ["--kiosk", "--private-window", "--profile", PROFILE]),
]


def enabled(root="/"):
    return os.path.exists(os.path.join(root, FLAG.lstrip("/")))


def keyboard_env(path=KEYBOARD):
    """The XKB_DEFAULT_* variables for the compositor (cage, through libxkbcommon), from the owner's keyboard file.
    The file is read as data, never sourced; one value outside [A-Za-z0-9_,:+-] refuses the whole file, as the console
    script does, and the compositor then keeps its own default (US). Empty values are left out."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(65536).splitlines()
    except OSError:
        return {}
    vals = {}
    for line in lines:
        m = re.match(r'^\s*(XKB[A-Z]+)="?([^"]*)"?\s*$', line)
        if m and m.group(1) in XKB:
            vals[m.group(1)] = m.group(2)
    if any(re.search(r"[^A-Za-z0-9_,:+-]", v) for v in vals.values()):
        print("kiosk: refusing the keyboard file (a value has odd characters); using the default layout", file=sys.stderr)
        return {}
    return {XKB[k]: v for k, v in vals.items() if v}


def plan(which=shutil.which):
    """The command to run: cage around a browser, or None when either is missing (then the text screen runs)."""
    cage = which("cage")
    if not cage:
        return None
    for name, flags in BROWSERS:
        path = which(name)
        if path:
            return [cage, "--", path, *flags, URL]
    return None


def wait_for_gateway(url=URL + "healthz", tries=60, pause=1.0, fetch=None, sleep=time.sleep):
    """The gateway unit is Type=simple, so it can still be starting when this unit runs, and Firefox does not
    reload an error page. Wait (up to tries x pause seconds) until /healthz answers; True when it did."""
    fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=2).status)
    for _ in range(tries):
        try:
            if fetch(url) == 200:
                return True
        except Exception:
            pass
        sleep(pause)
    return False


def main():
    if not enabled():
        print("kiosk is not enabled (onemind kiosk enable)", file=sys.stderr)
        return 0
    argv = plan()
    if argv is None:
        print("kiosk: cage or a browser is not installed; showing the text screen instead", file=sys.stderr)
        screen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "onemind_screen.py")
        os.execv(sys.executable, [sys.executable, "-I", screen])
    wait_for_gateway()
    os.makedirs(PROFILE, exist_ok=True)
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run/onemind-kiosk")
    os.environ.update(keyboard_env())
    os.execv(argv[0], argv)


if __name__ == "__main__":
    sys.exit(main())
