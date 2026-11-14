// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"errors"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"
)

func TestSaveLoadConfigRoundTrip(t *testing.T) {
	p := filepath.Join(t.TempDir(), "leaf-config.json")
	c := validConfig()
	if changed, err := SaveConfig(p, c); err != nil || !changed {
		t.Fatalf("save: %v %v", changed, err)
	}
	if changed, err := SaveConfig(p, c); err != nil || changed {
		t.Fatalf("second save must be a no-op: %v %v", changed, err)
	}
	got, err := LoadConfig(p)
	if err != nil || got.ServerName != c.ServerName || len(got.HubURLs) != len(c.HubURLs) {
		t.Fatalf("load: %+v %v", got, err)
	}
	bad := validConfig()
	bad.Listen = "0.0.0.0:4222" // H-24: never off the loopback
	if _, err := SaveConfig(p, bad); err == nil {
		t.Fatal("a non-loopback listener must not be saved")
	}
	if err := os.WriteFile(p, []byte(`{"ServerName":"x y"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadConfig(p); err == nil {
		t.Fatal("an invalid persisted config must not load")
	}
}

// fakeLeafz serves /leafz as up or down.
func fakeLeafz(t *testing.T, up *atomic.Bool) string {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if up.Load() {
			_, _ = w.Write([]byte(`{"leafnodes":1,"leafs":[{"name":"hub","rtt":"2ms"}]}`))
		} else {
			_, _ = w.Write([]byte(`{"leafnodes":0,"leafs":[]}`))
		}
	})}
	go func() { _ = srv.Serve(l) }()
	t.Cleanup(func() { _ = srv.Close() })
	return l.Addr().String()
}

// runAsync runs s until the returned stop function is called, and waits for Run to return.
func runAsync(s *Supervisor) (stop func()) {
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { s.Run(ctx); close(done) }()
	return func() { cancel(); <-done }
}

func waitFor(t *testing.T, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatal("condition not reached in 5 s")
		}
		time.Sleep(5 * time.Millisecond)
	}
}

func TestSupervisorLinkAndRestartAfterRepeatedFailures(t *testing.T) {
	var up atomic.Bool
	c := validConfig()
	c.Monitor = fakeLeafz(t, &up)
	var restarts atomic.Int32
	s := &Supervisor{Config: c, ReadOnly: true, Interval: 10 * time.Millisecond, RestartAfter: 3, RestartCooldown: time.Hour,
		Restart: func(context.Context) error { restarts.Add(1); return nil }}
	if s.Link() != "none" {
		t.Fatalf("unchecked supervisor must report none, got %s", s.Link())
	}
	stop := runAsync(s)
	waitFor(t, func() bool { return restarts.Load() >= 1 })
	time.Sleep(80 * time.Millisecond) // many more failed checks: the cooldown holds further restarts back
	stop()
	if s.Link() != "down" {
		t.Fatalf("link %s", s.Link())
	}
	if restarts.Load() != 1 {
		t.Fatalf("restarts = %d, want exactly 1 (cooldown)", restarts.Load())
	}

	up.Store(true)
	c.Monitor = fakeLeafz(t, &up)
	restarts.Store(0)
	s2 := &Supervisor{Config: c, ReadOnly: true, Interval: 10 * time.Millisecond, RestartAfter: 1,
		Restart: func(context.Context) error { restarts.Add(1); return nil }}
	stop2 := runAsync(s2)
	waitFor(t, func() bool { return s2.Link() == "up" })
	time.Sleep(50 * time.Millisecond)
	stop2()
	if s2.Link() != "up" || restarts.Load() != 0 {
		t.Fatalf("healthy leaf: link %s, restarts %d, last %+v", s2.Link(), restarts.Load(), s2.Last())
	}
}

func TestSupervisorRestartErrorDoesNotStopRun(t *testing.T) {
	var up atomic.Bool
	c := validConfig()
	c.Monitor = fakeLeafz(t, &up)
	var calls atomic.Int32
	s := &Supervisor{Config: c, ReadOnly: true, Interval: 5 * time.Millisecond, RestartAfter: 1, RestartCooldown: time.Millisecond,
		Restart: func(context.Context) error { calls.Add(1); return errors.New("no systemd") }}
	stop := runAsync(s)
	waitFor(t, func() bool { return calls.Load() >= 2 })
	stop()
	if calls.Load() < 2 {
		t.Fatalf("a failing restart must be retried after the cooldown, calls=%d", calls.Load())
	}
}

func TestSupervisorReadOnlyDoesNotWriteLeafConf(t *testing.T) {
	dir := t.TempDir()
	conf := filepath.Join(dir, "leaf.conf")
	c := validConfig()
	c.NkeyFile = filepath.Join(dir, "node.nkey.conf")
	c.Monitor = "127.0.0.1:1"
	s := &Supervisor{ConfPath: conf, Config: c, ReadOnly: true, Interval: 5 * time.Millisecond}
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	s.Run(ctx)
	if _, err := os.Stat(conf); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("read-only supervisor wrote leaf.conf: %v", err)
	}
}

func TestSupervisorReloadsWhenPersistedConfigChanges(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "leaf-config.json")
	c := validConfig()
	if _, err := SaveConfig(p, c); err != nil {
		t.Fatal(err)
	}
	var reloads atomic.Int32
	s := NewSupervisor(filepath.Join(dir, "leaf.conf"), p, "", nil)
	if s.Config.ServerName != c.ServerName {
		t.Fatalf("the persisted config is loaded at start: %+v", s.Config)
	}
	s.Reload = func(context.Context) error { reloads.Add(1); return nil }
	s.Restart = nil
	s.Interval = 10 * time.Millisecond
	s.Config.Monitor = "127.0.0.1:1"

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { s.Run(ctx); close(done) }()
	time.Sleep(60 * time.Millisecond)
	if reloads.Load() != 0 {
		t.Fatalf("first load is not a change: reloads=%d", reloads.Load())
	}
	c2 := validConfig()
	c2.MaxFileStore = "512MB"
	if _, err := SaveConfig(p, c2); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for reloads.Load() == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	cancel()
	<-done
	if reloads.Load() != 1 {
		t.Fatalf("reloads = %d, want 1", reloads.Load())
	}
	s.mu.Lock()
	got := s.Config.MaxFileStore
	s.mu.Unlock()
	if got != "512MB" {
		t.Fatalf("new config not adopted: %s", got)
	}
}

func TestNewSupervisorWithoutConfigUsesDefaults(t *testing.T) {
	s := NewSupervisor("/nonexistent/leaf.conf", filepath.Join(t.TempDir(), "none.json"), "", nil)
	if s.Config == nil || !s.ReadOnly || s.Restart == nil || s.Reload == nil {
		t.Fatalf("%+v", s)
	}
	if s.Link() != "none" {
		t.Fatal(s.Link())
	}
}
