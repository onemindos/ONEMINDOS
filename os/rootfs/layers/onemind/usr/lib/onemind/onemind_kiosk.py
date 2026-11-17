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
import os, shutil, sys

PORT = 8080
FLAG = "/data/onemind/kiosk/enabled"
URL = f"http://127.0.0.1:{PORT}/"
PROFILE = "/run/onemind-kiosk/profile"
# (executable, flags that put it full screen with no chrome and no saved state), first one found wins.
BROWSERS = [
    ("chromium", ["--kiosk", "--incognito", "--no-first-run", "--disable-infobars", "--noerrdialogs",
                  "--user-data-dir=" + PROFILE]),
    ("firefox-esr", ["--kiosk", "--private-window", "--profile", PROFILE]),
    ("firefox", ["--kiosk", "--private-window", "--profile", PROFILE]),
]


def enabled(root="/"):
    return os.path.exists(os.path.join(root, FLAG.lstrip("/")))


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


def main():
    if not enabled():
        print("kiosk is not enabled (onemind kiosk enable)", file=sys.stderr)
        return 0
    argv = plan()
    if argv is None:
        print("kiosk: cage or a browser is not installed; showing the text screen instead", file=sys.stderr)
        screen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "onemind_screen.py")
        os.execv(sys.executable, [sys.executable, "-I", screen])
    os.makedirs(PROFILE, exist_ok=True)
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run/onemind-kiosk")
    os.execv(argv[0], argv)


if __name__ == "__main__":
    sys.exit(main())
