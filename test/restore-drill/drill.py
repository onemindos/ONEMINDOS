#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""BAK-02 (#163): whole-box restore drill. Back a box up, restore onto a clean VM, verify, and time it.

Boots a Debian 13 VM (QEMU/KVM, same pinned image as the 2-VM proof), installs OneMind, writes real data
(a file, a large payload, a database), backs the whole box up to a virtual USB disk and writes the
emergency kit. That VM is then thrown away. A second, clean Debian 13 VM gets only the USB disk and the
owner key (what a person has after a fire), installs OneMind, restores, and the data is checked byte for
byte. The clock is install + restore + verify on the clean VM; over 3600 s fails the run.

  python3 -I test/restore-drill/drill.py --results test/restore-drill/results/run.json

Environment: ONEMIND_DRILL_SRC_REF (commit-ish to test instead of the checkout), ONEMIND_DRILL_CACHE
(image cache dir), ONEMIND_DRILL_KEEP=1 (leave the work dir and logs). Exit 0 only for PASS.
The pure judging logic is drillcore.py (unit-tested in test/unit/test_restore_drill.py).
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load("drillcore", os.path.join(HERE, "drillcore.py"))
net = _load("two_vm", os.path.join(ROOT, "test", "net", "two_vm.py"))   # image pin, source tree build, console guard


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class VM:
    """One Debian 13 VM on QEMU user networking (SSH forwarded to loopback) with an optional USB-style disk."""

    def __init__(self, name, work, key, mem, cpus, accel, usb=None):
        self.name, self.work, self.key, self.mem, self.cpus, self.accel, self.usb = name, work, key, mem, cpus, accel, usb
        self.ssh_port, self.proc, self.scanned = net.free_port(), None, 0
        self.console = os.path.join(work, f"{name}-console.log")

    def prepare(self, base):
        d = os.path.join(self.work, self.name)
        os.makedirs(d, exist_ok=True)
        self.disk = os.path.join(d, "disk.qcow2")
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", base, self.disk, "30G"], check=True)
        pub = open(self.key + ".pub").read().strip()
        open(os.path.join(d, "user-data"), "w").write(
            "#cloud-config\nhostname: %s\nmanage_etc_hosts: true\nssh_pwauth: false\nusers:\n  - name: debian\n"
            "    sudo: ALL=(ALL) NOPASSWD:ALL\n    shell: /bin/bash\n    lock_passwd: true\n    ssh_authorized_keys:\n      - %s\n" % (self.name, pub))
        open(os.path.join(d, "meta-data"), "w").write(f"instance-id: drill-{self.name}\nlocal-hostname: {self.name}\n")
        self.seed = os.path.join(d, "seed.iso")
        subprocess.run(["cloud-localds", self.seed, os.path.join(d, "user-data"), os.path.join(d, "meta-data")], check=True)

    def start(self):
        cmd = ["qemu-system-x86_64", "-machine", f"q35,accel={self.accel}", "-cpu", "host" if self.accel == "kvm" else "max",
               "-smp", str(self.cpus), "-m", str(self.mem), "-display", "none", "-monitor", "none",
               "-serial", f"file:{self.console}", "-no-reboot",
               "-drive", f"file={self.disk},if=virtio,format=qcow2", "-drive", f"file={self.seed},if=virtio,format=raw,readonly=on",
               "-netdev", f"user,id=wan,hostfwd=tcp:127.0.0.1:{self.ssh_port}-:22", "-device", "virtio-net-pci,netdev=wan"]
        if self.usb:   # serial=drillusb shows up as /dev/disk/by-id/virtio-drillusb in the guest
            cmd += ["-drive", f"file={self.usb},if=none,id=usb,format=raw", "-device", "virtio-blk-pci,drive=usb,serial=drillusb"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(os.path.join(self.work, f"{self.name}-qemu.err"), "w"))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()

    def guard(self):
        if self.proc.poll() is not None:
            raise net.Abort(f"{self.name}: QEMU exited with {self.proc.returncode}")
        try:
            with open(self.console, "rb") as f:
                f.seek(self.scanned)
                chunk = f.read().decode("utf-8", "replace")
                self.scanned = f.tell()
        except OSError:
            return
        m = net.FATAL.search(chunk)
        if m:
            raise net.Abort(f"{self.name}: fatal console line: {m.group(0)}")

    def ssh(self):
        return ["ssh", "-i", self.key, "-p", str(self.ssh_port), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=15", "-o", "BatchMode=yes", "debian@127.0.0.1"]

    def wait_ready(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.guard()
            p = subprocess.run(self.ssh() + ["cloud-init status --wait >/dev/null 2>&1; cloud-init status"], capture_output=True, timeout=120)
            if p.returncode == 0 and b"done" in p.stdout:
                return True
            time.sleep(3)
        return False

    def run(self, script, timeout):
        """Run a bash script as root; stream nothing, return (rc, output). Abort on a fatal console line or the deadline."""
        p = subprocess.Popen(self.ssh() + ["sudo", "bash", "-s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = []
        threading.Thread(target=lambda: out.append(p.stdout.read()), daemon=True).start()
        try:
            p.stdin.write(("set -u\n" + script + "\n").encode())
            p.stdin.close()
        except BrokenPipeError:
            pass
        end = time.time() + timeout
        while p.poll() is None:
            try:
                self.guard()
            except net.Abort:
                p.kill()
                raise
            if time.time() > end:
                p.kill()
                raise net.Abort(f"{self.name}: command exceeded {timeout} s")
            time.sleep(2)
        time.sleep(0.2)
        return p.returncode, (out[0].decode("utf-8", "replace") if out else "")

    def put(self, local, remote_cmd, timeout=300):
        with open(local, "rb") as f:
            p = subprocess.run(self.ssh() + ["sudo bash -c " + net.sh_q(remote_cmd)], stdin=f, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise net.Abort(f"{self.name}: copy failed: {p.stderr.decode()[:200]}")

    def get(self, remote_path):
        p = subprocess.run(self.ssh() + ["sudo cat " + net.sh_q(remote_path)], capture_output=True, timeout=60)
        if p.returncode != 0:
            raise net.Abort(f"{self.name}: could not read {remote_path}")
        return p.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--results", required=True)
    ap.add_argument("--mem", type=int, default=6144)
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--budget", type=int, default=core.BUDGET_SECONDS, help="restore clock limit in seconds (default 3600)")
    ap.add_argument("--payload-mb", type=int, default=256)
    ap.add_argument("--tcg", action="store_true", help="no KVM (slow; never counts for the timing proof)")
    ap.add_argument("--cache", default=os.environ.get("ONEMIND_DRILL_CACHE") or os.path.join(tempfile.gettempdir(), "onemind-net-cache"))
    a = ap.parse_args()
    for tool in ("qemu-system-x86_64", "qemu-img", "cloud-localds", "ssh", "ssh-keygen", "git", "tar"):
        if not shutil.which(tool):
            sys.exit(f"missing tool: {tool}")
    accel = "kvm" if os.access("/dev/kvm", os.R_OK | os.W_OK) and not a.tcg else "tcg"
    work = tempfile.mkdtemp(prefix="restore-drill.")
    os.makedirs(os.path.dirname(os.path.abspath(a.results)), exist_ok=True)
    logs = os.path.splitext(a.results)[0] + "-logs"
    os.makedirs(logs, exist_ok=True)
    transcript, abort, boot_s, vms = [], None, None, []
    try:
        tgz, _src = net.build_tree(work, os.environ.get("ONEMIND_DRILL_SRC_REF"))
        img, pin = net.fetch_image(a.cache)
        key = os.path.join(work, "ssh_key")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
        usb = os.path.join(work, "usb.img")
        with open(usb, "wb") as f:
            f.truncate(4 << 30)   # sparse
        env = f"DRILL_PAYLOAD_MB={a.payload_mb} "

        log(f"source box: boot ({a.mem} MiB, accel={accel})")
        src = VM("source", work, key, a.mem, a.cpus, accel, usb)
        vms.append(src)
        src.prepare(img)
        src.start()
        if not src.wait_ready(300):
            raise net.Abort("source VM did not finish cloud-init with SSH within 300 s")
        src.put(tgz, "rm -rf /opt/src && mkdir -p /opt/src && tar -xzf - -C /opt/src")
        log("source box: install, seed data, back up (several minutes)")
        rc, out = src.run(f"{env}bash /opt/src/test/restore-drill/in-vm.sh source /opt/src /opt/src/onemindd 2>&1", 2700)
        transcript.append(out)
        open(os.path.join(logs, "source.log"), "w").write(net.mask(out))
        if rc != 0:
            raise net.Abort(f"source half exited {rc} (see {os.path.basename(logs)}/source.log)")
        owner_key, expected = src.get("/run/drill/owner.key"), src.get("/root/drill-expected.env")
        src.run("sync; systemctl poweroff --no-block", 60)
        for _ in range(60):
            if src.proc.poll() is not None:
                break
            time.sleep(1)
        src.stop()   # the old box is gone: only the USB disk and the owner key survive
        log("source box destroyed; booting a clean machine")

        t0 = time.time()
        new = VM("clean", work, key, a.mem, a.cpus, accel, usb)
        vms.append(new)
        new.prepare(img)
        new.start()
        if not new.wait_ready(300):
            raise net.Abort("clean VM did not finish cloud-init with SSH within 300 s")
        boot_s = round(time.time() - t0, 1)
        new.put(tgz, "rm -rf /opt/src && mkdir -p /opt/src && tar -xzf - -C /opt/src")
        for name, data, mode in (("/run/drill/owner.key", owner_key, "600"), ("/root/drill-expected.env", expected, "600")):
            p = subprocess.run(new.ssh() + ["sudo bash -c " + net.sh_q(f"mkdir -p /run/drill && umask 077 && cat > {name} && chmod {mode} {name}")],
                               input=data, capture_output=True)
            if p.returncode != 0:
                raise net.Abort("could not hand the owner key to the clean VM")
        log("clean box: install, restore, verify (this is the timed part)")
        rc, out = new.run(f"{env}bash /opt/src/test/restore-drill/in-vm.sh restore /opt/src /opt/src/onemindd 2>&1", a.budget + 900)
        transcript.append(out)
        open(os.path.join(logs, "restore.log"), "w").write(net.mask(out))
    except net.Abort as e:
        abort = str(e)
        log(f"ABORT: {abort}")
    except subprocess.CalledProcessError as e:
        abort = f"harness error: {e}"
        log(abort)
    finally:
        for v in vms:
            v.stop()
            if os.path.exists(v.console):
                shutil.copy(v.console, os.path.join(logs, os.path.basename(v.console)))
        text = "\n".join(transcript)
        result = core.evaluate(text, budget_s=a.budget, boot_seconds=boot_s, abort=abort)
        result.update({"accel": accel, "source_ref": os.environ.get("ONEMIND_DRILL_SRC_REF") or "checkout", "payload_mb": a.payload_mb,
                       "image": os.path.basename(locals().get("pin", {}).get("URL", "")) or None})
        if accel != "kvm":
            result["reasons"].append("ran without KVM: the timing is not evidence")
            if result["verdict"] == "PASS":
                result["verdict"] = "FAIL"
        json.dump(result, open(a.results, "w"), indent=2, sort_keys=True)
        open(os.path.splitext(a.results)[0] + ".md", "w").write(core.summary_markdown(result))
        print(json.dumps({k: result[k] for k in ("verdict", "restore_seconds", "budget_seconds", "reasons")}))
        if os.environ.get("ONEMIND_DRILL_KEEP") != "1":
            shutil.rmtree(work, ignore_errors=True)
    sys.exit(core.exit_code(result))


if __name__ == "__main__":
    main()
