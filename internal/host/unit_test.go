// SPDX-License-Identifier: Apache-2.0

package host

import (
	"bytes"
	"context"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/storage/ops"
	"github.com/onemindos/onemindos/internal/update"
)

func shortTempDir(t *testing.T) (string, error) {
	d, err := os.MkdirTemp("", "oh") // a Unix socket path must stay under ~100 bytes
	if err == nil {
		t.Cleanup(func() { os.RemoveAll(d) })
	}
	return d, err
}

// The real SO_PEERCRED check: a process that is neither root nor in the
// allowed group is refused.
func TestRealPeerCredRefusesStrangers(t *testing.T) {
	if runtime.GOOS != "linux" || os.Getuid() == 0 {
		t.Skip("needs Linux and a non-root test user")
	}
	dir, err := shortTempDir(t)
	if err != nil {
		t.Fatal(err)
	}
	s, p := newService(t, filepath.Join(dir, "j"), "b")
	sock := filepath.Join(dir, "h.sock")
	l, err := ops.Listen(sock, -1)
	if err != nil {
		t.Fatal(err)
	}
	gid := os.Getgid() + 1 // a group this process is not in
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- (&Server{S: s, AllowUID: -1, AllowGID: gid}).Serve(ctx, l) }()
	defer func() { cancel(); <-done }()
	c := &http.Client{Transport: &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", sock)
	}}}
	resp, err := c.Post("http://host/v1/operations", "application/json", bytes.NewBufferString(`{"action_id":"a","kind":"restart"}`))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden || p.reboots != 0 {
		t.Fatalf("status %d reboots %d", resp.StatusCode, p.reboots)
	}
}

func TestPinnedInstallerRefusesAnotherVersion(t *testing.T) {
	c := &update.Config{StateDir: t.TempDir()}
	st := &update.Status{TargetVersion: "1.3.0"}
	if err := st.Save(c); err != nil {
		t.Fatal(err)
	}
	inner := &recInstaller{}
	if err := (pinnedInstaller{inner: inner, cfg: c, want: "1.2.0"}).Install(context.Background(), "b.raucb"); err == nil || inner.n != 0 {
		t.Fatalf("installed an unapproved version: %v %d", err, inner.n)
	}
	if err := (pinnedInstaller{inner: inner, cfg: c, want: "1.3.0"}).Install(context.Background(), "b.raucb"); err != nil || inner.n != 1 {
		t.Fatalf("approved version: %v %d", err, inner.n)
	}
	called := false
	rb := &recReboot{}
	if err := (announceRebooter{inner: rb, before: func() { called = rb.n == 0 }}).Reboot(context.Background()); err != nil || !called || rb.n != 1 {
		t.Fatal("going_down must be journaled before the reboot")
	}
}

type recInstaller struct{ n int }

func (r *recInstaller) Install(context.Context, string) error { r.n++; return nil }

type recReboot struct{ n int }

func (r *recReboot) Reboot(context.Context) error { r.n++; return nil }

func TestUpdateEngineUnavailableWithoutConfig(t *testing.T) {
	u := &UpdateEngine{ConfigPath: filepath.Join(t.TempDir(), "update.conf")}
	if why := u.Unavailable(); !strings.Contains(why, "not an A/B OneMind image") {
		t.Fatalf("%q", why)
	}
	if _, _, err := u.Install(context.Background(), "1.0.0", nil); err == nil {
		t.Fatal("installed without settings")
	}
}

// unit reads the image unit as key -> every value given (a key may repeat).
func unit(t *testing.T) map[string][]string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("..", "..", "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-host.service"))
	if err != nil {
		t.Fatal(err)
	}
	m := map[string][]string{}
	for _, l := range strings.Split(string(b), "\n") {
		l = strings.TrimSpace(l)
		if k, v, ok := strings.Cut(l, "="); ok && !strings.HasPrefix(l, "#") {
			m[k] = append(m[k], v)
		}
	}
	return m
}

// The unit is privileged (it reboots the box and installs the OS), so both
// halves are pinned: what it needs, and every hardening line it keeps.
func TestHostUnitSandbox(t *testing.T) {
	u := unit(t)
	if v := u["ExecStart"]; len(v) != 1 || v[0] != "/usr/bin/onemindd host serve --group onemind" {
		t.Errorf("ExecStart = %q", v)
	}
	if v := u["CapabilityBoundingSet"]; len(v) != 1 || v[0] != "CAP_DAC_READ_SEARCH CAP_CHOWN" {
		t.Errorf("CapabilityBoundingSet = %q, want exactly CAP_DAC_READ_SEARCH CAP_CHOWN", v)
	}
	if v := u["ReadWritePaths"]; len(v) != 1 || v[0] != "/data /run/onemind" {
		t.Errorf("ReadWritePaths = %q", v)
	}
	for _, k := range []string{"User=root", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes",
		"PrivateTmp=yes", "PrivateDevices=yes", "ProtectKernelTunables=yes", "ProtectKernelModules=yes",
		"ProtectControlGroups=yes", "RestrictSUIDSGID=yes", "MemoryDenyWriteExecute=yes", "RestrictNamespaces=yes",
		"SystemCallFilter=~@privileged", "UMask=0077", "AmbientCapabilities=", "RequiresMountsFor=/data",
		"RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX"} {
		key, val, _ := strings.Cut(k, "=")
		found := false
		for _, v := range u[key] {
			found = found || v == val
		}
		if !found {
			t.Errorf("%s missing", k)
		}
	}
	if _, ok := u["WantedBy"]; !ok {
		t.Error("[Install] missing")
	}
}
