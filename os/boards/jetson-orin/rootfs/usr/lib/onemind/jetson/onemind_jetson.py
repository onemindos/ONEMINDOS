# SPDX-License-Identifier: Apache-2.0
"""OneMind on NVIDIA Jetson (L4T): the health gate inside NVIDIA's rootfs validation hook,
and the OneMind release contract around NVIDIA's image-based OTA (brief 30 B4.7, 01 §4.2 item 1).

NVIDIA owns A/B on Jetson: rootfs slots APP / APP_b, a retry counter that the cpu-bootloader
lowers on every *warm* boot that does not reach `nvbootctrl verify`, and a switch to the other
slot when it runs out. OneMind plugs in at two points and never patches NVIDIA's binaries:

  gate        Called by /usr/sbin/user_rootfs_validation.sh, the customer hook that NVIDIA's
              rootfs-validation service runs (nvidia-l4t-bootloader-utils 39.2.1 and
              nvidia-l4t-init 36.5.2 both read that path). Exit 0 = this rootfs is good;
              exit 1 = NVIDIA's script runs `reboot` (a warm reset, so the retry counter
              advances [C-REF3-DC-technical-001]). Same checks as the RAUC gate
              (/usr/lib/onemind/onemind-k3s-check, G1-G6) plus G7 (booted version = bundle).
  wait-pass   ExecStartPre of nv-l4t-bootloader-config.service: blocks `nvbootctrl verify`
              until the gate passed on *this* boot. NVIDIA orders that service only After= a
              Type=simple validation service, which does not wait for the hook to finish.
  ota-verify  OneMind's own payload verifier: NVIDIA's payload is unsigned and leaves
  ota-apply   authenticity to the integrator [C-REF3-DC-security-001]. A CMS signature by the
              OneMind release CA (the RAUC trust root) over manifest.json, then layout flags,
              L4T base, QSPI version, bad-release list and file hashes; only then the trial
              marker and NVIDIA's nv_ota_start.sh.
  ota-sign    Host side: refuses a manifest whose layout flags differ from the device's
              recorded layout (a mismatched payload has needed a USB reflash [C-REF-DC-cost-004]).

Python 3 standard library only; signatures use the openssl CLI (Ubuntu ships it on L4T).
"""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, tarfile, time

SCHEMA = "onemind.io/jetson-ota/v1"
LAYOUT_FLAGS = ("target_board", "rootfs_ab", "external_device", "rootfs_size", "rootfs_enc", "uefi_secure_boot")


class Paths:
    """Every path the tool touches; tests point `root` at a temp dir."""

    def __init__(self, root="/"):
        j = lambda p: os.path.join(root, p.lstrip("/"))
        self.state = j("/data/onemind")
        self.pending = j("/data/onemind/pending")
        self.bad = j("/data/onemind/bad-releases")
        self.log = j("/data/onemind/gate.log")
        self.device_layout = j("/data/onemind/jetson/device-layout.json")
        self.ota_work = j("/data/onemind/jetson/ota-work")
        self.ota_dir = j("/ota")
        self.run = j("/run/onemind")
        self.passfile = j("/run/onemind/jetson-gate.pass")
        self.image_layout = j("/etc/onemind/jetson-layout.json")
        self.release = j("/etc/onemind/release")
        self.keyring = j("/etc/onemind/keyring.pem")
        self.gate_defaults = j("/etc/default/onemind-health-gate")
        self.nv_release = j("/etc/nv_tegra_release")
        self.boot_id = j("/proc/sys/kernel/random/boot_id")
        self.console = j("/dev/console")
        self.check = "/usr/lib/onemind/onemind-k3s-check"
        self.nvbootctrl = "/usr/sbin/nvbootctrl"


# ---------------------------------------------------------------- small helpers
def read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".new"
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def kv(text):
    """KEY=value lines (shell-style, optional quotes) -> dict."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def slot_letter(n):
    return {"0": "A", "1": "B"}.get(str(n).strip())


def parse_nv_release(text):
    """'# R39 (release), REVISION: 2.1, ...' -> '39.2.1'."""
    m = re.search(r"#\s*R(\d+)\s*\(release\),\s*REVISION:\s*([0-9.]+)", text)
    return f"{m.group(1)}.{m.group(2)}" if m else None


def parse_slots(text):
    """nvbootctrl [-t rootfs] dump-slots-info -> {'version': '39.2.0', 'A': 'normal', 'B': 'unbootable'}."""
    out = {}
    m = re.search(r"Current version:\s*(\S+)", text)
    if m:
        out["version"] = m.group(1)
    for n, status in re.findall(r"slot:\s*(\d)\s*,.*?status:\s*(\w+)", text):
        out[slot_letter(n)] = status
    return out


def layout_flags(d):
    return {k: d.get(k) for k in LAYOUT_FLAGS}


def layout_mismatch(a, b):
    """Names of layout flags that differ (empty list = same layout)."""
    fa, fb = layout_flags(a), layout_flags(b)
    return [k for k in LAYOUT_FLAGS if fa[k] != fb[k]]


# ---------------------------------------------------------------- device facts (overridable in tests)
class Device:
    def __init__(self, paths):
        self.p = paths

    def _nv(self, *args):
        r = subprocess.run([self.p.nvbootctrl, *args], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"nvbootctrl {' '.join(args)}: rc={r.returncode} {r.stderr.strip()}")
        return r.stdout

    def current_slot(self):
        return slot_letter(self._nv("-t", "rootfs", "get-current-slot").strip())

    def rootfs_slots(self):
        return parse_slots(self._nv("-t", "rootfs", "dump-slots-info"))

    def qspi_version(self):
        return parse_slots(self._nv("dump-slots-info")).get("version")

    def l4t_version(self):
        return parse_nv_release(read(self.p.nv_release))

    def boot_id(self):
        return read(self.p.boot_id).strip()

    def check(self):
        r = subprocess.run([self.p.check], capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout.strip().splitlines() or ["(no output)"])[-1]


# ---------------------------------------------------------------- the gate
class Gate:
    def __init__(self, paths, device, sleep=time.sleep, clock=time.monotonic):
        self.p, self.d, self.sleep, self.clock = paths, device, sleep, clock
        cfg = kv(read(paths.gate_defaults))
        cfg.update({k: v for k, v in os.environ.items() if k.startswith("ONEMIND_GATE_")})
        self.timeout = int(cfg.get("ONEMIND_GATE_TIMEOUT", 300))
        self.stable = int(cfg.get("ONEMIND_GATE_STABLE", 3))
        self.interval = int(cfg.get("ONEMIND_GATE_INTERVAL", 10))

    def log(self, msg):
        line = f"HEALTH-GATE: {datetime.datetime.now(datetime.timezone.utc):%H:%M:%S} jetson {msg}"
        os.makedirs(self.p.state, exist_ok=True)
        with open(self.p.log, "a") as f:
            f.write(line + "\n")
        try:
            with open(self.p.console, "w") as c:
                c.write(line + "\n")
        except OSError:
            pass
        print(line, flush=True)

    def version(self):
        return kv(read(self.p.release)).get("ONEMIND_VERSION", "unknown")

    def bad_versions(self):
        return {m.group(1) for m in re.finditer(r"version=(\S+)", read(self.p.bad))}

    def remember_bad(self, version, verdict):
        os.makedirs(self.p.state, exist_ok=True)
        with open(self.p.bad, "a") as f:
            f.write(f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ} version={version} verdict={verdict}\n")
            f.flush()
            os.fsync(f.fileno())

    def record_layout(self):
        """The first boot after the factory flash records the layout this device was flashed with."""
        if not os.path.exists(self.p.device_layout) and os.path.exists(self.p.image_layout):
            write_atomic(self.p.device_layout, read(self.p.image_layout))
            self.log("recorded device layout from the factory flash")

    def passed(self, why):
        write_atomic(self.p.passfile, f"{self.d.boot_id()} {why}\n")
        return 0

    def run(self):
        self.record_layout()
        ver = self.version()
        marker = read(self.p.pending).split()
        pslot, pver = (marker + ["", ""])[:2]
        try:
            slot = self.d.current_slot()
        except Exception as e:  # noqa: BLE001 - any failure to read the slot is reported the same way
            slot = None
            self.log(f"cannot read the rootfs slot: {e}")
        # An unreadable slot with a marker pending is judged as a trial, never waved through.
        mode = "committed" if not pslot else ("trial" if slot is None or pslot == slot else "fell-back")
        self.log(f"start slot={slot} version={ver} mode={mode}")

        if mode == "committed":
            self.log(f"RESULT committed-boot slot={slot} version={ver}")
            return self.passed("committed")

        if mode == "fell-back":
            if pver not in self.bad_versions():
                self.remember_bad(pver, "image-bad")
            os.remove(self.p.pending)
            self.log(f"RESULT fell-back slot={slot} version={ver}; slot {pslot} (v{pver}) marked bad, never retried")
            return self.passed("fell-back")

        # trial: this boot runs the slot the update wrote
        if slot is None:
            return self.fail(ver, "image-bad", "rootfs slot unknown during a trial")
        if ver in self.bad_versions():
            return self.fail(ver, None, f"version {ver} already judged bad on this device (retry boot)")
        if pver != ver:
            return self.fail(ver, "image-bad", f"fail G7: booted version {ver} != bundle version {pver}")
        t0, ok, worst, last = self.clock(), 0, 0, "n/a"
        while self.clock() - t0 < self.timeout:
            good, last = self.d.check()
            if good:
                ok += 1
                self.log(f"CHECK pass {ok}/{self.stable} at {int(self.clock() - t0)}s: {last}")
                if ok >= self.stable:
                    os.remove(self.p.pending)
                    self.log(f"RESULT mark-good slot={slot} version={ver} after {int(self.clock() - t0)}s "
                             "(nvbootctrl verify follows in nv-l4t-bootloader-config)")
                    return self.passed("trial-good")
            else:
                ok = 0
                self.log(f"CHECK fail at {int(self.clock() - t0)}s: {last}")
                m = re.match(r"fail G(\d)", last)
                worst = max(worst, int(m.group(1)) if m else 0)
            self.sleep(self.interval)
        verdict = "environment-bad" if worst == 4 else "image-bad"
        return self.fail(ver, verdict, f"deadline {self.timeout}s (last: {last})")

    def fail(self, ver, verdict, why):
        other = None
        try:
            slots = self.d.rootfs_slots()
            cur = self.d.current_slot()
            other = slots.get({"A": "B", "B": "A"}.get(cur))
        except Exception:  # noqa: BLE001
            pass
        if other is not None and other != "normal":
            # Rejecting would only walk into the recovery kernel: keep this slot and alert.
            self.log(f"RESULT unhealthy version={ver} ({why}) but the other slot is '{other}': staying (alert)")
            return self.passed("unhealthy-no-fallback")
        if verdict:
            self.remember_bad(ver, verdict)
        self.log(f"RESULT reject version={ver} verdict={verdict or 'known-bad'} ({why}) -> warm reboot "
                 "(NVIDIA's retry counter falls back to the other slot)")
        return 1


def wait_pass(paths, device, limit, sleep=time.sleep, clock=time.monotonic):
    """Block nvbootctrl verify until the gate passed on this boot."""
    t0, bid = clock(), device.boot_id()
    while clock() - t0 < limit:
        if read(paths.passfile).split()[:1] == [bid]:
            return 0
        sleep(2)
    print(f"onemind-jetson: gate did not pass within {limit}s on this boot; not running nvbootctrl verify", file=sys.stderr)
    return 1


# ---------------------------------------------------------------- OTA: sign, verify, apply
def cms_verify(manifest, sig, keyring):
    r = subprocess.run(["openssl", "cms", "-verify", "-binary", "-inform", "DER", "-in", sig, "-content", manifest,
                        "-CAfile", keyring, "-purpose", "any", "-out", os.devnull],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]


def cms_sign(manifest, sig, cert, key):
    subprocess.run(["openssl", "cms", "-sign", "-binary", "-in", manifest, "-signer", cert, "-inkey", key,
                    "-outform", "DER", "-out", sig, "-nosmimecap"], check=True)


def check_manifest(m, *, device_layout, image_layout, l4t, qspi, bad, running_version, now=None):
    """All content checks after the signature. Returns a list of reasons to refuse (empty = OK)."""
    why = []
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if m.get("schema") != SCHEMA:
        why.append(f"schema {m.get('schema')!r} is not {SCHEMA}")
    if m.get("compatible") != image_layout.get("compatible"):
        why.append(f"compatible {m.get('compatible')!r} != device {image_layout.get('compatible')!r}")
    exp = m.get("expires")
    try:
        if not exp or datetime.datetime.fromisoformat(exp.replace("Z", "+00:00")) <= now:
            why.append(f"manifest expired or has no expiry ({exp})")
    except ValueError:
        why.append(f"unreadable expiry {exp!r}")
    diff = layout_mismatch(m.get("layout", {}), device_layout)
    if diff:
        why.append("layout flags differ from the device's recorded layout: " + ", ".join(diff))
    if (m.get("l4t") or {}).get("from") != l4t:
        why.append(f"payload is built from L4T {(m.get('l4t') or {}).get('from')} but the device runs {l4t}")
    if (m.get("bootloader") or {}).get("requires_qspi") != qspi:
        why.append(f"payload requires QSPI {(m.get('bootloader') or {}).get('requires_qspi')} but the device has {qspi}")
    if m.get("version") in bad:
        why.append(f"version {m.get('version')} was rolled back on this device before (no auto-retry)")
    if m.get("version") == running_version:
        why.append(f"version {running_version} is already running")
    files = m.get("files") or {}
    if "ota_payload_package.tar.gz" not in files or not any(n.startswith("ota_tools_") for n in files):
        why.append("manifest must list ota_payload_package.tar.gz and an ota_tools_*.tbz2")
    for name in files:
        if os.path.basename(name) != name or name.startswith("."):
            why.append(f"file name {name!r} is not a plain file name")
    return why


def verify_bundle(bundle, paths, device, gate):
    """Signature, then content, then hashes. Returns (manifest, reasons)."""
    man, sig = os.path.join(bundle, "manifest.json"), os.path.join(bundle, "manifest.json.p7s")
    if not (os.path.isfile(man) and os.path.isfile(sig)):
        return None, ["bundle needs manifest.json and manifest.json.p7s"]
    good, err = cms_verify(man, sig, paths.keyring)
    if not good:
        return None, [f"signature does not verify against {paths.keyring}: {err}"]
    m = json.loads(read(man))
    why = check_manifest(m, device_layout=json.loads(read(paths.device_layout) or "{}"),
                         image_layout=json.loads(read(paths.image_layout) or "{}"),
                         l4t=device.l4t_version(), qspi=device.qspi_version(), bad=gate.bad_versions(),
                         running_version=gate.version())
    for name, meta in (m.get("files") or {}).items():
        f = os.path.join(bundle, os.path.basename(name))
        if not os.path.isfile(f):
            why.append(f"missing {name}")
        elif sha256_file(f) != meta.get("sha256"):
            why.append(f"sha256 mismatch for {name}")
    return m, why


def safe_extract(tbz2, dest):
    with tarfile.open(tbz2, "r:bz2") as t:
        t.extractall(dest, filter="data")


def stage_bundle(bundle, paths):
    """Copy the bundle into a root-only directory first, so the files that are verified are the
    files that are used (the source directory may belong to the user who copied it in)."""
    shutil.rmtree(paths.ota_work, ignore_errors=True)
    dest = os.path.join(paths.ota_work, "bundle")
    os.makedirs(dest, mode=0o700)
    for name in os.listdir(bundle):
        src = os.path.join(bundle, name)
        wanted = name in ("manifest.json", "manifest.json.p7s", "ota_payload_package.tar.gz") or \
            (name.startswith("ota_tools_") and name.endswith(".tbz2"))
        if wanted and os.path.isfile(src) and not os.path.islink(src):
            shutil.copyfile(src, os.path.join(dest, name))
    return dest


def apply_bundle(bundle, paths, device, gate, reboot=False):
    if os.path.exists(paths.pending):
        print("REFUSED: a trial is already pending (/data/onemind/pending); let the gate judge it first", file=sys.stderr)
        return 2
    bundle = stage_bundle(bundle, paths)
    m, why = verify_bundle(bundle, paths, device, gate)
    if why:
        for w in why:
            print(f"REFUSED: {w}", file=sys.stderr)
        return 2
    cur = device.current_slot()
    if cur not in ("A", "B"):
        print(f"REFUSED: cannot read the current rootfs slot ({cur}); is the device flashed with ROOTFS_AB=1?", file=sys.stderr)
        return 2
    target = {"A": "B", "B": "A"}[cur]
    tools = next(n for n in m["files"] if n.startswith("ota_tools_"))
    safe_extract(os.path.join(bundle, tools), paths.ota_work)
    os.makedirs(paths.ota_dir, exist_ok=True)
    shutil.copyfile(os.path.join(bundle, "ota_payload_package.tar.gz"), os.path.join(paths.ota_dir, "ota_payload_package.tar.gz"))
    # The trial marker is written before anything touches the other slot (the RAUC pre-install rule).
    write_atomic(paths.pending, f"{target} {m['version']}\n")
    gate.log(f"ota: trial marker slot={target} version={m['version']} (L4T {m['l4t']['from']} -> {m['l4t']['to']})")
    start = os.path.join(paths.ota_work, "Linux_for_Tegra/tools/ota_tools/version_upgrade")
    r = subprocess.run(["./nv_ota_start.sh", os.path.join(paths.ota_dir, "ota_payload_package.tar.gz")], cwd=start)
    if r.returncode != 0:
        os.remove(paths.pending)
        gate.log(f"ota: nv_ota_start.sh failed rc={r.returncode}; trial marker removed")
        return r.returncode
    gate.log("ota: NVIDIA OTA staged; the next boot runs the update, then the gate judges the new slot")
    if reboot:
        subprocess.run(["systemctl", "reboot"])
    return 0


def sign_manifest(manifest, out, cert, key, device_layouts):
    m = json.loads(read(manifest))
    if not device_layouts:
        print("REFUSED: give at least one --device-layout (the layout recorded when the devices were flashed)", file=sys.stderr)
        return 2
    for dl in device_layouts:
        diff = layout_mismatch(m.get("layout", {}), json.loads(read(dl)))
        if diff:
            print(f"REFUSED: layout flags differ from {dl}: {', '.join(diff)}", file=sys.stderr)
            return 2
    cms_sign(manifest, out, cert, key)
    return 0


def make_manifest(bundle, *, version, compatible, layout, l4t_from, l4t_to, requires_qspi, days):
    files = {n: {"sha256": sha256_file(os.path.join(bundle, n)), "size": os.path.getsize(os.path.join(bundle, n))}
             for n in sorted(os.listdir(bundle)) if n == "ota_payload_package.tar.gz" or n.startswith("ota_tools_")}
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    return {"schema": SCHEMA, "version": version, "compatible": compatible, "layout": layout_flags(layout),
            "l4t": {"from": l4t_from, "to": l4t_to}, "bootloader": {"requires_qspi": requires_qspi, "installs": l4t_to},
            "files": files, "expires": exp.strftime("%Y-%m-%dT%H:%M:%SZ")}


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog="onemind-jetson")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gate")
    w = sub.add_parser("wait-pass"); w.add_argument("--limit", type=int, default=0)
    for c in ("ota-verify", "ota-apply"):
        s = sub.add_parser(c); s.add_argument("bundle")
        if c == "ota-apply":
            s.add_argument("--reboot", action="store_true")
    mm = sub.add_parser("ota-manifest")
    mm.add_argument("bundle"); mm.add_argument("--version", required=True); mm.add_argument("--layout", required=True)
    mm.add_argument("--l4t-from", required=True); mm.add_argument("--l4t-to", required=True)
    mm.add_argument("--requires-qspi", required=True); mm.add_argument("--days", type=int, default=90)
    sg = sub.add_parser("ota-sign")
    sg.add_argument("manifest"); sg.add_argument("--out", required=True); sg.add_argument("--cert", required=True)
    sg.add_argument("--key", required=True); sg.add_argument("--device-layout", action="append", default=[])
    a = ap.parse_args(argv)

    paths = Paths(os.environ.get("ONEMIND_JETSON_ROOT", "/"))
    dev = Device(paths)
    if a.cmd == "gate":
        return Gate(paths, dev).run()
    if a.cmd == "wait-pass":
        g = Gate(paths, dev)
        return wait_pass(paths, dev, a.limit or g.timeout + 300)
    if a.cmd == "ota-verify":
        _, why = verify_bundle(a.bundle, paths, dev, Gate(paths, dev))
        for x in why:
            print(f"REFUSED: {x}", file=sys.stderr)
        print("bundle OK" if not why else "bundle REFUSED")
        return 0 if not why else 2
    if a.cmd == "ota-apply":
        return apply_bundle(a.bundle, paths, dev, Gate(paths, dev), reboot=a.reboot)
    if a.cmd == "ota-manifest":
        lay = json.loads(read(a.layout))
        m = make_manifest(a.bundle, version=a.version, compatible=lay.get("compatible"), layout=lay,
                          l4t_from=a.l4t_from, l4t_to=a.l4t_to, requires_qspi=a.requires_qspi, days=a.days)
        write_atomic(os.path.join(a.bundle, "manifest.json"), json.dumps(m, indent=2, sort_keys=True) + "\n")
        print(os.path.join(a.bundle, "manifest.json"))
        return 0
    if a.cmd == "ota-sign":
        return sign_manifest(a.manifest, a.out, a.cert, a.key, a.device_layout)
    return 2


if __name__ == "__main__":
    sys.exit(main())
