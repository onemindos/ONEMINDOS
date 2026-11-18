// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// unitSettings reads the systemd unit as key -> every value given (a key may repeat).
func unitSettings(t *testing.T) map[string][]string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("..", "..", "deploy", "systemd", "onemind-rescue.service"))
	if err != nil {
		t.Fatal(err)
	}
	m := map[string][]string{}
	for _, l := range strings.Split(string(b), "\n") {
		l = strings.TrimSpace(l)
		if k, v, ok := strings.Cut(l, "="); ok && !strings.HasPrefix(l, "#") && !strings.HasPrefix(l, "[") {
			m[k] = append(m[k], v)
		}
	}
	return m
}

func has(vals []string, want string) bool {
	for _, v := range vals {
		if v == want {
			return true
		}
	}
	return false
}

// The shell is a child of the rescue unit, so the unit must let a pty and the audit file work, and must
// not be loosened beyond that. Both halves are pinned: a hardening line removed is as much a failure as a
// pty line missing.
func TestRescueUnitLetsTheTerminalWorkAndNothingMore(t *testing.T) {
	u := unitSettings(t)
	// needed: a pty, the audit directory
	if has(u["PrivateDevices"], "yes") {
		t.Error("PrivateDevices=yes hides /dev/ptmx: no shell can open")
	}
	for _, d := range []string{"/dev/ptmx rw", "char-pts rw"} {
		if !has(u["DeviceAllow"], d) {
			t.Errorf("DeviceAllow=%s missing", d)
		}
	}
	if !has(u["ReadWritePaths"], "/var/lib/onemind") {
		t.Error("ReadWritePaths=/var/lib/onemind missing: the audit chain cannot be written, so no shell may open")
	}
	// not loosened: devices closed to an allow list, read-only system, no privileges
	if !has(u["DevicePolicy"], "closed") {
		t.Error("DevicePolicy=closed missing: with PrivateDevices off every device would be open")
	}
	for _, d := range u["DeviceAllow"] {
		dev, mode, _ := strings.Cut(d, " ")
		if strings.ContainsAny(mode, "m") || strings.HasSuffix(dev, "*") || strings.Contains(dev, "mem") ||
			strings.Contains(dev, "kmsg") || strings.HasPrefix(dev, "block-") || dev == "/dev/sda" {
			t.Errorf("DeviceAllow=%s is wider than a pty needs", d)
		}
	}
	for _, k := range []string{"NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes",
		"ProtectKernelTunables=yes", "ProtectKernelModules=yes", "RestrictSUIDSGID=yes", "MemoryDenyWriteExecute=yes",
		"RestrictNamespaces=yes", "SystemCallFilter=~@privileged"} {
		key, val, _ := strings.Cut(k, "=")
		if !has(u[key], val) {
			t.Errorf("%s was removed", k)
		}
	}
	// The console needs exactly one capability (CORE-UPDATE-9: read the onemind-owned CA key and tokens); the
	// shell sheds it through the helper (shell.go), which needs capset and nothing else from @privileged.
	if v := u["CapabilityBoundingSet"]; len(v) != 1 || v[0] != "CAP_DAC_READ_SEARCH" {
		t.Errorf("CapabilityBoundingSet = %q, want exactly [CAP_DAC_READ_SEARCH]", v)
	}
	if v := u["AmbientCapabilities"]; len(v) != 1 || v[0] != "" {
		t.Errorf("AmbientCapabilities = %q: nothing may pass to children on its own", v)
	}
	if v, want := strings.Join(u["SystemCallFilter"], "|"), "@system-service|~@privileged|capset"; v != want {
		t.Errorf("SystemCallFilter = %q, want %q (only capset is taken back from @privileged)", v, want)
	}
	for _, rw := range u["ReadWritePaths"] {
		if rw != "/var/lib/onemind" {
			t.Errorf("ReadWritePaths=%s: the audit directory is the only writable path", rw)
		}
	}
	for _, af := range strings.Fields(strings.Join(u["RestrictAddressFamilies"], " ")) {
		if af != "AF_INET" && af != "AF_INET6" && af != "AF_UNIX" {
			t.Errorf("address family %s is not needed", af)
		}
	}
	if !strings.HasSuffix(strings.Join(u["ExecStart"], ""), "onemindd rescue") || !has(u["User"], "root") {
		t.Error("unit no longer runs `onemindd rescue` as root")
	}
}
