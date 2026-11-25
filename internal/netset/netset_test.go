// SPDX-License-Identifier: Apache-2.0

package netset

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// fakeNM stands in for nmcli and busctl: a profile's properties, the checkpoint list and every command run.
type fakeNM struct {
	running    bool
	devices    string
	props      map[string]string
	checkpoint string // "" = none held by NetworkManager
	cmds       []string
	failUp     bool
	failModify bool
	rollbackTo map[string]string // what a CheckpointRollback restores (nil: NetworkManager restores nothing)
}

func newFake() *fakeNM {
	return &fakeNM{running: true, devices: "eth0:ethernet:connected:6f1e1c1a-0000-4000-8000-000000000001\nlo:loopback:connected (externally):lo\nflannel.1:vxlan:unmanaged:--\neth1:ethernet:disconnected:--\ntailscale0:tun:unmanaged:--\neth2:ethernet:unmanaged:--",
		props: map[string]string{"ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "", "ipv4.dns": "", "ipv4.ignore-auto-dns": "no"}}
}

func (f *fakeNM) Run(_ context.Context, name string, args ...string) ([]byte, error) {
	line := name + " " + strings.Join(args, " ")
	f.cmds = append(f.cmds, line)
	switch {
	case strings.HasPrefix(line, "nmcli -t -g RUNNING general"):
		if f.running {
			return []byte("running\n"), nil
		}
		return nil, errors.New("nmcli: NetworkManager is not running")
	case strings.HasPrefix(line, "nmcli -t -f DEVICE,TYPE,STATE,CON-UUID device status"):
		return []byte(f.devices + "\n"), nil
	case strings.HasPrefix(line, "nmcli -t -g ipv4"):
		return []byte(f.props[args[2]] + "\n"), nil
	case strings.HasPrefix(line, "nmcli connection modify uuid "):
		if f.failModify {
			return nil, errors.New("nmcli: NetworkManager is not running")
		}
		for i := 4; i+1 < len(args); i += 2 {
			f.props[args[i]] = args[i+1]
		}
	case strings.HasPrefix(line, "nmcli --wait 40 connection up"):
		if f.failUp {
			return nil, errors.New("nmcli: Activation failed")
		}
	case strings.Contains(line, "GetDeviceByIpIface s eth0"):
		return []byte(`o "/org/freedesktop/NetworkManager/Devices/2"` + "\n"), nil
	case strings.Contains(line, "GetDeviceByIpIface"):
		return nil, errors.New("busctl: no such device")
	case strings.Contains(line, "CheckpointCreate"):
		f.checkpoint = "/org/freedesktop/NetworkManager/Checkpoint/7"
		return []byte(`o "` + f.checkpoint + `"` + "\n"), nil
	case strings.Contains(line, "CheckpointDestroy"):
		// Like NetworkManager: only a checkpoint it holds can be destroyed.
		if args[len(args)-1] != f.checkpoint || f.checkpoint == "" {
			return nil, errors.New("busctl: Call failed: checkpoint does not exist")
		}
		f.checkpoint = ""
	case strings.Contains(line, "CheckpointRollback"):
		if args[len(args)-1] != f.checkpoint || f.checkpoint == "" {
			return nil, errors.New("busctl: Call failed: checkpoint does not exist")
		}
		f.checkpoint = ""
		for k, v := range f.rollbackTo {
			f.props[k] = v
		}
	case strings.Contains(line, "get-property"):
		if f.checkpoint == "" {
			return []byte("ao 0\n"), nil
		}
		return []byte(`ao 1 "` + f.checkpoint + `"` + "\n"), nil
	}
	return nil, nil
}

func (f *fakeNM) ran(sub string) int {
	n := 0
	for _, c := range f.cmds {
		if strings.Contains(c, sub) {
			n++
		}
	}
	return n
}

func setup(t *testing.T) (*Manager, *fakeNM, *time.Time) {
	t.Helper()
	f := newFake()
	now := time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC)
	return &Manager{Run: f, StatePath: filepath.Join(t.TempDir(), "state", "change.json"), BootID: "boot-1",
		Now: func() time.Time { return now }}, f, &now
}

var static = Config{Mode: "static", Address: "192.0.2.50/24", Gateway: "192.0.2.1", DNS: []string{"192.0.2.53"}, RollbackSeconds: 30}

func reason(err error) string {
	var r *Refusal
	if errors.As(err, &r) {
		return r.Reason
	}
	return "other: " + errString(err)
}

func errString(err error) string {
	if err == nil {
		return "<nil>"
	}
	return err.Error()
}

func TestValidate(t *testing.T) {
	ok := func(c Config) Config { return c }
	cases := []struct {
		name string
		c    Config
		want string
	}{
		{"static ok", ok(static), ""},
		{"dhcp ok", Config{Mode: "dhcp"}, ""},
		{"dhcp with address", Config{Mode: "dhcp", Address: "192.0.2.5/24"}, "invalid_config"},
		{"no mode", Config{}, "invalid_mode"},
		{"ipv6", Config{Mode: "static", Address: "fd00::5/64", Gateway: "fd00::1"}, "invalid_address"},
		{"no prefix", Config{Mode: "static", Address: "192.0.2.5", Gateway: "192.0.2.1"}, "invalid_address"},
		{"network address", Config{Mode: "static", Address: "192.0.2.0/24", Gateway: "192.0.2.1"}, "invalid_address"},
		{"broadcast", Config{Mode: "static", Address: "192.0.2.255/24", Gateway: "192.0.2.1"}, "invalid_address"},
		{"loopback", Config{Mode: "static", Address: "127.0.0.2/8", Gateway: "127.0.0.1"}, "invalid_address"},
		{"link local", Config{Mode: "static", Address: "169.254.3.4/16", Gateway: "169.254.0.1"}, "invalid_address"},
		{"prefix 31", Config{Mode: "static", Address: "192.0.2.4/31", Gateway: "192.0.2.5"}, "invalid_address"},
		{"no gateway", Config{Mode: "static", Address: "192.0.2.5/24"}, "invalid_gateway"},
		{"gateway outside subnet", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "198.51.100.1"}, "invalid_gateway"},
		{"gateway is the address", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.5"}, "invalid_gateway"},
		{"gateway is broadcast", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.255"}, "invalid_gateway"},
		{"four dns", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.1", DNS: []string{"192.0.2.2", "192.0.2.3", "192.0.2.4", "192.0.2.6"}}, "invalid_dns"},
		{"dns loopback", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.1", DNS: []string{"127.0.0.1"}}, "invalid_dns"},
		{"dns ipv6", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.1", DNS: []string{"2001:db8::53"}}, "invalid_dns"},
		{"dns twice", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.1", DNS: []string{"192.0.2.9", "192.0.2.9"}}, "invalid_dns"},
		{"dns flag injection", Config{Mode: "static", Address: "192.0.2.5/24", Gateway: "192.0.2.1", DNS: []string{"--wait"}}, "invalid_dns"},
		{"rollback too short", Config{Mode: "dhcp", RollbackSeconds: 5}, "invalid_rollback"},
		{"rollback too long", Config{Mode: "dhcp", RollbackSeconds: 601}, "invalid_rollback"},
	}
	for _, tc := range cases {
		c := tc.c
		got := ""
		if err := c.Validate(); err != nil {
			got = reason(err)
		}
		if got != tc.want {
			t.Errorf("%s: got %q want %q", tc.name, got, tc.want)
		}
	}
	c := Config{Mode: "dhcp"}
	_ = c.Validate()
	if c.RollbackSeconds != 120 {
		t.Fatalf("default rollback is 120 s, got %d", c.RollbackSeconds)
	}
}

func TestApplyThenConfirm(t *testing.T) {
	m, f, now := setup(t)
	st, err := m.Apply(context.Background(), "eth0", static)
	if err != nil {
		t.Fatal(err)
	}
	if st.Pending == nil || st.Pending.Interface != "eth0" || st.Pending.Deadline != now.Add(30*time.Second) || st.Pending.Checkpoint != "" || st.Pending.Previous != nil {
		t.Fatalf("pending view: %+v", st.Pending)
	}
	if f.props["ipv4.method"] != "manual" || f.props["ipv4.addresses"] != "192.0.2.50/24" || f.props["ipv4.gateway"] != "192.0.2.1" || f.props["ipv4.dns"] != "192.0.2.53" || f.props["ipv4.ignore-auto-dns"] != "yes" {
		t.Fatalf("profile: %v", f.props)
	}
	if f.ran("CheckpointCreate aouu 1 /org/freedesktop/NetworkManager/Devices/2 30 1") != 1 {
		t.Fatalf("one checkpoint with the owner's timer: %v", f.cmds)
	}
	// The checkpoint is taken before the profile is touched.
	if ci, mi := idx(f.cmds, "CheckpointCreate"), idx(f.cmds, "connection modify"); ci < 0 || mi < ci {
		t.Fatalf("checkpoint first: %v", f.cmds)
	}
	again := m.Status(context.Background())
	if again.Pending == nil {
		t.Fatal("still pending on a second look")
	}
	if _, err := m.Apply(context.Background(), "eth0", static); reason(err) != "change_pending" {
		t.Fatalf("one change at a time: %v", err)
	}
	st, err = m.Confirm(context.Background(), "eth0")
	if err != nil || st.Pending != nil || st.Last == nil || st.Last.Result != ResultConfirmed {
		t.Fatalf("confirm: %+v %v", st, err)
	}
	if f.ran("CheckpointDestroy o /org/freedesktop/NetworkManager/Checkpoint/7") != 1 || f.props["ipv4.method"] != "manual" {
		t.Fatalf("confirming keeps the new settings: %v %v", f.cmds, f.props)
	}
	if got := m.Status(context.Background()); got.Pending != nil || got.Last.Result != ResultConfirmed {
		t.Fatalf("after confirm: %+v", got)
	}
	if _, err := m.Confirm(context.Background(), "eth0"); reason(err) != "no_pending_change" {
		t.Fatalf("a second confirm: %v", err)
	}
	// And a new change may follow.
	if _, err := m.Apply(context.Background(), "eth0", Config{Mode: "dhcp", RollbackSeconds: 30}); err != nil {
		t.Fatal(err)
	}
	if f.props["ipv4.method"] != "auto" || f.props["ipv4.addresses"] != "" || f.props["ipv4.dns"] != "" || f.props["ipv4.ignore-auto-dns"] != "no" {
		t.Fatalf("back to DHCP clears address, gateway and DNS: %v", f.props)
	}
}

func idx(cmds []string, sub string) int {
	for i, c := range cmds {
		if strings.Contains(c, sub) {
			return i
		}
	}
	return -1
}

func TestNetworkManagerRollsBackByItself(t *testing.T) {
	m, f, now := setup(t)
	f.rollbackTo = nil
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	// NetworkManager's timer ends: it drops the checkpoint and restores the profile.
	*now = now.Add(31 * time.Second)
	f.checkpoint = ""
	f.props = map[string]string{"ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "", "ipv4.dns": "", "ipv4.ignore-auto-dns": "no"}
	ups := f.ran("connection up")
	st := m.Status(context.Background())
	if st.Pending != nil || st.Last == nil || st.Last.Result != ResultRolledBack || st.Last.EndedAt == nil {
		t.Fatalf("rolled back: %+v", st)
	}
	if f.ran("connection up") != ups {
		t.Fatal("NetworkManager already restored everything: nothing is reactivated a second time")
	}
	if _, err := m.Confirm(context.Background(), "eth0"); reason(err) != "no_pending_change" {
		t.Fatalf("a late confirm is refused: %v", err)
	}
}

func TestRollbackThatLeftTheProfileChangedIsFinishedByTheHost(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	*now = now.Add(31 * time.Second)
	f.checkpoint = "" // the checkpoint is gone but the profile on disk still holds the new settings
	if st := m.Status(context.Background()); st.Last == nil || st.Last.Result != ResultRolledBack {
		t.Fatalf("%+v", st)
	}
	if f.props["ipv4.method"] != "auto" || f.props["ipv4.addresses"] != "" || f.props["ipv4.gateway"] != "" || f.props["ipv4.dns"] != "" {
		t.Fatalf("the saved settings are back: %v", f.props)
	}
}

func TestNetworkManagerLostTheCheckpointEarly(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	*now = now.Add(5 * time.Second) // well before the deadline: NetworkManager restarted, the timer is gone
	f.checkpoint = ""
	st := m.Status(context.Background())
	if st.Pending != nil || st.Last.Result != ResultRolledBack || f.props["ipv4.method"] != "auto" {
		t.Fatalf("%+v %v", st, f.props)
	}
}

func TestFailedActivationRollsBackAtOnce(t *testing.T) {
	m, f, _ := setup(t)
	f.failUp = true
	_, err := m.Apply(context.Background(), "eth0", static)
	if reason(err) != "apply_failed" {
		t.Fatalf("got %v", err)
	}
	if f.ran("CheckpointRollback") != 1 || f.props["ipv4.method"] != "auto" || f.props["ipv4.addresses"] != "" {
		t.Fatalf("rolled back: %v %v", f.cmds, f.props)
	}
	st := m.Status(context.Background())
	if st.Pending != nil || st.Last == nil || st.Last.Result != ResultRolledBack {
		t.Fatalf("%+v", st)
	}
}

func TestRefusalsChangeNothing(t *testing.T) {
	cases := []struct {
		name, iface, want string
		tweak             func(*fakeNM)
	}{
		{"loopback", "lo", "not_wired", nil},
		{"tunnel", "tailscale0", "not_wired", nil},
		{"unknown", "eth9", "unknown_interface", nil},
		{"unmanaged wired", "eth2", "unmanaged", nil},
		{"no active connection", "eth1", "no_connection", nil},
		{"option as a name", "--help", "unknown_interface", nil},
		{"NetworkManager down", "eth0", "network_unavailable", func(f *fakeNM) { f.running = false }},
	}
	for _, tc := range cases {
		m, f, _ := setup(t)
		if tc.tweak != nil {
			tc.tweak(f)
		}
		before := map[string]string{}
		for k, v := range f.props {
			before[k] = v
		}
		_, err := m.Apply(context.Background(), tc.iface, static)
		if reason(err) != tc.want {
			t.Errorf("%s: got %v want %s", tc.name, err, tc.want)
		}
		if f.ran("connection modify") != 0 || f.ran("CheckpointCreate") != 0 {
			t.Errorf("%s: a refused change touched the box: %v", tc.name, f.cmds)
		}
		for k, v := range before {
			if f.props[k] != v {
				t.Errorf("%s: %s changed", tc.name, k)
			}
		}
	}
	m, f, _ := setup(t)
	bad := static
	bad.Gateway = ""
	if _, err := m.Apply(context.Background(), "eth0", bad); reason(err) != "invalid_gateway" || len(f.cmds) != 0 {
		t.Fatalf("an invalid config is refused before anything runs: %v %v", err, f.cmds)
	}
}

func TestRecoverPutsBackAChangeThatWasWaitingAtReboot(t *testing.T) {
	m, f, _ := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	// Same boot: the host service only restarted. Recover leaves it for Status.
	m.Recover(context.Background())
	if f.props["ipv4.method"] != "manual" {
		t.Fatal("a pending change of this boot is not undone by Recover")
	}
	// The box rebooted: NetworkManager's timer is gone, the new profile is on disk.
	f.checkpoint = ""
	m2 := &Manager{Run: f, StatePath: m.StatePath, BootID: "boot-2", Now: m.Now}
	m2.Recover(context.Background())
	if f.props["ipv4.method"] != "auto" || f.props["ipv4.addresses"] != "" || f.props["ipv4.gateway"] != "" || f.props["ipv4.dns"] != "" {
		t.Fatalf("old settings back: %v", f.props)
	}
	st := m2.Status(context.Background())
	if st.Pending != nil || st.Last == nil || st.Last.Result != ResultRolledBack {
		t.Fatalf("%+v", st)
	}
	// A confirmed change is left alone by a later boot.
	if _, err := m2.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	if _, err := m2.Confirm(context.Background(), "eth0"); err != nil {
		t.Fatal(err)
	}
	(&Manager{Run: f, StatePath: m.StatePath, BootID: "boot-3"}).Recover(context.Background())
	if f.props["ipv4.method"] != "manual" {
		t.Fatal("a confirmed change survives the reboot")
	}
}

func TestSplitTerse(t *testing.T) {
	got := splitTerse(`eth0:ethernet:connected:Wired\: office`, 4)
	if len(got) != 4 || got[3] != "Wired: office" {
		t.Fatalf("%q", got)
	}
}

func TestRecoverThatCannotPutTheSettingsBackStaysPendingAndIsRetried(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	f.checkpoint = "" // the box rebooted: NetworkManager's timer is gone, the new profile is on disk
	m2 := &Manager{Run: f, StatePath: m.StatePath, BootID: "boot-2", Now: m.Now}
	f.failModify = true // NetworkManager is not answering yet
	m2.Recover(context.Background())
	if cur, last := m2.load(); cur == nil || cur.Result != ResultPending || last != nil {
		t.Fatalf("a failed put-back must not be recorded as rolled back: %+v %+v", cur, last)
	}
	if f.props["ipv4.method"] != "manual" {
		t.Fatalf("the fake should still hold the new profile: %v", f.props)
	}
	// NetworkManager is up: the next Status retries and finishes the rollback.
	f.failModify = false
	*now = now.Add(time.Minute)
	st := m2.Status(context.Background())
	if st.Pending != nil || st.Last == nil || st.Last.Result != ResultRolledBack || f.props["ipv4.method"] != "auto" || f.props["ipv4.dns"] != "" {
		t.Fatalf("%+v %v", st, f.props)
	}
}

func TestProfilesAreAddressedByUUID(t *testing.T) {
	m, f, _ := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	if f.ran("connection modify uuid 6f1e1c1a-0000-4000-8000-000000000001 ") != 1 || f.ran("connection up uuid 6f1e1c1a-0000-4000-8000-000000000001 ifname eth0") != 1 {
		t.Fatalf("%v", f.cmds)
	}
}
