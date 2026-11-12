// SPDX-License-Identifier: Apache-2.0

package mesh

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// All addresses below are examples from 100.64.0.0/10 (the mesh range) and the
// RFC 5737 documentation range 203.0.113.0/24.

var now = time.Date(2026, 11, 12, 10, 0, 0, 0, time.UTC)

// fakeRunner scripts the tailscale CLI.
type fakeRunner struct {
	mu       sync.Mutex
	calls    [][]string
	statuses [][]byte // returned in order by "status"; the last one repeats
	statErr  error
	upErr    error
	onUp     func(args []string)
}

func (f *fakeRunner) Run(_ context.Context, args ...string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, append([]string(nil), args...))
	switch args[0] {
	case "status":
		if f.statErr != nil {
			return nil, f.statErr
		}
		out := f.statuses[0]
		if len(f.statuses) > 1 {
			f.statuses = f.statuses[1:]
		}
		return out, nil
	case "up":
		if f.onUp != nil {
			f.onUp(args)
		}
		return nil, f.upErr
	}
	return nil, errors.New("unexpected command " + args[0])
}

func statusJSON(t *testing.T, backend string, selfIPs []string, peers map[string]map[string]any) []byte {
	t.Helper()
	st := map[string]any{
		"BackendState": backend,
		"Self":         map[string]any{"HostName": "node-3f9c2a1b7d4e", "TailscaleIPs": selfIPs},
		"Peer":         peers,
	}
	b, err := json.Marshal(st)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func ts(d time.Duration) string { return now.Add(-d).Format(time.RFC3339Nano) }

func samplePeers() map[string]map[string]any {
	return map[string]map[string]any{
		"nodekey:a": {"HostName": "hub", "DNSName": "node-hub.onemind.internal.", "TailscaleIPs": []string{"100.64.0.1", "fd7a:115c:a1e0::1"},
			"Tags": []string{"tag:onemind-hub", "tag:onemind-k3s"}, "CurAddr": "203.0.113.10:41641", "Relay": "onemind-hub",
			"Online": true, "LastHandshake": ts(30 * time.Second)},
		"nodekey:b": {"HostName": "field", "DNSName": "node-field.onemind.internal.", "TailscaleIPs": []string{"100.64.0.7"},
			"Tags": []string{"tag:onemind-leaf"}, "CurAddr": "", "Relay": "onemind-hub",
			"Online": true, "LastHandshake": ts(90 * time.Second)},
		"nodekey:c": {"HostName": "phone", "DNSName": "phone.onemind.internal.", "TailscaleIPs": []string{"100.64.0.9"},
			"CurAddr": "", "Relay": "onemind-hub", "Online": false, "LastHandshake": "0001-01-01T00:00:00Z"},
	}
}

func client(f *fakeRunner) *Client { return &Client{Runner: f, Now: func() time.Time { return now }} }

func TestStatusUp(t *testing.T) {
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "Running", []string{"100.64.0.5", "fd7a:115c:a1e0::5"}, samplePeers())}}
	s := client(f).Status(context.Background())
	if s.State != StateUp || s.Addr != "100.64.0.5" {
		t.Fatalf("state=%s addr=%s", s.State, s.Addr)
	}
	if s.Path != PathRelayed || s.HubPath != PathDirect {
		t.Fatalf("path=%s hub_path=%s", s.Path, s.HubPath)
	}
	want := map[string]string{"node-hub": PathDirect, "node-field": PathRelayed, "phone": PathNone}
	if len(s.Peers) != 3 {
		t.Fatalf("peers=%d", len(s.Peers))
	}
	for _, p := range s.Peers {
		if want[p.Name] != p.Path {
			t.Errorf("peer %s path %s, want %s", p.Name, p.Path, want[p.Name])
		}
	}
	if s.LastHandshake == nil || *s.LastHandshake != "2026-11-12T09:59:30Z" {
		t.Fatalf("last_handshake=%v", s.LastHandshake)
	}
	if s.Peers[2].LastHandshake != nil {
		t.Errorf("zero handshake should be null")
	}
}

func TestHeartbeatCarriesNoAddresses(t *testing.T) {
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "Running", []string{"100.64.0.5"}, samplePeers())}}
	h := client(f).Status(context.Background()).Heartbeat()
	if h.Peers != 3 || h.Direct != 1 || h.Relayed != 1 || h.HubPath != PathDirect {
		t.Fatalf("%+v", h)
	}
	b, _ := json.Marshal(h)
	for _, bad := range []string{"100.64.", "203.0.113", "fd7a:", "node-hub", "phone"} {
		if strings.Contains(string(b), bad) {
			t.Fatalf("heartbeat leaks %q: %s", bad, b)
		}
	}
}

func TestStaleRelayedPeerIsIdle(t *testing.T) {
	p := samplePeers()
	p["nodekey:b"]["LastHandshake"] = ts(10 * time.Minute)
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "Running", []string{"100.64.0.5"}, p)}}
	s := client(f).Status(context.Background())
	if s.Path != PathDirect {
		t.Fatalf("path=%s", s.Path)
	}
}

func TestStatusNotRunning(t *testing.T) {
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "NeedsLogin", nil, nil)}}
	s := client(f).Status(context.Background())
	if s.State != StateDown || s.Backend != "NeedsLogin" || s.Path != PathNone {
		t.Fatalf("%+v", s)
	}
	// Running but no address in the mesh range is not up.
	f = &fakeRunner{statuses: [][]byte{statusJSON(t, "Running", []string{"198.51.100.4"}, nil)}}
	if s := client(f).Status(context.Background()); s.State != StateDown {
		t.Fatalf("%+v", s)
	}
}

func TestStatusDaemonDownAndNotInstalled(t *testing.T) {
	f := &fakeRunner{statErr: errors.New("failed to connect to local tailscaled")}
	if s := client(f).Status(context.Background()); s.State != StateDown || s.Error == "" {
		t.Fatalf("%+v", s)
	}
	f = &fakeRunner{statErr: ErrNotInstalled}
	s := client(f).Status(context.Background())
	if s.State != StateNone || s.Heartbeat().State != StateNone {
		t.Fatalf("%+v", s)
	}
	if reporter(client(f), nil)() != nil {
		t.Fatal("reporter must omit the object when there is no mesh")
	}
}

func bundle() *Bundle {
	return &Bundle{
		ControlURL: "https://control.onemind.internal", ControlAddrs: []string{"192.0.2.10"},
		AuthKey: "test-" + strings.Repeat("k", 20), Hostname: "node-3f9c2a1b7d4e", HubMeshIP: "100.64.0.1",
		ShieldsUp: true,
	}
}

func TestEnrollWritesKeyFileOnlyDuringUp(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "mesh")
	b := bundle()
	var seenKey, keyPath string
	var mode os.FileMode
	f := &fakeRunner{
		statuses: [][]byte{
			statusJSON(t, "NeedsLogin", nil, nil),
			statusJSON(t, "Starting", nil, nil),
			statusJSON(t, "Running", []string{"100.64.0.5"}, nil),
		},
		onUp: func(args []string) {
			for _, a := range args {
				if v, ok := strings.CutPrefix(a, "--auth-key=file:"); ok {
					keyPath = v
				}
				if strings.Contains(a, b.AuthKey) {
					t.Errorf("auth key on the command line: %q", a)
				}
			}
			fi, err := os.Stat(keyPath)
			if err != nil {
				t.Fatalf("key file missing during up: %v", err)
			}
			mode = fi.Mode().Perm()
			raw, _ := os.ReadFile(keyPath)
			seenKey = string(raw)
		},
	}
	res, err := client(f).Enroll(context.Background(), b, EnrollOptions{KeyDir: dir, Timeout: 5 * time.Second, Poll: time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	if res.Already || res.Addr != "100.64.0.5" {
		t.Fatalf("%+v", res)
	}
	if seenKey != b.AuthKey || mode != 0o600 {
		t.Fatalf("key=%q mode=%o", seenKey, mode)
	}
	if _, err := os.Stat(keyPath); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("key file not deleted: %v", err)
	}
	if fi, _ := os.Stat(dir); fi.Mode().Perm() != 0o700 {
		t.Fatalf("key dir mode %o", fi.Mode().Perm())
	}
	var up []string
	for _, c := range f.calls {
		if c[0] == "up" {
			up = c
		}
	}
	for _, want := range []string{"--login-server=https://control.onemind.internal", "--hostname=node-3f9c2a1b7d4e",
		"--accept-routes=false", "--ssh=false", "--shields-up", "--reset"} {
		if !contains(up, want) {
			t.Errorf("up args %v missing %s", up, want)
		}
	}
}

func TestEnrollFailureStillDeletesKey(t *testing.T) {
	dir := t.TempDir()
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "NeedsLogin", nil, nil)}, upErr: errors.New("authkey already used")}
	_, err := client(f).Enroll(context.Background(), bundle(), EnrollOptions{KeyDir: dir, Timeout: time.Second})
	if err == nil || !strings.Contains(err.Error(), "already used") {
		t.Fatalf("err=%v", err)
	}
	if strings.Contains(err.Error(), bundle().AuthKey) {
		t.Fatal("error leaks the key")
	}
	left, _ := os.ReadDir(dir)
	if len(left) != 0 {
		t.Fatalf("files left: %v", left)
	}
}

func TestEnrollAlreadyUpDoesNotUseKey(t *testing.T) {
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "Running", []string{"100.64.0.5"}, nil)}}
	res, err := client(f).Enroll(context.Background(), bundle(), EnrollOptions{KeyDir: t.TempDir()})
	if err != nil || !res.Already {
		t.Fatalf("res=%+v err=%v", res, err)
	}
	for _, c := range f.calls {
		if c[0] == "up" {
			t.Fatal("up must not run when already enrolled")
		}
	}
}

func TestEnrollNotInstalled(t *testing.T) {
	f := &fakeRunner{statErr: ErrNotInstalled}
	if _, err := client(f).Enroll(context.Background(), bundle(), EnrollOptions{KeyDir: t.TempDir()}); !errors.Is(err, ErrNotInstalled) {
		t.Fatalf("err=%v", err)
	}
}

func TestWaitIPTimeout(t *testing.T) {
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "Starting", nil, nil)}}
	_, err := client(f).WaitIP(context.Background(), 30*time.Millisecond, 5*time.Millisecond)
	if err == nil || !strings.Contains(err.Error(), "Starting") {
		t.Fatalf("err=%v", err)
	}
}

func TestBundleValidate(t *testing.T) {
	cases := map[string]func(b *Bundle){
		"http":      func(b *Bundle) { b.ControlURL = "http://control.onemind.internal" },
		"userinfo":  func(b *Bundle) { b.ControlURL = "https://u:p@control.onemind.internal" },
		"query":     func(b *Bundle) { b.ControlURL = "https://control.onemind.internal/?x=1" },
		"empty key": func(b *Bundle) { b.AuthKey = " " },
		"key space": func(b *Bundle) { b.AuthKey = "a b" },
		"hostname":  func(b *Bundle) { b.Hostname = "Node_1" },
		"hub ip":    func(b *Bundle) { b.HubMeshIP = "198.51.100.1" },
		"ctrl addr": func(b *Bundle) { b.ControlAddrs = []string{"hub.local"} },
		"ca sha256": func(b *Bundle) { b.CASHA256 = "ABC" },
	}
	if err := bundle().Validate(); err != nil {
		t.Fatalf("valid bundle: %v", err)
	}
	for name, mut := range cases {
		b := bundle()
		mut(b)
		err := b.Validate()
		if err == nil {
			t.Errorf("%s: accepted", name)
		} else if strings.Contains(err.Error(), bundle().AuthKey) {
			t.Errorf("%s: error leaks the key", name)
		}
	}
}

func TestCLI(t *testing.T) {
	f := &fakeRunner{statuses: [][]byte{statusJSON(t, "Running", []string{"100.64.0.5"}, samplePeers())}}
	var out, errw bytes.Buffer
	if code := runCLI(client(f), []string{"status"}, &out, &errw); code != 0 {
		t.Fatalf("code %d: %s", code, errw.String())
	}
	if !strings.Contains(out.String(), "node-hub") || !strings.Contains(out.String(), "relayed (hub: direct)") {
		t.Fatalf("table:\n%s", out.String())
	}
	out.Reset()
	if code := runCLI(client(f), []string{"status", "--json"}, &out, &errw); code != 0 {
		t.Fatal(code)
	}
	var s State
	if err := json.Unmarshal(out.Bytes(), &s); err != nil || s.State != StateUp {
		t.Fatalf("json: %v %+v", err, s)
	}
	out.Reset()
	if code := runCLI(client(f), []string{"wait-ip", "--timeout", "1s"}, &out, &errw); code != 0 || strings.TrimSpace(out.String()) != "100.64.0.5" {
		t.Fatalf("wait-ip: %d %q", code, out.String())
	}
	if code := runCLI(client(f), []string{"bogus"}, &out, &errw); code != 2 {
		t.Fatal(code)
	}
	if code := runCLI(client(f), []string{"enroll"}, &out, &errw); code != 1 {
		t.Fatal(code)
	}
	// enroll from a bundle file when already up.
	p := filepath.Join(t.TempDir(), "bundle.json")
	raw, _ := json.Marshal(bundle())
	if err := os.WriteFile(p, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	out.Reset()
	if code := runCLI(client(f), []string{"enroll", "--bundle", p, "--key-dir", t.TempDir()}, &out, &errw); code != 0 || !strings.Contains(out.String(), "already") {
		t.Fatalf("enroll: %d %q %q", code, out.String(), errw.String())
	}
}

func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}
