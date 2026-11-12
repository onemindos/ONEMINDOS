// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/service"
)

// DefaultConfPath is where `onemind fabric join` writes the node's leaf.conf.
const DefaultConfPath = "/etc/onemind/nats/leaf.conf"

// Monitor watches this machine's local NATS leaf for the heartbeat's
// fabric.leaf_link (contract §12.10). It only reads the loopback monitoring
// endpoint: leaf.conf is written by `onemind fabric join` (onemindd's sandbox
// keeps /etc read-only), and nats-server itself runs in its own unit.
type Monitor struct {
	ConfPath string
	Addr     string
	Interval time.Duration

	mu   sync.Mutex
	last Health
	seen bool
}

// NewMonitor watches the leaf whose config is confPath, monitoring endpoint addr.
func NewMonitor(confPath, addr string) *Monitor {
	return &Monitor{ConfPath: confPath, Addr: addr, Interval: 10 * time.Second}
}

// Last is the most recent health result.
func (m *Monitor) Last() Health {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.last
}

// Link is the heartbeat value: up | down | none (no leaf on this machine, or not checked yet).
func (m *Monitor) Link() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	if !m.seen {
		return "none"
	}
	if m.last.State == StateUp {
		return "up"
	}
	return "down"
}

func (m *Monitor) check(ctx context.Context, hc *http.Client, log *slog.Logger) {
	h := CheckHealth(ctx, hc, m.Addr)
	m.mu.Lock()
	prev := m.last.State
	m.last, m.seen = h, true
	m.mu.Unlock()
	if prev != h.State {
		log.Info("nats leaf", "from", prev, "to", h.State, "err", h.Error)
	}
}

// Service runs the monitor inside onemindd when this machine has a leaf.
func (m *Monitor) Service() service.Service {
	return service.Service{
		Name: "leaf",
		Enabled: func() bool {
			_, err := os.Stat(m.ConfPath)
			return err == nil
		},
		Run: func(ctx context.Context, log *slog.Logger) error {
			hc := &http.Client{Timeout: 3 * time.Second}
			t := time.NewTicker(m.Interval)
			defer t.Stop()
			for {
				m.check(ctx, hc, log)
				select {
				case <-ctx.Done():
					return nil
				case <-t.C:
				}
			}
		},
	}
}
