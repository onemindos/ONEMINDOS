# SPDX-License-Identifier: Apache-2.0
"""Kiosk mode of the box's own screen (UX-07, #242 part 2): the OneMind desktop full screen on the box's monitor.

On by default on the boards that ship a compositor and a browser (founder decision 2026-11-28): first boot
creates the flag file below once (onemind_firstboot.kiosk_default), so a monitor on a fresh box shows the setup
page and then the desktop, not the text screen. The owner can turn it off in setup, with `onemind kiosk
disable` or over the API; first boot never turns it back on. The kiosk browser opens only the local gateway
address (Chromium's managed policy /etc/chromium/policies/managed/onemind-kiosk.json blocks every other URL,
developer tools, downloads, file dialogs, printing and saved passwords), in a private profile on tmpfs that is
gone at stop. The launcher holds no token; a person who signs in at the box holds that session's token in the
browser until it ends, and the dashboard locks it after an idle time it will not let anyone switch off here
(the URL's kiosk=1 marker). With no monitor connected, or if the compositor (cage) or a
browser is not in the image, the launcher shows the text screen (onemind_screen.py) instead, so the kiosk never
leaves a blank monitor; a monitor plugged in later is picked up within a few seconds.
Run by onemind-kiosk.service.
"""
import glob, os, re, shutil, subprocess, sys, time, urllib.request

PORT = 8080
FLAG = "/data/onemind/kiosk/enabled"
URL = f"http://127.0.0.1:{PORT}/"
# What the browser opens: kiosk=1 tells the dashboard it runs on the box's own screen (forced idle lock).
KIOSK_URL = URL + "?kiosk=1"
RUNTIME = "/run/onemind-kiosk"
PROFILE = RUNTIME + "/profile"
# The owner's keyboard layout (P-11), the file onemind-console-keyboard also reads: /etc/default/keyboard format.
KEYBOARD = "/data/onemind/console/keyboard"
XKB = {"XKBMODEL": "XKB_DEFAULT_MODEL", "XKBLAYOUT": "XKB_DEFAULT_LAYOUT", "XKBVARIANT": "XKB_DEFAULT_VARIANT",
       "XKBOPTIONS": "XKB_DEFAULT_OPTIONS"}
# (executable, flags that put it full screen with no chrome and no saved state), first one found wins.
BROWSERS = [
    ("chromium", ["--ozone-platform=wayland", "--kiosk", "--incognito", "--no-first-run",
                  "--no-default-browser-check", "--disable-infobars", "--noerrdialogs", "--password-store=basic",
                  "--disable-features=Translate", "--overscroll-history-navigation=0",
                  "--user-data-dir=" + PROFILE]),
    ("firefox-esr", ["--kiosk", "--private-window", "--profile", PROFILE]),
    ("firefox", ["--kiosk", "--private-window", "--profile", PROFILE]),
]
NO_MONITOR = "kiosk: no monitor is connected; showing the text screen until one is"
NO_BROWSER = "kiosk: cage or a browser is not installed; showing the text screen instead"


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


def monitor_connected(root="/"):
    """True when a display connector reports a monitor (/sys/class/drm/card*-*/status). A box with no GPU
    output at all (a server, the battery's VM with -vga none) has none, and then the text screen runs."""
    for status in glob.glob(os.path.join(root, "sys", "class", "drm", "card*-*", "status")):
        try:
            with open(status) as f:
                if f.read().strip() == "connected":
                    return True
        except OSError:
            pass
    return False


def plan(which=shutil.which):
    """The command to run: cage around a browser, or None when either is missing (then the text screen runs)."""
    cage = which("cage")
    if not cage:
        return None
    for name, flags in BROWSERS:
        path = which(name)
        if path:
            return [cage, "--", path, *flags, KIOSK_URL]
    return None


def environment(base):
    """The browser's environment: everything it writes stays in the unit's runtime directory (tmpfs, 0700,
    removed at stop), because the kiosk user has no home and the root filesystem is read-only."""
    env = dict(base)
    env.update({"HOME": RUNTIME, "XDG_RUNTIME_DIR": RUNTIME, "XDG_CONFIG_HOME": RUNTIME + "/config",
                "XDG_CACHE_HOME": RUNTIME + "/cache", "XDG_DATA_HOME": RUNTIME + "/data"})
    return env


def wait_for_gateway(url=URL + "healthz", tries=60, pause=1.0, fetch=None, sleep=time.sleep):
    """The gateway unit is Type=simple, so it can still be starting when this unit runs, and Firefox does not
    reload an error page. Wait (up to tries x pause seconds) until /healthz answers; True when it did.
    Before setup the wizard answers it on loopback, so first boot opens the setup page."""
    fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=2).status)
    for _ in range(tries):
        try:
            if fetch(url) == 200:
                return True
        except Exception:
            pass
        sleep(pause)
    return False


def text_screen_until_monitor(screen, connected=monitor_connected, spawn=subprocess.Popen, sleep=time.sleep,
                              pause=5.0, rounds=None):
    """Run the text screen while no monitor is connected. When one shows up, stop it and return 1, so
    systemd restarts this unit (Restart=always) and the next start opens the browser. `rounds` bounds the
    loop for the tests; the service passes None and waits for as long as it takes."""
    child = spawn([sys.executable, "-I", screen])
    n = 0
    try:
        while rounds is None or n < rounds:
            n += 1
            if connected():
                return 1
            if child.poll() is not None:            # the text screen died: let systemd start everything again
                return 1
            sleep(pause)
        return 0
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


def main():
    if not enabled():
        print("kiosk is not enabled (onemind kiosk enable)", file=sys.stderr)
        return 0
    screen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "onemind_screen.py")
    argv = plan()
    if argv is None:
        print(NO_BROWSER, file=sys.stderr, flush=True)
        os.execv(sys.executable, [sys.executable, "-I", screen])
    if not monitor_connected():
        print(NO_MONITOR, file=sys.stderr, flush=True)
        return text_screen_until_monitor(screen)
    wait_for_gateway()
    os.environ.update(keyboard_env())
    env = environment(os.environ)
    for d in (PROFILE, env["XDG_CONFIG_HOME"], env["XDG_CACHE_HOME"], env["XDG_DATA_HOME"]):
        os.makedirs(d, exist_ok=True)
    os.execve(argv[0], argv, env)


if __name__ == "__main__":
    sys.exit(main())
