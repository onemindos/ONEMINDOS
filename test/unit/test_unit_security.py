# SPDX-License-Identifier: Apache-2.0
"""CI score gate: no OneMind systemd unit may be less sandboxed than its recorded ceiling.

`systemd-analyze security` gives every unit an "exposure" score from 0.0 (fully locked down) to 10.0
(no sandbox at all). This test scores every unit the image ships (os/**/*.service, with its drop-ins
applied) and fails when:
  - a unit scores above its ceiling in CEILINGS (the ceiling is the measured score plus a small margin,
    so a PR that removes a sandbox line fails), or
  - a unit has no ceiling and scores above DEFAULT_CEILING (so a NEW unit must be sandboxed from day one,
    or be added to CEILINGS on purpose, in a reviewed diff), or
  - CEILINGS names a unit that no longer exists (keeps the table honest).
When you harden a unit, lower its ceiling in the same PR (the ratchet only turns one way).

Needs `systemd-analyze` (Linux with systemd 252 or newer; GitHub's ubuntu-24.04 runners have it). Without it
the test is skipped locally; set ONEMIND_REQUIRE_SYSTEMD_ANALYZE=1 (CI does) to make that a failure.
"""
import glob, os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A unit with no entry below must score at most this (MEDIUM or better; systemd calls 5.0 and up "MEDIUM").
DEFAULT_CEILING = 5.0

# Measured with systemd 255 in offline mode (the ceiling is the score plus about 0.3). Three groups:
CEILINGS = {
    # 1. Cannot be sandboxed without breaking what it does: containerd, the CNI and pods need mount, namespace,
    #    cgroup and device access. The one deliberate exception; do not raise it.
    "k3s.service": 9.6,
    # 2. Hardened in this PR (item 12 of the 2026-11-21 image audit). Lower these when you add more lines.
    "onemind-firstboot.service": 7.1,
    "onemind-mesh-setup.service": 6.9,
    "onemind-fabric-join.service": 6.9,
    "tailscaled.service": 5.3,
    "onemind-local-api.service": 1.7,
    "onemind-recovery-web.service": 5.3,
    # 3. Not sandboxed yet. Each is a boot-time or board-specific oneshot that needs its own on-hardware check
    #    before it can be locked down (see the PR's follow-up list). The ceiling stops it getting worse, and a
    #    PR that hardens one should lower its number. onemind-setup.service is sandboxed by its own open PR.
    "onemind-setup.service": 8.4,
    "onemind-screen.service": 8.9,
    "onemind-ssh-hostkeys.service": 9.6,
    "onemind-rpi5-grow.service": 9.6,
    "onemind-rpi5-eeprom-check.service": 9.6,
    "onemind-recovery.service": 9.6,
    "onemind-nats-reload.service": 9.6,
    "onemind-jetson-data.service": 9.6,
    "onemind-installer-web.service": 9.6,
    "onemind-health-gate.service": 9.6,
    "onemind-gateway-kube.service": 9.6,
    "onemind-data-layout.service": 9.6,
    "onemind-data-grow.service": 9.6,
    "onemind-data-extend.service": 9.6,
    "onemind-data-check.service": 9.6,
    "onemind-cloud-home.service": 9.6,
    # 4. Units that arrived from separate PRs merged together on release/next (each was under the default when
    #    its PR ran, because the score gate only knew the units of its own branch). Recorded at their measured
    #    score plus 0.3 so they cannot get worse; hardening them is a follow-up (lower the number then).
    "onemind-data-encrypt.service": 9.6,
    "onemind-factory-reset.service": 9.6,
    "onemind-firewall.service": 9.6,
    "onemind-nvidia-setup.service": 9.6,
    "onemind-storage.service": 8.0,
    # The kiosk units (#333, UX-07) met this gate only when W0 merged them onto release/next (systemd 255:
    # kiosk 7.6, kiosk-apply 9.4). Hardening them needs an on-hardware check of the screen switch: follow-up.
    "onemind-kiosk.service": 7.9,
    "onemind-kiosk-apply.service": 9.7,
    # The UPS low-battery shutdown (IMG-06, #244; measured 9.4 with systemd 255). Cannot be sandboxed: it stops
    # k3s, kills what is left in its cgroup, unmounts /data, closes the encrypted disk and powers the box off. It
    # runs only when upsmon starts it on a low battery (onemind-ups.service and -monitor are under the default).
    "onemind-ups-shutdown.service": 9.7,
}


def unit_files():
    """Map unit name -> list of (unit file path, drop-in paths); a unit several boards ship appears once."""
    units = {}
    for path in glob.glob(os.path.join(ROOT, "os", "**", "*.service"), recursive=True):
        name = os.path.basename(path)
        if os.path.islink(path) or "@" in name or "/avahi/" in path:   # wants/ links, templates, avahi records
            continue
        units.setdefault(name, []).append(path)
    out = {}
    for name, paths in units.items():
        layer_drops = glob.glob(os.path.join(ROOT, "os", "rootfs", "layers", "*", "usr", "lib", "systemd", "system", name + ".d", "*.conf"))
        out[name] = [(p, sorted(set(glob.glob(p + ".d/*.conf")) | set(layer_drops), key=os.path.basename)) for p in paths]
    return out


def read(path):
    with open(path) as f:
        return f.read()


def merged_text(unit, drops):
    return "\n".join([read(unit)] + ["\n" + read(d) for d in drops])


def score(name, text, tmp):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(text)
    r = subprocess.run(["systemd-analyze", "security", "--offline=true", "--no-pager", path],
                       capture_output=True, text=True, timeout=60)
    m = re.search(r"Overall exposure level for \S+: ([0-9.]+)", r.stdout)
    if not m:
        raise AssertionError("no score for %s (rc=%d): %s %s" % (name, r.returncode, r.stdout[-300:], r.stderr[-300:]))
    return float(m.group(1))


def worst_score(name, copies, tmp):
    return max(score(name, merged_text(u, d), tmp) for u, d in copies)


class UnitSecurityScore(unittest.TestCase):
    def setUp(self):
        if not shutil.which("systemd-analyze"):
            if os.environ.get("ONEMIND_REQUIRE_SYSTEMD_ANALYZE") == "1":
                self.fail("systemd-analyze is required here (ONEMIND_REQUIRE_SYSTEMD_ANALYZE=1) and is missing")
            self.skipTest("systemd-analyze not installed (runs in CI and on the Linux build worker)")

    def test_every_unit_is_within_its_ceiling(self):
        units = unit_files()
        self.assertGreater(len(units), 20, "unit discovery found too few units")
        too_exposed, scores = [], {}
        with tempfile.TemporaryDirectory() as tmp:
            for name, copies in sorted(units.items()):
                s = scores[name] = worst_score(name, copies, tmp)
                ceiling = CEILINGS.get(name, DEFAULT_CEILING)
                if s > ceiling:
                    too_exposed.append("%s scores %.1f, ceiling %.1f" % (name, s, ceiling))
        print("\nunit exposure scores:\n" + "\n".join("  %4.1f  %s" % (v, k) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])))
        self.assertEqual(too_exposed, [], "units less sandboxed than allowed; add the missing sandbox lines "
                         "(see os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-gateway.service for a model)")

    def test_gate_bites_on_an_unsandboxed_unit(self):
        bare = "[Service]\nExecStart=/bin/true\n"
        with tempfile.TemporaryDirectory() as tmp:
            self.assertGreater(score("bare.service", bare, tmp), DEFAULT_CEILING)
            self.assertLessEqual(score("ok.service", bare + "NoNewPrivileges=yes\nProtectSystem=strict\n"
                                       "PrivateDevices=yes\nCapabilityBoundingSet=\nRestrictAddressFamilies=AF_UNIX\n"
                                       "SystemCallFilter=@system-service\nSystemCallArchitectures=native\n"
                                       "ProtectKernelTunables=yes\nProtectKernelModules=yes\nProtectKernelLogs=yes\n"
                                       "ProtectControlGroups=yes\nProtectClock=yes\nProtectHostname=yes\n"
                                       "LockPersonality=yes\nMemoryDenyWriteExecute=yes\nRestrictRealtime=yes\n"
                                       "RestrictNamespaces=yes\nRestrictSUIDSGID=yes\nPrivateTmp=yes\nProtectHome=yes\n"
                                       "DynamicUser=yes\nPrivateNetwork=yes\n", tmp), DEFAULT_CEILING)

    def test_ceiling_table_has_no_stale_names(self):
        names = set(unit_files())
        self.assertEqual(sorted(set(CEILINGS) - names), [], "CEILINGS names units that do not exist any more")


if __name__ == "__main__":
    unittest.main()
