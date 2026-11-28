// SPDX-License-Identifier: Apache-2.0

// Package netset changes a wired interface's IPv4 settings (static address and DNS, or back to DHCP)
// with an automatic way back (P-08). It is the box side of `PUT /v1/network/{iface}` and runs inside
// the host service (internal/host), only after an owner approved the change in the gateway.
//
// Why a checkpoint: a wrong address cuts off the person who typed it, and they cannot undo it from a
// screen they can no longer reach. NetworkManager has a built-in answer, the checkpoint (D-Bus
// CheckpointCreate with a rollback timeout, see the NetworkManager reference manual): it remembers the
// connection settings, and unless somebody calls CheckpointDestroy before the timer ends it puts them
// back by itself. The owner confirms the approved action after checking the new address; if they cannot reach it, nothing is
// needed from them and the old settings return. The profile is a keyfile under
// /etc/NetworkManager/system-connections, a bind mount from /data, so a confirmed change survives
// reboots and A/B updates (os/rootfs/layers/networkmanager).
//
// A reboot kills NetworkManager's timer but not the file it already wrote. So the settings that were in
// force are saved first, and Recover (run when the host service starts) puts them back if a change was
// still waiting for confirmation when the box went down.
package netset

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/netip"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Results of a change.
const (
	ResultPending    = "pending"     // applied; waiting for the owner to confirm
	ResultConfirmed  = "confirmed"   // the owner confirmed; it stays
	ResultRolledBack = "rolled_back" // nobody confirmed in time (or it failed); the old settings are back
)

const (
	DefaultRollback = 120 * time.Second
	MinRollback     = 10 * time.Second
	MaxRollback     = 600 * time.Second
	DefaultState    = "/data/onemind/host/network-change.json"

	nmBus  = "org.freedesktop.NetworkManager"
	nmPath = "/org/freedesktop/NetworkManager"
	// CheckpointCreate flag 1 = DESTROY_ALL: an old, forgotten checkpoint never blocks a new one.
	checkpointFlags = "1"
)

var (
	ifaceRe      = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,14}$`) // the kernel's 15-character limit
	actionIDRe   = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$`)
	checkpointRe = regexp.MustCompile(`"(/org/freedesktop/NetworkManager/Checkpoint/\d+)"`)
	devicePathRe = regexp.MustCompile(`"(/org/freedesktop/NetworkManager/Devices/\d+)"`)
	// The properties a change touches, and so the ones that are saved and put back.
	props = []string{"ipv4.method", "ipv4.addresses", "ipv4.gateway", "ipv4.dns", "ipv4.ignore-auto-dns"}
)

// Refusal is a request the box will not run: a stable Reason for the gateway and a Message for the owner.
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

func refuse(reason, format string, a ...any) *Refusal {
	return &Refusal{Reason: reason, Message: fmt.Sprintf(format, a...)}
}

// Config is the wanted IPv4 setup of one interface.
type Config struct {
	ActionID        string   `json:"action_id"`                  // the gateway's approved action
	Mode            string   `json:"mode"`                       // static | dhcp
	Address         string   `json:"address,omitempty"`          // static: CIDR, e.g. 192.0.2.10/24
	Gateway         string   `json:"gateway,omitempty"`          // static: a host inside the subnet
	DNS             []string `json:"dns,omitempty"`              // static: up to three servers
	RollbackSeconds int      `json:"rollback_seconds,omitempty"` // 10-600, default 120
}

// Validate refuses a malformed or unsafe Config and fills the default rollback time.
func (c *Config) Validate() error {
	if c.RollbackSeconds == 0 {
		c.RollbackSeconds = int(DefaultRollback / time.Second)
	}
	if d := time.Duration(c.RollbackSeconds) * time.Second; d < MinRollback || d > MaxRollback {
		return refuse("invalid_rollback", "the rollback time must be between %d and %d seconds", int(MinRollback/time.Second), int(MaxRollback/time.Second))
	}
	switch c.Mode {
	case "dhcp":
		if c.Address != "" || c.Gateway != "" || len(c.DNS) > 0 {
			return refuse("invalid_config", "automatic (DHCP) takes no address, gateway or DNS: the router hands them out")
		}
		return nil
	case "static":
	default:
		return refuse("invalid_mode", "mode must be static or dhcp")
	}
	pfx, err := netip.ParsePrefix(c.Address)
	if err != nil || !pfx.Addr().Is4() || pfx.Masked().Addr() == pfx.Addr() && pfx.Bits() < 31 {
		return refuse("invalid_address", "address must be an IPv4 host address with its prefix, like 192.0.2.20/24")
	}
	ip := pfx.Addr()
	if pfx.Bits() < 8 || pfx.Bits() > 30 {
		return refuse("invalid_address", "the prefix length must be between 8 and 30")
	}
	if !usable(ip) || ip == broadcast(pfx) {
		return refuse("invalid_address", "%s cannot be a box address (network, broadcast, loopback, link-local or multicast)", ip)
	}
	gw, err := netip.ParseAddr(c.Gateway)
	if err != nil || !gw.Is4() {
		return refuse("invalid_gateway", "a static address needs a gateway: the router's IPv4 address")
	}
	if !pfx.Masked().Contains(gw) || gw == ip || !usable(gw) || gw == broadcast(pfx) || gw == pfx.Masked().Addr() {
		return refuse("invalid_gateway", "the gateway must be another host inside %s", pfx.Masked())
	}
	if len(c.DNS) > 3 {
		return refuse("invalid_dns", "at most three DNS servers")
	}
	seen := map[netip.Addr]bool{}
	for _, s := range c.DNS {
		a, err := netip.ParseAddr(s)
		// IPv4 only: the profile's ipv4.dns property cannot hold an IPv6 server (nmcli would fail the change later).
		if err != nil || !a.Is4() || !a.IsGlobalUnicast() || seen[a] {
			return refuse("invalid_dns", "%q is not a usable, distinct DNS server address", s)
		}
		seen[a] = true
	}
	return nil
}

func usable(a netip.Addr) bool { return a.IsGlobalUnicast() && !a.IsUnspecified() }

func broadcast(p netip.Prefix) netip.Addr {
	b := p.Masked().Addr().As4()
	host := 32 - p.Bits()
	for i := 0; i < host; i++ {
		b[3-i/8] |= 1 << (i % 8)
	}
	return netip.AddrFrom4(b)
}

// Change is one change and what became of it (the record on /data).
type Change struct {
	ActionID   string            `json:"action_id,omitempty"`
	Interface  string            `json:"interface"`
	Connection string            `json:"connection"` // the profile's UUID (a name can collide with nmcli's own keywords)
	Mode       string            `json:"mode"`
	Address    string            `json:"address,omitempty"`
	Gateway    string            `json:"gateway,omitempty"`
	DNS        []string          `json:"dns,omitempty"`
	Result     string            `json:"result"`
	StartedAt  time.Time         `json:"started_at"`
	Deadline   time.Time         `json:"deadline"` // when NetworkManager rolls back unless confirmed
	EndedAt    *time.Time        `json:"ended_at,omitempty"`
	Checkpoint string            `json:"checkpoint,omitempty"`
	BootID     string            `json:"boot_id,omitempty"`
	Previous   map[string]string `json:"previous,omitempty"` // the settings to put back
	// ConfirmedAt is written BEFORE the checkpoint is destroyed: if the box goes down (or /data fails) between
	// destroying the checkpoint and recording "confirmed", the record still says the owner confirmed, and the
	// change is kept when the profile holds it instead of being undone as "lost".
	ConfirmedAt *time.Time `json:"confirmed_at,omitempty"`
}

// Status is GET /v1/network/changes.
type Status struct {
	Available bool    `json:"available"`
	Reason    *string `json:"unavailable_reason"`
	Pending   *Change `json:"pending"`
	Last      *Change `json:"last"` // the most recent finished change
}

// Runner runs a program and returns its standard output.
type Runner interface {
	Run(ctx context.Context, name string, args ...string) ([]byte, error)
}

// ExecRunner is the real thing. An error carries the program's own message.
type ExecRunner struct{}

func (ExecRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	var out, errb bytes.Buffer
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout, cmd.Stderr = &out, &errb
	if err := cmd.Run(); err != nil {
		return out.Bytes(), fmt.Errorf("%s: %w: %s", name, err, strings.TrimSpace(errb.String()))
	}
	return out.Bytes(), nil
}

// Manager applies and confirms changes. One change at a time, box-wide.
type Manager struct {
	Run       Runner
	StatePath string // default DefaultState
	BootID    string
	Now       func() time.Time
	Log       *slog.Logger

	mu sync.Mutex
}

func (m *Manager) now() time.Time {
	if m.Now != nil {
		return m.Now().UTC()
	}
	return time.Now().UTC()
}

func (m *Manager) path() string {
	if m.StatePath != "" {
		return m.StatePath
	}
	return DefaultState
}

func (m *Manager) log() *slog.Logger {
	if m.Log != nil {
		return m.Log
	}
	return slog.Default()
}

// Unavailable says why this box cannot change its network now, or "".
func (m *Manager) Unavailable() string {
	out, err := m.Run.Run(context.Background(), "nmcli", "-t", "-g", "RUNNING", "general")
	if err != nil || strings.TrimSpace(string(out)) != "running" {
		return "NetworkManager is not running on this box"
	}
	return ""
}

func (m *Manager) load() (cur, last *Change) {
	raw, err := os.ReadFile(m.path())
	if err != nil {
		return nil, nil
	}
	var rec struct {
		Current *Change `json:"current"`
		Last    *Change `json:"last"`
	}
	if json.Unmarshal(raw, &rec) != nil {
		return nil, nil
	}
	return rec.Current, rec.Last
}

func (m *Manager) save(cur, last *Change) error {
	raw, _ := json.Marshal(struct {
		Current *Change `json:"current"`
		Last    *Change `json:"last"`
	}{cur, last})
	if err := os.MkdirAll(filepath.Dir(m.path()), 0o700); err != nil {
		return err
	}
	tmp := m.path() + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, m.path())
}

// Status reads the record and settles it against NetworkManager's own list of checkpoints, so a
// rollback that NetworkManager did by itself shows up as rolled_back. It never waits behind an Apply or
// Confirm in progress (those hold the lock for up to about 40 seconds of `nmcli up`): it then answers from
// the record as it stands, and Watch settles it afterwards.
func (m *Manager) Status(ctx context.Context) Status {
	if !m.mu.TryLock() {
		st := Status{Available: true}
		if why := m.Unavailable(); why != "" {
			st.Available, st.Reason = false, &why
		}
		cur, last := m.load()
		if cur != nil && cur.Result == ResultPending {
			st.Pending = view(cur)
		}
		st.Last = view(last)
		return st
	}
	defer m.mu.Unlock()
	return m.statusLocked(ctx)
}

// WatchEvery is how often Watch looks at a change that waits for confirmation.
const WatchEvery = 10 * time.Second

// Watch settles a pending change by itself until ctx ends, so the way back never depends on somebody opening
// the Network screen: when NetworkManager restarted and lost its checkpoint, or when Recover at boot could not
// reach NetworkManager yet, the old settings still come back within about WatchEvery. The host service runs it
// for its whole life. Without a pending change each tick is one small file read.
func (m *Manager) Watch(ctx context.Context, every time.Duration) {
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		if cur, _ := m.load(); cur == nil || cur.Result != ResultPending {
			continue
		}
		m.mu.Lock()
		m.statusLocked(ctx)
		m.mu.Unlock()
	}
}

func (m *Manager) statusLocked(ctx context.Context) Status {
	st := Status{Available: true}
	if why := m.Unavailable(); why != "" {
		st.Available, st.Reason = false, &why
	}
	cur, last := m.load()
	if cur != nil && cur.Result == ResultPending && st.Available {
		listed, err := m.checkpointListed(ctx, cur.Checkpoint)
		if listed || err != nil && m.now().Before(cur.Deadline.Add(5*time.Second)) {
			// Listed: NetworkManager still holds the timer. Unreadable (a D-Bus hiccup) before the deadline: nothing
			// is decided on a failed read, because "gone" would undo a change the owner may be confirming; Watch
			// looks again in a few seconds. After the deadline the change is settled either way (unforced: the
			// saved settings are written only where the profile differs).
			return Status{Available: true, Pending: view(cur), Last: view(last)}
		}
		// Gone. After the deadline NetworkManager rolled back by itself; before it, NetworkManager lost it
		// (a restart), so the settings are put back here.
		done, err := m.resolve(ctx, cur, m.now().Before(cur.Deadline.Add(-2*time.Second)))
		if err != nil {
			// The old settings are NOT back: the change stays pending in the record and is retried by Watch, the
			// next Status, Recover or Apply, instead of being recorded as rolled back while the new profile is in force.
			return Status{Available: true, Pending: view(cur), Last: view(last)}
		}
		last = done
		cur = nil
		_ = m.save(nil, last)
	}
	st.Last = view(last)
	return st
}

// view is what leaves the host service: no checkpoint path, no saved settings.
func view(c *Change) *Change {
	if c == nil {
		return nil
	}
	v := *c
	v.Checkpoint, v.BootID, v.Previous, v.Connection, v.ConfirmedAt = "", "", nil, "", nil
	return &v
}

// resolve ends a pending change whose checkpoint is gone. When the owner had confirmed (ConfirmedAt) and the
// profile still holds the new settings, it is kept: the checkpoint was destroyed by Confirm, not lost. Otherwise
// the saved settings go back (force: also when the profile looks unchanged, because NetworkManager did not
// roll it back itself). An error means nothing is decided yet and the caller keeps the change pending.
func (m *Manager) resolve(ctx context.Context, c *Change, force bool) (*Change, error) {
	if c.ConfirmedAt != nil {
		kept, err := m.holdsNew(ctx, c)
		if err != nil {
			return nil, err
		}
		if kept {
			return m.finish(c, ResultConfirmed), nil
		}
		force = false // NetworkManager rolled back before Confirm destroyed the checkpoint: only check the profile
	}
	if err := m.settle(ctx, c, force); err != nil {
		return nil, err
	}
	return m.finish(c, ResultRolledBack), nil
}

// holdsNew says whether the profile carries the change (rather than the settings that were saved before it).
func (m *Manager) holdsNew(ctx context.Context, c *Change) (bool, error) {
	method, err := m.get(ctx, c.Connection, "ipv4.method")
	if err != nil {
		return false, err
	}
	if c.Mode == "dhcp" {
		return method == "auto", nil
	}
	addrs, err := m.get(ctx, c.Connection, "ipv4.addresses")
	if err != nil {
		return false, err
	}
	return method == "manual" && addrs == c.Address, nil
}

func (m *Manager) finish(c *Change, result string) *Change {
	now := m.now()
	c.Result, c.EndedAt, c.Checkpoint = result, &now, ""
	return c
}

// settle makes sure the profile holds the saved settings again. NetworkManager restores them by itself
// on rollback; this checks, and puts them back (reactivating the connection) only when they differ or
// when force says NetworkManager did not do it. It returns an error when the settings could not be put
// back (for example NetworkManager is not up yet), so the caller keeps the change pending and retries.
func (m *Manager) settle(ctx context.Context, c *Change, force bool) error {
	if len(c.Previous) == 0 {
		return nil
	}
	differ := force
	for _, p := range props {
		if v, err := m.get(ctx, c.Connection, p); err != nil || v != c.Previous[p] {
			differ = true // an unreadable profile is written back rather than trusted
		}
	}
	if !differ {
		return nil
	}
	if err := m.write(ctx, c.Connection, c.Previous); err != nil {
		m.log().Error("network change: the old settings could not be put back", "err", err)
		return err
	}
	if _, err := m.Run.Run(ctx, "nmcli", "--wait", "30", "connection", "up", "uuid", c.Connection, "ifname", c.Interface); err != nil {
		// The profile holds the old settings again; only the live connection did not follow. Not fatal:
		// the record can end, and the next activation (or reboot) picks the profile up.
		m.log().Error("network change: reactivating after the rollback failed", "err", err)
	}
	return nil
}

func (m *Manager) get(ctx context.Context, con, prop string) (string, error) {
	out, err := m.Run.Run(ctx, "nmcli", "-t", "-g", prop, "connection", "show", "uuid", con)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

func (m *Manager) write(ctx context.Context, con string, v map[string]string) error {
	args := []string{"connection", "modify", "uuid", con} // by UUID: a profile named "id", "uuid" or "path" would be misread
	for _, p := range props {
		args = append(args, p, v[p])
	}
	_, err := m.Run.Run(ctx, "nmcli", args...)
	return err
}

// checkpointListed says whether NetworkManager still holds the checkpoint; an error means the list could not be read.
func (m *Manager) checkpointListed(ctx context.Context, cp string) (bool, error) {
	if cp == "" {
		return false, nil
	}
	out, err := m.Run.Run(ctx, "busctl", "--system", "get-property", nmBus, nmPath, nmBus, "Checkpoints")
	if err != nil {
		return false, err
	}
	return strings.Contains(string(out), `"`+cp+`"`), nil
}

// Recover runs when the host service starts. A change that was waiting for confirmation when the box
// went down lost NetworkManager's timer but kept its new profile, so the saved settings go back.
func (m *Manager) Recover(ctx context.Context) {
	m.mu.Lock()
	defer m.mu.Unlock()
	cur, _ := m.load()
	// An empty BootID (it could not be read) never matches, so every host-service restart rolls a pending
	// change back: the safe direction, because the owner can always ask again.
	if cur == nil || cur.Result != ResultPending || (m.BootID != "" && cur.BootID == m.BootID) {
		return // nothing waiting, or this very boot (the host service only restarted: Status settles it)
	}
	m.log().Warn("an unconfirmed network change survived a reboot: putting the old settings back", "interface", cur.Interface)
	done, err := m.resolve(ctx, cur, true)
	if err != nil {
		m.log().Error("network change: not settled at start; Watch retries", "interface", cur.Interface, "err", err)
		return // still pending in the record: Watch retries once NetworkManager answers
	}
	_ = m.save(nil, done)
}

// Apply starts a change: checkpoint, new settings, activation. The returned Status has it pending; the
// owner must Confirm before the deadline or NetworkManager puts the old settings back.
func (m *Manager) Apply(ctx context.Context, iface string, c Config) (Status, error) {
	if err := c.Validate(); err != nil {
		return Status{}, err
	}
	if !ifaceRe.MatchString(iface) {
		return Status{}, refuse("unknown_interface", "that is not an interface name")
	}
	if !actionIDRe.MatchString(c.ActionID) {
		return Status{}, refuse("invalid_action_id", "an approved network action ID is required")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	st := m.statusLocked(ctx)
	if !st.Available {
		return Status{}, refuse("network_unavailable", "%s", *st.Reason)
	}
	if st.Pending != nil {
		return Status{}, refuse("change_pending", "the change to %s is still waiting for confirmation (until %s)", st.Pending.Interface, st.Pending.Deadline.Format(time.RFC3339))
	}
	con, err := m.wiredConnection(ctx, iface)
	if err != nil {
		return Status{}, err
	}
	prev := map[string]string{}
	for _, p := range props {
		v, err := m.get(ctx, con, p)
		if err != nil {
			// Saving an empty value would make a later put-back write `ipv4.method ""`, which fails for ever.
			m.log().Error("network change: the current settings could not be read", "interface", iface, "prop", p, "err", err)
			return Status{}, refuse("network_unavailable", "the current settings of %s could not be read, so nothing was changed", iface)
		}
		prev[p] = v
	}
	devOut, err := m.Run.Run(ctx, "busctl", "--system", "call", nmBus, nmPath, nmBus, "GetDeviceByIpIface", "s", iface)
	dm := devicePathRe.FindSubmatch(devOut)
	if err != nil || dm == nil {
		m.log().Error("network change: NetworkManager does not know the interface", "interface", iface, "err", err, "reply", string(devOut))
		return Status{}, refuse("unknown_interface", "NetworkManager does not know an interface called %s", iface)
	}
	cp, err := m.Run.Run(ctx, "busctl", "--system", "call", nmBus, nmPath, nmBus, "CheckpointCreate", "aouu",
		"1", string(dm[1]), strconv.Itoa(c.RollbackSeconds), checkpointFlags)
	cm := checkpointRe.FindSubmatch(cp)
	if err != nil || cm == nil {
		m.log().Error("network change: NetworkManager would not take a checkpoint", "interface", iface, "err", err, "reply", string(cp))
		return Status{}, refuse("checkpoint_failed", "NetworkManager would not take a checkpoint, so nothing was changed")
	}
	ch := &Change{ActionID: c.ActionID, Interface: iface, Connection: con, Mode: c.Mode, Address: c.Address, Gateway: c.Gateway, DNS: c.DNS,
		Result: ResultPending, StartedAt: m.now(), Checkpoint: string(cm[1]), BootID: m.BootID, Previous: prev}
	ch.Deadline = ch.StartedAt.Add(time.Duration(c.RollbackSeconds) * time.Second)
	// Written before anything changes: a crash from here on is recovered from this record.
	_, last := m.load()
	if err := m.save(ch, last); err != nil {
		_, _ = m.Run.Run(ctx, "busctl", "--system", "call", nmBus, nmPath, nmBus, "CheckpointDestroy", "o", ch.Checkpoint)
		return Status{}, refuse("state_unavailable", "the change record could not be saved (is /data mounted?), so nothing was changed")
	}
	want := map[string]string{"ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "", "ipv4.dns": "", "ipv4.ignore-auto-dns": "no"}
	if c.Mode == "static" {
		want = map[string]string{"ipv4.method": "manual", "ipv4.addresses": c.Address, "ipv4.gateway": c.Gateway,
			"ipv4.dns": strings.Join(c.DNS, ","), "ipv4.ignore-auto-dns": "yes"}
	}
	err = m.write(ctx, con, want)
	if err == nil {
		_, err = m.Run.Run(ctx, "nmcli", "--wait", "40", "connection", "up", "uuid", con, "ifname", iface)
	}
	if err != nil {
		m.log().Error("network change failed; rolling back", "interface", iface, "err", err)
		_, _ = m.Run.Run(ctx, "busctl", "--system", "call", nmBus, nmPath, nmBus, "CheckpointRollback", "o", ch.Checkpoint)
		if m.settle(ctx, ch, false) == nil {
			_ = m.save(nil, m.finish(ch, ResultRolledBack))
			return Status{}, refuse("apply_failed", "NetworkManager could not apply that; the old settings are back")
		}
		// The record stays pending and Watch retries the put-back; NetworkManager's checkpoint ends at the deadline too.
		return Status{}, refuse("apply_failed", "NetworkManager could not apply that, and the old settings are not back yet: "+
			"the box keeps putting them back by itself, at the latest by %s", ch.Deadline.Format(time.RFC3339))
	}
	return Status{Available: true, Pending: view(ch), Last: view(last)}, nil
}

// wiredConnection is the active profile of an ethernet interface, or a Refusal saying why there is none.
func (m *Manager) wiredConnection(ctx context.Context, iface string) (string, error) {
	out, err := m.Run.Run(ctx, "nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CON-UUID", "device", "status")
	if err != nil {
		return "", refuse("network_unavailable", "NetworkManager could not list the interfaces")
	}
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		f := splitTerse(line, 4)
		if len(f) < 4 || f[0] != iface {
			continue
		}
		switch {
		case f[1] != "ethernet":
			return "", refuse("not_wired", "%s is not a wired (ethernet) interface; this changes cables only", iface)
		case f[2] == "unmanaged":
			return "", refuse("unmanaged", "%s is not managed by NetworkManager (the cluster and mesh links are left alone)", iface)
		case f[3] == "" || f[3] == "--":
			return "", refuse("no_connection", "%s has no active connection: plug the cable in and let it connect first", iface)
		}
		return f[3], nil
	}
	return "", refuse("unknown_interface", "this box has no interface called %s", iface)
}

// splitTerse splits nmcli -t output on unescaped colons (a literal colon is written \:).
func splitTerse(s string, n int) []string {
	var out []string
	var cur strings.Builder
	for i := 0; i < len(s); i++ {
		switch {
		case s[i] == '\\' && i+1 < len(s):
			i++
			cur.WriteByte(s[i])
		case s[i] == ':' && len(out) < n-1:
			out = append(out, cur.String())
			cur.Reset()
		default:
			cur.WriteByte(s[i])
		}
	}
	return append(out, cur.String())
}

// Confirm keeps only the pending change for the identified approval.
func (m *Manager) Confirm(ctx context.Context, iface, actionID string) (Status, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	st := m.statusLocked(ctx)
	if st.Pending == nil || st.Pending.Interface != iface {
		return Status{}, refuse("no_pending_change", "no change to %s is waiting for confirmation (it may have rolled back already)", iface)
	}
	cur, last := m.load() // the record, not the view: only the record knows the checkpoint's path
	if cur == nil || cur.Result != ResultPending {
		return Status{}, refuse("no_pending_change", "no change to %s is waiting for confirmation", iface)
	}
	if cur.ActionID == "" || cur.ActionID != actionID {
		return Status{}, refuse("change_mismatch", "the pending change on %s does not match this approval; check the Network page", iface)
	}
	// The owner's confirmation is recorded first, while the checkpoint still exists. If that write fails, nothing
	// is confirmed and the change rolls back at its deadline, which is what the owner is told.
	at := m.now()
	cur.ConfirmedAt = &at
	if err := m.save(cur, last); err != nil {
		m.log().Error("network change: the confirmation could not be recorded", "interface", iface, "err", err)
		return Status{}, refuse("confirm_failed", "the confirmation could not be recorded on the box (is /data full?); the change rolls back at its deadline")
	}
	if out, err := m.Run.Run(ctx, "busctl", "--system", "call", nmBus, nmPath, nmBus, "CheckpointDestroy", "o", cur.Checkpoint); err != nil {
		m.log().Error("network change: NetworkManager would not confirm", "interface", iface, "err", err, "reply", string(out))
		cur.ConfirmedAt = nil
		if err := m.save(cur, last); err != nil {
			// The checkpoint is still listed, so Status keeps the change pending; it rolls back at the deadline. Only
			// if NetworkManager loses the checkpoint before then is ConfirmedAt read, and the change is kept: the
			// owner did attest to reaching the box at its new address.
			m.log().Error("network change: the failed confirmation could not be undone in the record", "err", err)
		}
		return Status{}, refuse("confirm_failed", "NetworkManager would not confirm the change; it will roll back at its deadline")
	}
	last = m.finish(cur, ResultConfirmed)
	if err := m.save(nil, last); err != nil {
		// The record still says pending, with ConfirmedAt: Status and Recover see the checkpoint gone and the new
		// settings in the profile, and record it as confirmed then. Nothing is undone.
		m.log().Error("network change confirmed but not recorded as finished; it is settled later", "err", err)
	}
	return Status{Available: true, Last: view(last)}, nil
}
