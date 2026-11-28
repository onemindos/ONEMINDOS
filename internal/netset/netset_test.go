// SPDX-License-Identifier: Apache-2.0

package netset

import (
	"context"
	"errors"
	"os"
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
	failGet    bool
	failList   bool
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
		if f.failGet {
			return nil, errors.New("nmcli: Error: NetworkManager is not running")
		}
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
	case strings.Contains(line, "get-property") && f.failList:
		return nil, errors.New("busctl: Connection timed out")
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

const staticAction = "act-static"

var static = Config{ActionID: staticAction, Mode: "static", Address: "192.0.2.50/24", Gateway: "192.0.2.1", DNS: []string{"192.0.2.53"}, RollbackSeconds: 30}

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
	st, err = m.Confirm(context.Background(), "eth0", staticAction)
	if err != nil || st.Pending != nil || st.Last == nil || st.Last.Result != ResultConfirmed {
		t.Fatalf("confirm: %+v %v", st, err)
	}
	if f.ran("CheckpointDestroy o /org/freedesktop/NetworkManager/Checkpoint/7") != 1 || f.props["ipv4.method"] != "manual" {
		t.Fatalf("confirming keeps the new settings: %v %v", f.cmds, f.props)
	}
	if got := m.Status(context.Background()); got.Pending != nil || got.Last.Result != ResultConfirmed {
		t.Fatalf("after confirm: %+v", got)
	}
	if _, err := m.Confirm(context.Background(), "eth0", staticAction); reason(err) != "no_pending_change" {
		t.Fatalf("a second confirm: %v", err)
	}
	// And a new change may follow.
	if _, err := m.Apply(context.Background(), "eth0", Config{ActionID: "act-dhcp", Mode: "dhcp", RollbackSeconds: 30}); err != nil {
		t.Fatal(err)
	}
	if f.props["ipv4.method"] != "auto" || f.props["ipv4.addresses"] != "" || f.props["ipv4.dns"] != "" || f.props["ipv4.ignore-auto-dns"] != "no" {
		t.Fatalf("back to DHCP clears address, gateway and DNS: %v", f.props)
	}
}

func TestConfirmCannotKeepAReplacementChange(t *testing.T) {
	m, f, _ := setup(t)
	ctx := context.Background()
	if _, err := m.Apply(ctx, "eth0", static); err != nil {
		t.Fatal(err)
	}
	if _, err := m.Confirm(ctx, "eth0", staticAction); err != nil {
		t.Fatal(err)
	}
	replacement := Config{ActionID: "act-dhcp", Mode: "dhcp", RollbackSeconds: 30}
	if _, err := m.Apply(ctx, "eth0", replacement); err != nil {
		t.Fatal(err)
	}
	destroys := f.ran("CheckpointDestroy")
	if _, err := m.Confirm(ctx, "eth0", staticAction); reason(err) != "change_mismatch" {
		t.Fatalf("refuse confirmation for the preceding approval: %v", err)
	}
	if cur, _ := m.load(); cur == nil || cur.ActionID != replacement.ActionID || cur.ConfirmedAt != nil || f.ran("CheckpointDestroy") != destroys {
		t.Fatalf("replacement must still have its checkpoint and rollback timer: %+v %v", cur, f.cmds)
	}
	if st, err := m.Confirm(ctx, "eth0", replacement.ActionID); err != nil || st.Last == nil || st.Last.ActionID != replacement.ActionID {
		t.Fatalf("the replacement's own approval can confirm it: %+v %v", st, err)
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
	if _, err := m.Confirm(context.Background(), "eth0", staticAction); reason(err) != "no_pending_change" {
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
	if _, err := m2.Confirm(context.Background(), "eth0", staticAction); err != nil {
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

// blockSave makes the next record writes fail (the temp file's name is taken by a non-empty directory, which
// even root cannot write over) while the record already on disk stays readable. It returns the undo.
func blockSave(t *testing.T, m *Manager) func() {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(m.path()+".tmp", "x"), 0o700); err != nil {
		t.Fatal(err)
	}
	return func() { _ = os.RemoveAll(m.path() + ".tmp") }
}

func pristine() map[string]string {
	return map[string]string{"ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "", "ipv4.dns": "", "ipv4.ignore-auto-dns": "no"}
}

// Review of #1156 (round 2, item 2): the checkpoint is destroyed, then the record cannot be written. The owner was
// told "Confirmed"; the change must stay, not be undone later as a lost checkpoint.
func TestConfirmWhoseFinalRecordFailsIsStillKept(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	var undo func()
	f2 := &hookNM{fakeNM: f, onDestroy: func() { undo = blockSave(t, m) }}
	m.Run = f2
	st, err := m.Confirm(context.Background(), "eth0", staticAction)
	if err != nil || st.Last == nil || st.Last.Result != ResultConfirmed {
		t.Fatalf("confirm: %+v %v", st, err)
	}
	if cur, _ := m.load(); cur == nil || cur.Result != ResultPending || cur.ConfirmedAt == nil {
		t.Fatalf("the record on disk still says pending, with the confirmation: %+v", cur)
	}
	undo()
	modifies := f.ran("connection modify")
	for _, later := range []time.Duration{5 * time.Second, time.Minute} { // before and after the deadline
		*now = now.Add(later)
		got := m.Status(context.Background())
		if got.Pending != nil || got.Last == nil || got.Last.Result != ResultConfirmed {
			t.Fatalf("after %v: %+v", later, got)
		}
	}
	if f.ran("connection modify") != modifies || f.props["ipv4.method"] != "manual" || f.props["ipv4.addresses"] != "192.0.2.50/24" {
		t.Fatalf("a confirmed change is never put back: %v %v", f.cmds, f.props)
	}
}

// hookNM runs a callback after a successful CheckpointDestroy.
type hookNM struct {
	*fakeNM
	onDestroy func()
}

func (h *hookNM) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	out, err := h.fakeNM.Run(ctx, name, args...)
	if err == nil && strings.Contains(strings.Join(args, " "), "CheckpointDestroy") && h.onDestroy != nil {
		h.onDestroy()
		h.onDestroy = nil
	}
	return out, err
}

func TestConfirmThatCannotBeRecordedConfirmsNothing(t *testing.T) {
	m, f, _ := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	undo := blockSave(t, m)
	if _, err := m.Confirm(context.Background(), "eth0", staticAction); reason(err) != "confirm_failed" {
		t.Fatalf("got %v", err)
	}
	undo()
	if f.checkpoint == "" || f.ran("CheckpointDestroy") != 0 {
		t.Fatalf("the checkpoint stays, so the change still rolls back at its deadline: %v", f.cmds)
	}
	if st := m.Status(context.Background()); st.Pending == nil {
		t.Fatalf("still pending: %+v", st)
	}
}

// The box went down after the confirmation was recorded but before the checkpoint was destroyed, and
// NetworkManager's timer ran out: the old settings are back, so the record says rolled_back, not confirmed.
func TestConfirmationRecordedButNetworkManagerRolledBackFirst(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	cur, last := m.load()
	at := *now
	cur.ConfirmedAt = &at
	if err := m.save(cur, last); err != nil {
		t.Fatal(err)
	}
	*now = now.Add(31 * time.Second)
	f.checkpoint, f.props = "", pristine()
	st := m.Status(context.Background())
	if st.Pending != nil || st.Last == nil || st.Last.Result != ResultRolledBack {
		t.Fatalf("%+v", st)
	}
}

// After a reboot, a change the owner confirmed (recorded) whose final record was lost is kept.
func TestRecoverKeepsAConfirmedChange(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	cur, last := m.load()
	at := *now
	cur.ConfirmedAt = &at
	_ = m.save(cur, last)
	f.checkpoint = ""
	m2 := &Manager{Run: f, StatePath: m.StatePath, BootID: "boot-2", Now: m.Now}
	m2.Recover(context.Background())
	if _, l := m2.load(); l == nil || l.Result != ResultConfirmed || f.props["ipv4.method"] != "manual" {
		t.Fatalf("%+v %v", l, f.props)
	}
}

// Review of #1156 (round 2, item 5): an unreadable profile is never saved as the settings to put back.
func TestApplyRefusesWhenTheCurrentSettingsCannotBeRead(t *testing.T) {
	m, f, _ := setup(t)
	f.failGet = true
	if _, err := m.Apply(context.Background(), "eth0", static); reason(err) != "network_unavailable" {
		t.Fatalf("got %v", err)
	}
	if f.ran("CheckpointCreate") != 0 || f.ran("connection modify") != 0 {
		t.Fatalf("nothing is touched: %v", f.cmds)
	}
	if cur, _ := m.load(); cur != nil {
		t.Fatalf("no record: %+v", cur)
	}
}

// Review of #1156 (round 2, item 3): when the put-back after a failed apply fails too, the owner is not told the
// old settings are back.
func TestFailedApplyWhosePutBackFailsSaysSo(t *testing.T) {
	m, f, _ := setup(t)
	f.failUp = true
	hook := &modifyFailsAfterFirst{fakeNM: f}
	m.Run = hook
	_, err := m.Apply(context.Background(), "eth0", static)
	var r *Refusal
	if !errors.As(err, &r) || r.Reason != "apply_failed" || strings.Contains(r.Message, "the old settings are back") || !strings.Contains(r.Message, "not back yet") {
		t.Fatalf("got %v", err)
	}
	if cur, _ := m.load(); cur == nil || cur.Result != ResultPending {
		t.Fatalf("stays pending for Watch to retry: %+v", cur)
	}
}

type modifyFailsAfterFirst struct {
	*fakeNM
	n int
}

func (h *modifyFailsAfterFirst) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	if strings.Contains(strings.Join(args, " "), "connection modify") {
		h.n++
		h.fakeNM.failModify = h.n > 1
	}
	return h.fakeNM.Run(ctx, name, args...)
}

// The way back must not depend on somebody opening the Network screen: Watch settles a change whose checkpoint
// NetworkManager lost (a restart), and one Recover could not settle at boot.
func TestWatchSettlesWithoutAnyoneLooking(t *testing.T) {
	m, f, _ := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	f.checkpoint = "" // NetworkManager restarted: the timer is gone, the new profile is in force
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { m.Watch(ctx, 5*time.Millisecond); close(done) }()
	deadline := time.Now().Add(5 * time.Second)
	for {
		if cur, last := m.load(); cur == nil && last != nil && last.Result == ResultRolledBack {
			break
		}
		if time.Now().After(deadline) {
			cancel()
			<-done
			t.Fatal("Watch did not settle the change")
		}
		time.Sleep(5 * time.Millisecond)
	}
	cancel()
	<-done
	if f.props["ipv4.method"] != "auto" || f.props["ipv4.addresses"] != "" {
		t.Fatalf("old settings back: %v", f.props)
	}
}

// Review of #1156 (round 2, item 4): a read never waits behind an Apply that holds the lock.
func TestStatusDoesNotWaitForAChangeInProgress(t *testing.T) {
	m, _, _ := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	m.mu.Lock()
	got := make(chan Status, 1)
	go func() { got <- m.Status(context.Background()) }()
	select {
	case st := <-got:
		if st.Pending == nil || st.Pending.Interface != "eth0" || st.Pending.Checkpoint != "" || st.Pending.Previous != nil {
			t.Fatalf("answers from the record, stripped: %+v", st.Pending)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Status waited for the lock")
	}
	m.mu.Unlock()
}

// A failed read of NetworkManager's checkpoint list decides nothing: Watch runs every few seconds, and treating
// a D-Bus hiccup as "checkpoint gone" would undo a change before its deadline.
func TestAnUnreadableCheckpointListLeavesTheChangePending(t *testing.T) {
	m, f, now := setup(t)
	if _, err := m.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	*now = now.Add(5 * time.Second)
	f.failList = true
	modifies := f.ran("connection modify")
	if st := m.Status(context.Background()); st.Pending == nil {
		t.Fatalf("still pending: %+v", st)
	}
	if f.ran("connection modify") != modifies || f.props["ipv4.method"] != "manual" {
		t.Fatalf("nothing was put back: %v", f.cmds)
	}
	f.failList = false
	if _, err := m.Confirm(context.Background(), "eth0", staticAction); err != nil {
		t.Fatalf("the owner can still confirm: %v", err)
	}
	// After the deadline an unreadable list no longer holds the way back.
	m2, f2, now2 := setup(t)
	if _, err := m2.Apply(context.Background(), "eth0", static); err != nil {
		t.Fatal(err)
	}
	*now2 = now2.Add(40 * time.Second)
	f2.failList = true
	if st := m2.Status(context.Background()); st.Pending != nil || st.Last == nil || st.Last.Result != ResultRolledBack || f2.props["ipv4.method"] != "auto" {
		t.Fatalf("settled after the deadline: %+v %v", st, f2.props)
	}
}
