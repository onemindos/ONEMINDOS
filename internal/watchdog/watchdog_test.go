// SPDX-License-Identifier: Apache-2.0

package watchdog

import (
	"context"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeClock is a manual clock: After channels fire when Advance passes their deadline.
type fakeClock struct {
	mu      sync.Mutex
	now     time.Time
	waiters []waiter
}
type waiter struct {
	at time.Time
	ch chan time.Time
}

func newFake() *fakeClock { return &fakeClock{now: time.Now()} }
func (f *fakeClock) Now() time.Time {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.now
}
func (f *fakeClock) After(d time.Duration) <-chan time.Time {
	f.mu.Lock()
	defer f.mu.Unlock()
	ch := make(chan time.Time, 1)
	f.waiters = append(f.waiters, waiter{f.now.Add(d), ch})
	return ch
}
func (f *fakeClock) pending() int { f.mu.Lock(); defer f.mu.Unlock(); return len(f.waiters) }

// Advance moves time forward in steps no larger than step, firing waiters, and waits for the
// monitor loop to re-arm between steps.
func (f *fakeClock) Advance(d, step time.Duration) {
	for moved := time.Duration(0); moved < d; moved += step {
		for f.pending() == 0 {
			time.Sleep(time.Millisecond)
		}
		f.mu.Lock()
		f.now = f.now.Add(step)
		ws := f.waiters
		f.waiters = nil
		var keep []waiter
		for _, w := range ws {
			if !w.at.After(f.now) {
				w.ch <- f.now
			} else {
				keep = append(keep, w)
			}
		}
		f.waiters = append(f.waiters, keep...)
		f.mu.Unlock()
		time.Sleep(2 * time.Millisecond) // let the monitor goroutine run its Check
	}
}

type recorder struct {
	mu     sync.Mutex
	events []Event
	at     []time.Time
	clock  Clock
}

func (r *recorder) Name() string { return "rec" }
func (r *recorder) Alert(_ context.Context, e Event) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, e)
	r.at = append(r.at, r.clock.Now())
	return nil
}
func (r *recorder) kinds() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	var k []string
	for _, e := range r.events {
		k = append(k, e.Kind)
	}
	return k
}

var testKey = []byte("0123456789abcdef-test-key")

// The acceptance test of #687: the hub heartbeat stops, the internet is off (only loopback UDP
// exists here), and a peer's local alert fires within 2 minutes of the last heartbeat.
func TestHubStopsPeerAlertsWithin2MinutesNoInternet(t *testing.T) {
	clk := newFake()
	peerRec := &recorder{clock: clk}
	pc, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go (&Listener{Key: testKey, Alerters: []Alerter{peerRec}, Clock: clk}).Serve(ctx, pc, nil)

	local := &recorder{clock: clk}
	m := New(Options{Clock: clk, Alerters: []Alerter{local, LANPush{Peers: []string{pc.LocalAddr().String()}, Key: testKey}}})
	go m.Run(ctx)

	// The hub beats every 10 s for 5 minutes: no alert.
	for i := 0; i < 30; i++ {
		m.Heartbeat("hub-1")
		clk.Advance(10*time.Second, 5*time.Second)
	}
	if k := local.kinds(); len(k) != 0 {
		t.Fatalf("false alarm while the hub was beating: %v", k)
	}
	lastBeat := clk.Now()

	// Power pulled: no more heartbeats. Run 2 minutes.
	clk.Advance(2*time.Minute, 5*time.Second)
	waitFor(t, func() bool { return len(peerRec.kinds()) > 0 })

	if k := local.kinds(); len(k) == 0 || k[0] != KindHubDown {
		t.Fatalf("local alert = %v", k)
	}
	peerRec.mu.Lock()
	defer peerRec.mu.Unlock()
	if peerRec.events[0].Kind != KindHubDown || peerRec.events[0].HubID != "hub-1" {
		t.Fatalf("peer event = %+v", peerRec.events[0])
	}
	if lat := peerRec.at[0].Sub(lastBeat); lat > MaxAlertLatency {
		t.Fatalf("peer alerted %v after the last heartbeat, want <= %v", lat, MaxAlertLatency)
	}
}

func waitFor(t *testing.T, ok func() bool) {
	t.Helper()
	for i := 0; i < 500; i++ {
		if ok() {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("condition not met")
}

func TestCheckDownRepeatAndRecovery(t *testing.T) {
	clk := newFake()
	rec := &recorder{clock: clk}
	m := New(Options{Clock: clk, Alerters: []Alerter{rec}})
	ctx := context.Background()
	m.Heartbeat("hub-1")
	clk.mu.Lock()
	clk.now = clk.now.Add(59 * time.Second)
	clk.mu.Unlock()
	m.Check(ctx)
	if len(rec.kinds()) != 0 {
		t.Fatal("alerted before the timeout")
	}
	step := func(d time.Duration) { clk.mu.Lock(); clk.now = clk.now.Add(d); clk.mu.Unlock(); m.Check(ctx) }
	step(2 * time.Second)
	step(30 * time.Second) // within the repeat window: no second alert
	if got := rec.kinds(); len(got) != 1 || got[0] != KindHubDown {
		t.Fatalf("events = %v", got)
	}
	step(31 * time.Second) // repeat reminder
	if got := rec.kinds(); len(got) != 2 || !rec.events[1].Repeat {
		t.Fatalf("no repeat: %v", got)
	}
	m.Heartbeat("hub-1")
	step(time.Second)
	if got := rec.kinds(); got[len(got)-1] != KindHubRecovered || m.Down() {
		t.Fatalf("no recovery: %v", got)
	}
}

func TestHubNeverSeenAlertsAfterTimeout(t *testing.T) {
	clk := newFake()
	rec := &recorder{clock: clk}
	m := New(Options{Clock: clk, Alerters: []Alerter{rec}})
	clk.mu.Lock()
	clk.now = clk.now.Add(61 * time.Second)
	clk.mu.Unlock()
	m.Check(context.Background())
	if got := rec.kinds(); len(got) != 1 || got[0] != KindHubDown {
		t.Fatalf("events = %v", got)
	}
}

func TestListenerRejectsForgedStaleAndMalformed(t *testing.T) {
	clk := newFake()
	l := &Listener{Key: testKey, Clock: clk}
	mk := func(key []byte, at time.Time, kind string) []byte {
		p := packet{V: packetVersion, Kind: kind, HubID: "hub-1", At: at.Unix()}
		p.Sig = p.mac(key)
		b, _ := json.Marshal(p)
		return b
	}
	if _, err := l.Parse(mk(testKey, clk.Now(), KindHubDown)); err != nil {
		t.Fatalf("valid packet rejected: %v", err)
	}
	for name, b := range map[string][]byte{
		"wrong key": mk([]byte("another-key-another-key"), clk.Now(), KindHubDown),
		"stale":     mk(testKey, clk.Now().Add(-time.Hour), KindHubDown),
		"future":    mk(testKey, clk.Now().Add(time.Hour), KindHubDown),
		"bad kind":  mk(testKey, clk.Now(), "siren_off"),
		"garbage":   []byte("not json"),
		"oversize":  []byte(strings.Repeat("x", 2000)),
		"empty":     nil,
		"tampered":  []byte(strings.Replace(string(mk(testKey, clk.Now(), KindHubDown)), "hub-1", "hub-2", 1)),
	} {
		if _, err := l.Parse(b); err == nil {
			t.Errorf("%s accepted", name)
		}
	}
	if _, err := (&Listener{Clock: clk}).Parse(mk(nil, clk.Now(), KindHubDown)); err == nil {
		t.Error("empty key accepted")
	}
}

func TestHookRunsWithFixedEnvironment(t *testing.T) {
	out := filepath.Join(t.TempDir(), "out")
	script := filepath.Join(t.TempDir(), "siren.sh")
	if err := os.WriteFile(script, []byte("#!/bin/sh\necho \"$ONEMIND_WATCHDOG_EVENT $ONEMIND_WATCHDOG_SILENT_S $HOME\" > \""+out+"\"\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	h := Hook{Command: []string{script}}
	if err := h.Alert(context.Background(), Event{Kind: KindHubDown, Silent: 75 * time.Second}); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(out)
	if got := strings.TrimSpace(string(b)); got != "hub_down 75" {
		t.Fatalf("hook saw %q (environment must be fixed, HOME empty)", got)
	}
	if err := (Hook{Command: []string{"/nonexistent/siren"}}).Alert(context.Background(), Event{}); err == nil {
		t.Fatal("failing hook returned nil")
	}
}

func TestLANPushErrorNamesNoPeerAddress(t *testing.T) {
	err := LANPush{Peers: []string{"bad host name:1"}, Key: testKey}.Alert(context.Background(), Event{Kind: KindHubDown, At: time.Now()})
	if err == nil || strings.Contains(err.Error(), "bad host") {
		t.Fatalf("err = %v", err)
	}
	if err := (LANPush{Peers: []string{"127.0.0.1:1"}}).Alert(context.Background(), Event{}); err == nil {
		t.Fatal("no key accepted")
	}
}

// The hub heartbeat comes from the leaf link: "up" feeds the monitor, "down" and "none" do not.
func TestWatchLinkFeedsOnlyWhileUp(t *testing.T) {
	var mu sync.Mutex
	state := "none"
	link := func() string { mu.Lock(); defer mu.Unlock(); return state }
	set := func(v string) { mu.Lock(); state = v; mu.Unlock() }
	beats := make(chan string, 64)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go WatchLink(ctx, link, 5*time.Millisecond, func(id string) {
		select {
		case beats <- id:
		default:
		}
	})
	time.Sleep(60 * time.Millisecond)
	if len(beats) != 0 {
		t.Fatalf("beats while link is none: %d", len(beats))
	}
	set("down")
	time.Sleep(60 * time.Millisecond)
	if len(beats) != 0 {
		t.Fatalf("beats while link is down: %d", len(beats))
	}
	set("up")
	select {
	case id := <-beats:
		if id != HubLinkID {
			t.Fatalf("saw %q", id)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("no beat while link is up")
	}
}

func TestServiceEnabledNeedsJoinedNodeAndConfig(t *testing.T) {
	link := func() string { return "up" }
	if Service(link, func() bool { return true }, "hub").Enabled() {
		t.Fatal("a hub must not watch itself")
	}
	if Service(link, func() bool { return false }, "node").Enabled() {
		t.Fatal("an unjoined node has no hub to watch")
	}
	if Service(nil, func() bool { return true }, "node").Enabled() {
		t.Fatal("no link source, no watchdog")
	}
}

func TestConfigValidation(t *testing.T) {
	write := func(s string) string {
		p := filepath.Join(t.TempDir(), "w.json")
		os.WriteFile(p, []byte(s), 0o600)
		return p
	}
	if c, err := LoadConfig(write(`{"hook":["/bin/true"],"peers":["192.0.2.5"],"key_file":"/k"}`)); err != nil || c.Peers[0] != "192.0.2.5:7481" {
		t.Fatalf("good config: %+v %v", c, err)
	}
	for name, s := range map[string]string{
		"nothing to alert": `{}`,
		"peers no key":     `{"peers":["a:1"]}`,
		"timeout too low":  `{"hook":["/bin/true"],"hub_timeout_s":3}`,
		"unknown field":    `{"hook":["/bin/true"],"shell":"x"}`,
	} {
		if _, err := LoadConfig(write(s)); err == nil {
			t.Errorf("%s accepted", name)
		}
	}
}

func TestNewRaisesTinyTimeout(t *testing.T) {
	if m := New(Options{Timeout: time.Second}); m.Timeout != DefaultTimeout {
		t.Fatalf("timeout %v", m.Timeout)
	}
}

// The default timeout plus the leaf ping budget (internal/leaf) must land the alert within 120 s, and a
// longer configured timeout is refused. Without the leaf ping settings the link took 5m46s to read down.
func TestAlertBudgetIs120SecondsOrLess(t *testing.T) {
	if got := WorstCaseAlertLatency(DefaultTimeout); got > MaxAlertLatency {
		t.Fatalf("default budget %s exceeds %s", got, MaxAlertLatency)
	}
	c := Config{HubTimeoutS: 600, Hook: []string{"/bin/true"}}
	if err := c.validate(); err == nil {
		t.Fatal("a 600 s hub_timeout_s must be refused: the alert would land after the 2 minute target")
	}
	c = Config{HubTimeoutS: int(DefaultTimeout / time.Second), Hook: []string{"/bin/true"}}
	if err := c.validate(); err != nil {
		t.Fatalf("default timeout refused: %v", err)
	}
}

func TestConfigPathFollowsEtcDir(t *testing.T) {
	t.Setenv("ONEMIND_ETC_DIR", "/data/onemind/etc")
	if got := ConfigPath(); got != "/data/onemind/etc/watchdog.json" {
		t.Fatalf("got %s", got)
	}
	t.Setenv("ONEMIND_ETC_DIR", "")
	if got := ConfigPath(); got != "/etc/onemind/watchdog.json" {
		t.Fatalf("default got %s", got)
	}
}
