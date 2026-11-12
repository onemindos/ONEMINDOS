// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os/exec"
	"sync"
	"time"
)

// Leaf states for the heartbeat and the Network page (§12).
const (
	StateUp   = "up"   // the local server has a leaf connection to the hub
	StateDown = "down" // the local server answers but has no hub connection
	// StateNoServer: the local nats-server does not answer at all.
	StateNoServer = "no_server"
)

// Health is the leaf's state as its own server reports it on /leafz.
type Health struct {
	State string `json:"state"`
	// RTT to the hub as nats-server measures it, e.g. "12.3ms".
	RTT       string `json:"rtt,omitempty"`
	CheckedAt string `json:"checked_at"`
	Error     string `json:"error,omitempty"`
}

// leafz is the subset of nats-server's /leafz response (server.Leafz).
type leafz struct {
	NumLeafs int `json:"leafnodes"`
	Leafs    []struct {
		Name string `json:"name"`
		RTT  string `json:"rtt"`
	} `json:"leafs"`
}

// CheckHealth asks the local server's monitoring endpoint (loopback) whether
// its leaf connection to the hub is up.
func CheckHealth(ctx context.Context, hc *http.Client, monitor string) Health {
	h := Health{State: StateNoServer, CheckedAt: time.Now().UTC().Format(time.RFC3339)}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://"+monitor+"/leafz", nil)
	if err != nil {
		h.Error = err.Error()
		return h
	}
	resp, err := hc.Do(req)
	if err != nil {
		h.Error = err.Error()
		return h
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		h.Error = fmt.Sprintf("leafz: HTTP %d", resp.StatusCode)
		return h
	}
	var lz leafz
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&lz); err != nil {
		h.Error = "leafz: " + err.Error()
		return h
	}
	h.State = StateDown
	if lz.NumLeafs > 0 && len(lz.Leafs) > 0 {
		h.State = StateUp
		h.RTT = lz.Leafs[0].RTT
	}
	return h
}

// Reloader makes the running nats-server re-read leaf.conf.
type Reloader func(ctx context.Context) error

// SystemdReload reloads the leaf unit (onemind-nats-leaf.service, §18; its
// ExecReload is `nats-server --signal reload`).
func SystemdReload(unit string) Reloader {
	return func(ctx context.Context) error {
		out, err := exec.CommandContext(ctx, "systemctl", "reload", unit).CombinedOutput()
		if err != nil {
			return fmt.Errorf("systemctl reload %s: %w: %s", unit, err, out)
		}
		return nil
	}
}

// Supervisor keeps leaf.conf equal to Config and tracks leaf health.
type Supervisor struct {
	ConfPath string
	Config   *Config
	Reload   Reloader
	Interval time.Duration // health check period; default 10 s (the heartbeat period)
	Log      *slog.Logger
	HTTP     *http.Client

	mu   sync.Mutex
	last Health
}

// Sync writes the config if it changed and reloads the server when it did.
func (s *Supervisor) Sync(ctx context.Context) (bool, error) {
	changed, err := Apply(s.ConfPath, s.Config)
	if err != nil {
		return false, err
	}
	if changed && s.Reload != nil {
		if err := s.Reload(ctx); err != nil {
			return true, err
		}
	}
	if changed && s.Log != nil {
		s.Log.Info("nats leaf config updated", "path", s.ConfPath)
	}
	return changed, nil
}

// Check runs one health check and stores the result.
func (s *Supervisor) Check(ctx context.Context) Health {
	hc := s.HTTP
	if hc == nil {
		hc = &http.Client{Timeout: 3 * time.Second}
	}
	d := s.Config.withDefaults()
	h := CheckHealth(ctx, hc, d.Monitor)
	s.mu.Lock()
	prev := s.last.State
	s.last = h
	s.mu.Unlock()
	if s.Log != nil && prev != h.State {
		s.Log.Info("nats leaf state", "from", prev, "to", h.State, "err", h.Error)
	}
	return h
}

// Last returns the most recent health result (for the heartbeat).
func (s *Supervisor) Last() Health {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.last
}

// Run syncs the config once, then checks health every Interval until ctx ends.
// A failed sync is logged and retried each round: the agent must not die
// because the leaf is broken (agent package design rule).
func (s *Supervisor) Run(ctx context.Context) {
	iv := s.Interval
	if iv <= 0 {
		iv = 10 * time.Second
	}
	t := time.NewTicker(iv)
	defer t.Stop()
	synced := false
	for {
		if !synced {
			if _, err := s.Sync(ctx); err != nil {
				if s.Log != nil {
					s.Log.Warn("nats leaf config", "err", err)
				}
			} else {
				synced = true
			}
		}
		s.Check(ctx)
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}
