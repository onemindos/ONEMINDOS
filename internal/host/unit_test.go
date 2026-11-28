// SPDX-License-Identifier: Apache-2.0

package host

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
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
	ok := &announceRebooter{inner: rb, before: func() { called = rb.n == 0 }, cfg: c, want: "1.3.0"}
	if err := ok.Reboot(context.Background()); err != nil || !called || rb.n != 1 {
		t.Fatal("going_down must be journaled before the reboot")
	}
	called = false
	other := &announceRebooter{inner: rb, before: func() { called = true }, cfg: c, want: "1.2.0"}
	if err := other.Reboot(context.Background()); err == nil || other.refused == nil || called || rb.n != 1 {
		t.Fatal("rebooted into a version the owner did not approve")
	}
}

// The engine: an approval for one version never reboots into another one the
// update service installed on its own (blocker: Run(ModeApply) reboots a
// pending install without running the installer).
func TestUpdateEngineNeverRebootsIntoAnotherVersion(t *testing.T) {
	dir := t.TempDir()
	conf := filepath.Join(dir, "update.conf")
	if err := os.WriteFile(conf, []byte("channel = security\nurl = https://example.org/tuf\nstate_dir = "+dir+"/state\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	c, err := update.LoadConfig(conf)
	if err != nil {
		t.Fatal(err)
	}
	offer := &update.Target{Meta: update.TargetMeta{Version: "1.2.0"}}
	rb, inst := &recReboot{}, &recInstaller{}
	pending := &update.Status{TargetVersion: "1.1.9"}
	pending.State = "pending_reboot"
	var modes []update.Mode
	u := &UpdateEngine{ConfigPath: conf,
		newEngine: func(*update.Config, *slog.Logger) *update.Engine {
			return &update.Engine{Installer: inst, Rebooter: rb}
		},
		run: func(ctx context.Context, e *update.Engine, m update.Mode) (*update.Result, error) {
			modes = append(modes, m)
			st, _ := update.LoadStatus(c)
			if m == update.ModeApply { // the engine's pending-reboot shortcut: no install, straight to reboot
				return &update.Result{Rebooted: e.Rebooter.Reboot(ctx) == nil, Status: st}, nil
			}
			return &update.Result{Candidate: offer, Status: st}, nil
		}}
	// 1. Seen at the check: refused before ModeApply runs.
	if err := pending.Save(c); err != nil {
		t.Fatal(err)
	}
	if u.UpdateBusy() == "" {
		t.Error("pending_reboot not reported busy")
	}
	var r *Refusal
	if _, _, err := u.Install(context.Background(), "1.2.0", func() { t.Error("going_down") }); !errors.As(err, &r) || r.Reason != "update_pending" {
		t.Fatalf("pending at check: %v", err)
	}
	if len(modes) != 1 || rb.n != 0 {
		t.Fatalf("modes %v reboots %d", modes, rb.n)
	}
	// 2. Appears between check and apply: the rebooter refuses.
	idle := &update.Status{TargetVersion: "1.1.9"}
	idle.State = "idle"
	if err := idle.Save(c); err != nil {
		t.Fatal(err)
	}
	modes = nil
	if _, _, err := u.Install(context.Background(), "1.2.0", func() { t.Error("going_down") }); !errors.As(err, &r) || r.Reason != "update_pending" {
		t.Fatalf("pending at apply: %v", err)
	}
	if len(modes) != 2 || rb.n != 0 || inst.n != 0 {
		t.Fatalf("modes %v reboots %d installs %d", modes, rb.n, inst.n)
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
	if v := u["ExecStart"]; len(v) != 1 || v[0] != "/usr/bin/onemindd host serve --user onemind" {
		t.Errorf("ExecStart = %q", v)
	}
	if v := u["CapabilityBoundingSet"]; len(v) != 1 || v[0] != "CAP_DAC_READ_SEARCH" {
		t.Errorf("CapabilityBoundingSet = %q, want exactly CAP_DAC_READ_SEARCH", v)
	}
	if v := u["ReadWritePaths"]; len(v) != 1 || v[0] != "/data /boot/efi" {
		t.Errorf("ReadWritePaths = %q", v)
	}
	for _, k := range []string{"User=root", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes",
		"PrivateTmp=yes", "PrivateDevices=no", "DevicePolicy=closed", "DeviceAllow=block-* r", "ProtectKernelTunables=yes", "ProtectKernelModules=yes",
		"ProtectControlGroups=yes", "RestrictSUIDSGID=yes", "MemoryDenyWriteExecute=yes", "RestrictNamespaces=yes",
		"SystemCallFilter=~@privileged", "UMask=0022", "Requires=onemind-host.socket", "AmbientCapabilities=", "RequiresMountsFor=/data",
		"RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK"} {
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

// ~@privileged forbids @chown (EPERM), so the service must never chown its
// socket: systemd makes it (onemind-host.socket) and the fallback opens it
// without a group. A text-only check of the unit missed this once.
func TestSocketNeedsNoChown(t *testing.T) {
	u := unit(t)
	for _, f := range u["SystemCallFilter"] {
		if f == "@chown" || f == "chown" {
			t.Fatal("the filter allows chown again: then the socket unit is the only safe way, keep it")
		}
	}
	b, err := os.ReadFile(filepath.Join("..", "..", "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-host.socket"))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"ListenStream=/run/onemind/host.sock", "SocketUser=root", "SocketGroup=onemind", "SocketMode=0660"} {
		if !strings.Contains(string(b), want) {
			t.Errorf("onemind-host.socket: %s missing", want)
		}
	}
	src, err := os.ReadFile(filepath.Join("..", "..", "cmd", "onemindd", "host.go"))
	if err != nil {
		t.Fatal(err)
	}
	if !regexp.MustCompile(`ops\.Listen\([^,]+,\s*-1\)`).Match(src) || strings.Contains(string(src), "Chown") {
		t.Error("cmd/onemindd/host.go must not chown (no CAP_CHOWN, @chown filtered)")
	}
	for _, f := range []string{"host.go", "server.go", "journal.go", "update.go"} {
		if b, _ := os.ReadFile(f); strings.Contains(string(b), "Chown(") {
			t.Errorf("%s chowns", f)
		}
	}
}

// The factory reset unit must run before the data set is assembled or mounted,
// only when armed, and fall into recovery mode (never the old data) on failure.
func TestFactoryResetUnitOrdering(t *testing.T) {
	b, err := os.ReadFile("../../os/recovery/onemind-factory-reset.service")
	if err != nil {
		t.Fatal(err)
	}
	s := string(b)
	for _, want := range []string{"ConditionPathExists=/boot/efi/onemind/factory-reset", "RequiresMountsFor=/boot/efi",
		"OnFailure=onemind-recovery.target", "OnFailureJobMode=isolate", "DefaultDependencies=no",
		"ExecStart=/usr/bin/onemindd factory-reset wipe"} {
		if !strings.Contains(s, want) {
			t.Errorf("unit lacks %q", want)
		}
	}
	for _, before := range []string{"data.mount", "onemind-data-assemble.service", "onemind-data-check.service", "local-fs.target"} {
		if !regexp.MustCompile(`(?m)^Before=.*\b` + regexp.QuoteMeta(before) + `\b`).MatchString(s) {
			t.Errorf("not ordered before %s", before)
		}
	}
	chk, _ := os.ReadFile("../../os/recovery/onemind-data-check")
	if !strings.Contains(string(chk), "factory-reset-pending") {
		t.Error("onemind-data-check must refuse while a marker exists")
	}
	cf, _ := os.ReadFile("../../os/rootfs/Containerfile")
	// Units are enabled by `systemctl enable a b c >/dev/null`, possibly joined to others and across
	// continuation lines; collect every enabled unit and require the wipe unit among them.
	enabled := map[string]bool{}
	joined := strings.ReplaceAll(string(cf), "\\\n", " ")
	for _, m := range regexp.MustCompile(`systemctl enable ([^;&|>]*)`).FindAllStringSubmatch(joined, -1) {
		for _, u := range strings.Fields(m[1]) {
			enabled[u] = true
		}
	}
	if !enabled["onemind-factory-reset.service"] {
		t.Error("the image does not enable the wipe unit")
	}
}

// REL-02 (#154): an approved os.update.settings writes the owner file the update engine reads; the
// image's update.conf is never touched.
func TestUpdateSettingsReachTheEngine(t *testing.T) {
	dir := t.TempDir()
	conf := filepath.Join(dir, "update.conf")
	image := "channel = security\nurl = https://example.org/tuf\nstate_dir = " + dir + "/state\n"
	if err := os.WriteFile(conf, []byte(image), 0o600); err != nil {
		t.Fatal(err)
	}
	u := &UpdateEngine{ConfigPath: conf}
	st, err := OpenStore(filepath.Join(dir, "journal"))
	if err != nil {
		t.Fatal(err)
	}
	s := &Service{Store: st, Update: u, BootID: "b"}
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "s1", Kind: KindOSSettings, Policy: "off", Window: "01:00-03:00"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("s1"); op.State != StateSucceeded || !strings.Contains(op.Message, "automatic updates are off") {
		t.Fatalf("op %+v", op)
	}
	c, err := update.LoadConfig(conf)
	if err != nil {
		t.Fatal(err)
	}
	if p, w, src, err := c.Effective(); err != nil || p != update.PolicyOff || w.String() != "01:00-03:00" || src != update.SourceOwner {
		t.Fatalf("effective %s %s %s %v", p, w, src, err)
	}
	if b, _ := os.ReadFile(conf); string(b) != image {
		t.Fatalf("image file changed: %q", b)
	}
	// The same id with other settings is a different request: refused, nothing rewritten.
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "s1", Kind: KindOSSettings, Policy: "auto", Window: "01:00-03:00"}); err == nil {
		t.Fatal("reused action id accepted")
	}
	if p, _, _, _ := c.Effective(); p != update.PolicyOff {
		t.Fatalf("policy %s after a refused reuse", p)
	}
}

func TestUpdateSettingsRequestValidation(t *testing.T) {
	for _, r := range []Request{
		{ActionID: "a", Kind: KindOSSettings, Policy: "sometimes", Window: "any"},
		{ActionID: "a", Kind: KindOSSettings, Policy: "off"},
		{ActionID: "a", Kind: KindOSSettings, Policy: "off", Window: "03:00-03:00"},
		{ActionID: "a", Kind: KindOSSettings, Policy: "off", Window: "any", Version: "1.0"},
		{ActionID: "a", Kind: KindRestart, Policy: "off"},
	} {
		if err := r.Validate(); err == nil {
			t.Errorf("accepted %+v", r)
		}
	}
	u := &UpdateEngine{ConfigPath: filepath.Join(t.TempDir(), "update.conf")}
	if why := u.SettingsUnavailable(); !strings.Contains(why, "not an A/B OneMind image") {
		t.Fatalf("%q", why)
	}
	s := &Service{Store: nil}
	if why := s.Unavailable(KindOSSettings); why == "" {
		t.Fatal("no journal, yet settings available")
	}
}
