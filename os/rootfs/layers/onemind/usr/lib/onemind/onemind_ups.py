# SPDX-License-Identifier: Apache-2.0
"""UPS support (IMG-06, #244): find a UPS on USB, set NUT up for it, and shut the box down in order on low battery.

`setup` (onemind-ups.service, ExecCondition, as root): when /data/onemind/ups holds no config yet, ask NUT's
nut-scanner for a UPS on USB (USB only, never a network scan). Found: write nut.conf, ups.conf, upsd.conf,
upsd.users and upsmon.conf there (0640 root:nut), with a random password that only upsd and upsmon share; it is
never printed. Exit 0 means "start the UPS service", exit 1 means "no UPS on this box": systemd then skips the
unit quietly instead of marking it failed. A UPS plugged in later is found at the next boot.

`shutdown` (onemind-ups-shutdown.service, started by upsmon's SHUTDOWNCMD when the UPS is on battery and low):
  1. apps: stop the k3s server, so nothing restarts an app (k3s.service has KillMode=process, so the containers
     keep running), then give every container SIGTERM and 30 seconds to save its work;
  2. k3s: stop the container runtime that is left in k3s's cgroup and unmount its mounts, deepest first;
  3. data: move the journal off /var/log (a bind from /data), sync, stop data.mount (systemd stops every unit and
     bind mount that needs /data first) and close the encrypted data disk;
  4. poweroff (and `systemctl poweroff --force` if that fails).
A command or step that fails is logged and the next one still runs: on a low battery the box must always reach
poweroff.
Every step has a deadline inside one overall budget (STEP_BUDGET), so a step that hangs runs out of time instead of
eating the battery: apps and k3s can never take the time reserved for the data volume, and step 4 always starts
within BUDGET seconds. BUDGET plus two poweroff attempts stays under the unit's TimeoutStartSec, and the unit has
FailureAction=poweroff-force as the last net if this program is killed or fails anyway.
`--dry-run` prints the plan and runs nothing (the tests and an owner who wants to see what it would do).
"""
import argparse, os, re, secrets, signal, subprocess, sys, time

CONF = "/data/onemind/ups"
UPS = "onemind"
MONITOR_USER = "upsmon-onemind"
PORT = 3493
SHUTDOWN_UNIT = "onemind-ups-shutdown.service"
FLAG = "/run/onemind-ups-monitor/killpower"
FILES = ("nut.conf", "ups.conf", "upsd.conf", "upsd.users", "upsmon.conf")
K3S = "/usr/local/bin/k3s"
K3S_CGROUP = "/sys/fs/cgroup/system.slice/k3s.service/cgroup.procs"
K3S_MOUNTS = ("/run/k3s/", "/var/lib/kubelet/pods/", "/var/lib/kubelet/plugins/", "/run/netns/cni-")
CRYPTSETUP = "/usr/lib/systemd/systemd-cryptsetup"
MAPPER = "onemind-data"
APP_GRACE = 30          # seconds each app gets after SIGTERM; a UPS on low battery has a few minutes at best
RUNTIME_GRACE = 10
# Seconds each step may use, in order. A step's deadline is the start plus its own slice and all slices before it,
# so time a fast step leaves over goes to the next one, and a hanging step never takes a later step's slice.
STEP_BUDGET = (("apps", 80), ("k3s", 30), ("data", 75))
BUDGET = sum(s for _, s in STEP_BUDGET)
POWEROFF_TIMEOUT = 20   # each of the two poweroff attempts; BUDGET + 2 * this < TimeoutStartSec=240 in the unit
KEYS = ("driver", "port", "vendorid", "productid", "serial")
SAFE = re.compile(r"^[A-Za-z0-9 ._:/+-]{1,128}$")


def parse_scanner(text):
    """The first UPS in nut-scanner's ups.conf-style output, with only the keys we use; None if none or odd."""
    for block in re.split(r"(?m)^\[[^\]]*\]\s*$", text)[1:]:
        dev = {}
        for m in re.finditer(r'(?m)^\s*(\w+)\s*=\s*"([^"]*)"\s*$', block):
            if m.group(1) in KEYS:
                dev[m.group(1)] = m.group(2)
        if "driver" not in dev or "port" not in dev or not all(SAFE.match(v) for v in dev.values()):
            return None
        return dev
    return None


def render(dev, password, port=PORT, shutdowncmd=None, run_as="nut", flag=FLAG, pollfreq=5):
    """The NUT config files for one UPS named `onemind`, as {file name: text}."""
    shutdowncmd = shutdowncmd or f"/usr/bin/systemctl start --no-block {SHUTDOWN_UNIT}"
    ups_conf = "maxretry = 3\n[%s]\n" % UPS + "".join(f'\t{k} = "{dev[k]}"\n' for k in KEYS if k in dev)
    mon = [f"MONITOR {UPS}@127.0.0.1:{port} 1 {MONITOR_USER} {password} primary", "MINSUPPLIES 1",
           f'SHUTDOWNCMD "{shutdowncmd}"', f"POLLFREQ {pollfreq}", f"POLLFREQALERT {pollfreq}", "HOSTSYNC 15",
           "DEADTIME 15", "FINALDELAY 0", f"POWERDOWNFLAG {flag}"]
    if run_as:
        mon.insert(0, f"RUN_AS_USER {run_as}")
    return {
        "nut.conf": "MODE=standalone\n",
        "ups.conf": ups_conf,
        "upsd.conf": f"LISTEN 127.0.0.1 {port}\nLISTEN ::1 {port}\n",
        "upsd.users": f"[{MONITOR_USER}]\n\tpassword = {password}\n\tupsmon primary\n",
        "upsmon.conf": "\n".join(mon) + "\n",
    }


def scan_usb():
    try:
        return subprocess.run(["/usr/bin/nut-scanner", "-U", "-q"], capture_output=True, text=True,
                              timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def nut_gid():
    try:
        import grp
        return grp.getgrnam("nut").gr_gid
    except (ImportError, KeyError):
        return None


def setup(conf=CONF, scan=scan_usb, gid="lookup"):
    """0 when the box has a UPS config (written now or earlier), 1 when there is no UPS."""
    if all(os.path.exists(os.path.join(conf, f)) for f in FILES):
        return 0
    dev = parse_scanner(scan())
    if dev is None:
        say("no UPS found on USB; the UPS service stays off until one is plugged in and the box restarts")
        return 1
    gid = nut_gid() if gid == "lookup" else gid
    os.makedirs(conf, mode=0o750, exist_ok=True)
    os.chmod(conf, 0o750)
    if gid is not None:
        os.chown(conf, 0, gid)
    for name, text in render(dev, secrets.token_urlsafe(32)).items():
        tmp = os.path.join(conf, f".{name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o640)
        if gid is not None:
            os.chown(tmp, 0, gid)
        os.replace(tmp, os.path.join(conf, name))
    say(f"UPS found on USB (driver {dev['driver']}); NUT is set up to watch it")
    return 0


class HostFs:
    def k3s_procs(self):
        try:
            with open(K3S_CGROUP) as f:
                return [p for p in f.read().split() if p.isdigit()]
        except OSError:
            return []

    def mounts_under(self, prefixes):
        try:
            with open("/proc/self/mounts") as f:
                points = [line.split()[1].replace("\\040", " ") for line in f if len(line.split()) > 1]
        except OSError:
            return []
        return [p for p in points if p.startswith(prefixes)]

    def has_mapper(self):
        return os.path.exists("/dev/mapper/" + MAPPER)


def run(cmd, timeout=None):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout or 60).stdout


def send(sig, pids):
    for p in pids:
        try:
            os.kill(int(p), getattr(signal, "SIG" + sig))
        except (ProcessLookupError, PermissionError, ValueError):
            pass


class OutOfTime(Exception):
    """The step used up its slice of the budget; the rest of it is skipped."""


def shutdown(runner=run, fs=None, kill=send, sleep=time.sleep, on_step=lambda name: None, clock=time.monotonic):
    fs = fs or HostFs()
    start, end = clock(), {}
    total = 0
    for name, slice_ in STEP_BUDGET:
        total += slice_
        end[name] = start + total
    current = ["apps"]

    def left():
        return end[current[0]] - clock()

    def within(want):
        """The timeout for one command: what it needs, cut to what is left of the step's slice."""
        room = left()
        if room < 1:
            raise OutOfTime
        return min(want, room)

    def attempt(cmd, want):
        """Run one command of a step; a failure or hang is logged and the step goes on with its next command."""
        try:
            return runner(cmd, timeout=within(want))
        except (subprocess.SubprocessError, OSError) as e:
            say(f"{current[0]}: {' '.join(cmd[:3])}: failed ({type(e).__name__}); going on")
            return None

    def apps():
        attempt(["systemctl", "stop", "k3s.service"], 60)
        ids = (attempt([K3S, "crictl", "ps", "-q"], 20) or "").split()
        if ids:
            t = within(APP_GRACE + 30)
            grace = max(1, min(APP_GRACE, int(t) - 30))
            runner([K3S, "crictl", "stop", "--timeout", str(grace), *ids], timeout=t)

    def k3s():
        pids = fs.k3s_procs()
        if pids:
            kill("TERM", pids)
            for _ in range(RUNTIME_GRACE):
                if not fs.k3s_procs() or left() < 2:
                    break
                sleep(1)
            rest = fs.k3s_procs()
            if rest:
                kill("KILL", rest)
        for point in sorted(fs.mounts_under(K3S_MOUNTS), key=len, reverse=True):
            attempt(["umount", point], 10)

    def data():
        attempt(["journalctl", "--relinquish-var"], 15)
        attempt(["sync"], 30)
        attempt(["systemctl", "stop", "data.mount"], 60)
        if fs.has_mapper():
            attempt([CRYPTSETUP, "detach", MAPPER], 30)

    for name, step in (("apps", apps), ("k3s", k3s), ("data", data)):
        say(f"low battery: step {name}")
        on_step(name)
        current[0] = name
        try:
            step()
        except OutOfTime:
            say(f"{name}: out of time; going on, the box must still power off")
        except (subprocess.SubprocessError, OSError) as e:
            say(f"{name}: failed ({type(e).__name__}); going on, the box must still power off")

    say("low battery: step poweroff")
    on_step("poweroff")
    try:
        runner(["systemctl", "poweroff"], timeout=POWEROFF_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as e:
        # --force skips stopping units but still kills every process and unmounts or remounts read-only.
        say(f"poweroff: failed ({type(e).__name__}); forcing it")
        try:
            runner(["systemctl", "poweroff", "--force"], timeout=POWEROFF_TIMEOUT)
        except (subprocess.SubprocessError, OSError) as e2:
            say(f"poweroff --force: failed ({type(e2).__name__}); the unit's FailureAction=poweroff-force is next")
            return 1
    return 0


def say(msg):
    print(f"onemind-ups: {msg}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="onemind-ups")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    sd = sub.add_parser("shutdown")
    sd.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    sd.add_argument("--log", help="with --dry-run: also append the plan to this file")
    a = ap.parse_args(argv)
    if a.cmd == "setup":
        return setup()
    if not a.dry_run:
        return shutdown()
    step = ["apps"]
    out = open(a.log, "a") if a.log else None

    def plan(cmd, timeout=None):
        line = f"{step[0]}: {' '.join(cmd)}"
        print(line, flush=True)
        if out:
            out.write(line + "\n")
            out.flush()
        return ""

    class DryFs(HostFs):
        def k3s_procs(self):
            plan(["kill", "-TERM", "<processes left in k3s.service>"])
            return []

        def has_mapper(self):
            return True

    def on_step(name):
        step[0] = name

    try:
        return shutdown(runner=plan, fs=DryFs(), kill=lambda s, p: None, sleep=lambda s: None, on_step=on_step)
    finally:
        if out:
            out.close()


if __name__ == "__main__":
    sys.exit(main())
