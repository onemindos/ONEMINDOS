// SPDX-License-Identifier: Apache-2.0

// Package watchdog is the node-side hub watcher (issue #687, notifications off-grid channels).
// Every machine that runs onemindd can watch the hub's heartbeat (contract §2, subject
// onemind.node.<id>.status, role "hub"). When the hub has been silent for longer than the
// timeout the watchdog alerts locally and pushes the alert to its peers over the LAN, with no
// internet and no cloud service involved.
//
// Two channels, both local:
//
//   - a local hook: an operator-configured program (siren relay, speaker script) run with no
//     shell and a fixed environment;
//   - a LAN push: one HMAC-signed UDP datagram to each configured peer (phone bridge, speaker,
//     another node). The peer's Listener verifies it and runs its own hook.
//
// The watchdog only observes and alerts. It never actuates anything on the hub, and the alert
// carries no address, secret or user data: just the hub's node id, the silence length and a time.
package watchdog

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// Event kinds.
const (
	KindHubDown      = "hub_down"
	KindHubRecovered = "hub_recovered"
)

// Defaults. A node publishes every 10 s (agent.DefaultInterval), so 60 s is six missed beats;
// with the 5 s check step the alert lands within about 65 s, inside the 2 minute target.
const (
	DefaultTimeout       = 60 * time.Second
	DefaultCheckEvery    = 5 * time.Second
	DefaultRepeatEvery   = 60 * time.Second
	MaxAlertLatency      = 2 * time.Minute
	minTimeout           = 15 * time.Second
	defaultRepeatMinimum = 10 * time.Second
)

// Clock is time as the monitor sees it; tests drive a fake one.
type Clock interface {
	Now() time.Time
	// After returns a channel that receives once d has passed.
	After(d time.Duration) <-chan time.Time
}

type realClock struct{}

func (realClock) Now() time.Time                         { return time.Now() }
func (realClock) After(d time.Duration) <-chan time.Time { return time.After(d) }

// RealClock is the wall clock.
var RealClock Clock = realClock{}

// Event is what an Alerter receives.
type Event struct {
	Kind   string        `json:"kind"`
	HubID  string        `json:"hub_id"`
	Silent time.Duration `json:"silent_ns"` // how long the hub has been silent (0 on recovery)
	At     time.Time     `json:"at"`
	Repeat bool          `json:"repeat"` // a reminder while the hub is still down
}

// Alerter delivers an event over one channel. Errors are logged, never fatal: one failing
// channel must not stop the others.
type Alerter interface {
	Name() string
	Alert(ctx context.Context, e Event) error
}

// Options configure a Monitor; every zero field takes its default.
type Options struct {
	Clock       Clock
	Timeout     time.Duration
	CheckEvery  time.Duration
	RepeatEvery time.Duration
	Alerters    []Alerter
	Log         *slog.Logger
}

// Monitor tracks the last time the hub was heard and fires events.
type Monitor struct {
	Options

	mu       sync.Mutex
	hubID    string
	lastSeen time.Time
	started  time.Time
	down     bool
	lastSent time.Time
}

// New returns a Monitor with defaults for every zero field. A Timeout below the floor is raised
// to the default so a jittery LAN cannot cause false alarms.
func New(o Options) *Monitor {
	if o.Clock == nil {
		o.Clock = RealClock
	}
	if o.Timeout < minTimeout {
		o.Timeout = DefaultTimeout
	}
	if o.CheckEvery <= 0 {
		o.CheckEvery = DefaultCheckEvery
	}
	if o.RepeatEvery < defaultRepeatMinimum {
		o.RepeatEvery = DefaultRepeatEvery
	}
	if o.Log == nil {
		o.Log = slog.Default()
	}
	return &Monitor{Options: o, started: o.Clock.Now()}
}

// Heartbeat records that the hub just published a heartbeat. hubID is its node id. A heartbeat
// after an outage ends it on the next check.
func (m *Monitor) Heartbeat(hubID string) {
	m.mu.Lock()
	m.hubID = hubID
	m.lastSeen = m.Clock.Now()
	m.mu.Unlock()
}

// Down reports whether the monitor currently considers the hub down.
func (m *Monitor) Down() bool { m.mu.Lock(); defer m.mu.Unlock(); return m.down }

// Check compares the clock to the last heartbeat and fires events. It is called every CheckEvery
// by Run and directly by tests. Before the first heartbeat the silence is measured from start,
// so a hub that never appears also alerts (hub id empty).
func (m *Monitor) Check(ctx context.Context) {
	m.mu.Lock()
	now := m.Clock.Now()
	ref := m.lastSeen
	if ref.IsZero() {
		ref = m.started
	}
	silent := now.Sub(ref)
	var ev *Event
	switch {
	case silent >= m.Timeout && !m.down:
		m.down, m.lastSent = true, now
		ev = &Event{Kind: KindHubDown, HubID: m.hubID, Silent: silent, At: now}
	case silent >= m.Timeout && m.down && now.Sub(m.lastSent) >= m.RepeatEvery:
		m.lastSent = now
		ev = &Event{Kind: KindHubDown, HubID: m.hubID, Silent: silent, At: now, Repeat: true}
	case silent < m.Timeout && m.down:
		m.down = false
		ev = &Event{Kind: KindHubRecovered, HubID: m.hubID, At: now}
	}
	m.mu.Unlock()
	if ev != nil {
		m.fire(ctx, *ev)
	}
}

func (m *Monitor) fire(ctx context.Context, e Event) {
	m.Log.Warn("hub watchdog", "kind", e.Kind, "hub", e.HubID, "silent", e.Silent.Round(time.Second), "repeat", e.Repeat)
	for _, a := range m.Alerters {
		if err := a.Alert(ctx, e); err != nil {
			m.Log.Error("watchdog channel failed", "channel", a.Name(), "err", err)
		}
	}
}

// Run checks every CheckEvery until ctx ends.
func (m *Monitor) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		case <-m.Clock.After(m.CheckEvery):
			m.Check(ctx)
		}
	}
}
