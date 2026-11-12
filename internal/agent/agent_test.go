package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"path/filepath"
	"testing"
	"time"

	natsserver "github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
)

func quietLogger() *slog.Logger { return slog.New(slog.NewTextHandler(io.Discard, nil)) }

func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	p := ln.Addr().(*net.TCPAddr).Port
	ln.Close()
	return p
}

func startNATS(t *testing.T, port int) *natsserver.Server {
	t.Helper()
	s, err := natsserver.NewServer(&natsserver.Options{Host: "127.0.0.1", Port: port, NoLog: true, NoSigs: true})
	if err != nil {
		t.Fatal(err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("nats not ready")
	}
	t.Cleanup(s.Shutdown)
	return s
}

func startAgent(t *testing.T, natsURL string) (*Agent, string) {
	t.Helper()
	col := detect.NewFixture(filepath.Join("..", "detect", "testdata", "rpi5"), "arm64")
	a := New(Config{NATSURL: natsURL, Interval: 100 * time.Millisecond, Collector: col, Logger: quietLogger()})
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- a.Serve(ctx, ln) }()
	t.Cleanup(func() {
		cancel()
		select {
		case err := <-done:
			if err != nil {
				t.Errorf("serve: %v", err)
			}
		case <-time.After(5 * time.Second):
			t.Error("agent did not stop")
		}
	})
	return a, "http://" + ln.Addr().String()
}

func getJSON(t *testing.T, url string, v any) {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 || resp.Header.Get("Content-Type") != "application/json" {
		t.Fatalf("%s: %d %s", url, resp.StatusCode, resp.Header.Get("Content-Type"))
	}
	if err := json.NewDecoder(resp.Body).Decode(v); err != nil {
		t.Fatal(err)
	}
}

func TestLocalAPI(t *testing.T) {
	_, base := startAgent(t, "")
	var st heartbeat.Status
	getJSON(t, base+"/api/v1/node", &st)
	if st.Schema != heartbeat.Schema || st.Board != heartbeat.BoardRPi5 || len(st.NodeID) != 12 {
		t.Fatalf("node = %+v", st)
	}
	var h map[string]any
	getJSON(t, base+"/healthz", &h)
	if h["ok"] != true || h["boot_id"] != "b0000000-0000-4000-8000-000000000001" || h["nats_connected"] != false {
		t.Fatalf("healthz = %v", h)
	}
	resp, err := http.Post(base+"/api/v1/node", "application/json", nil)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("POST status = %d, want 405", resp.StatusCode)
	}
}

// TestRetriesUntilNATSUp starts the agent while NATS is down, checks that
// the API still works, then starts NATS and expects heartbeats to arrive.
func TestRetriesUntilNATSUp(t *testing.T) {
	port := freePort(t)
	url := fmt.Sprintf("nats://127.0.0.1:%d", port)
	a, base := startAgent(t, url)

	time.Sleep(300 * time.Millisecond)
	var st heartbeat.Status
	getJSON(t, base+"/api/v1/node", &st) // API alive while hub is down
	if a.Sent() != 0 {
		t.Fatalf("sent %d heartbeats with NATS down", a.Sent())
	}

	startNATS(t, port)
	sub, err := nats.Connect(url)
	if err != nil {
		t.Fatal(err)
	}
	defer sub.Close()
	ch := make(chan *nats.Msg, 8)
	if _, err := sub.ChanSubscribe("onemind.node.*.status", ch); err != nil {
		t.Fatal(err)
	}
	select {
	case m := <-ch:
		var got heartbeat.Status
		if err := json.Unmarshal(m.Data, &got); err != nil {
			t.Fatal(err)
		}
		if m.Subject != heartbeat.Subject(got.NodeID) || got.NodeID != st.NodeID {
			t.Fatalf("subject %q for node %q", m.Subject, got.NodeID)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("no heartbeat after NATS came up")
	}
	var h map[string]any
	getJSON(t, base+"/healthz", &h)
	if h["nats_connected"] != true {
		t.Fatalf("healthz = %v", h)
	}
}

// TestSurvivesHubRestart stops NATS after the first heartbeat, then starts
// it again and expects the agent to reconnect and publish again.
func TestSurvivesHubRestart(t *testing.T) {
	port := freePort(t)
	url := fmt.Sprintf("nats://127.0.0.1:%d", port)
	srv := startNATS(t, port)
	a, base := startAgent(t, url)
	waitFor(t, func() bool { return a.Sent() > 0 }, "first heartbeat")

	srv.Shutdown()
	srv.WaitForShutdown()
	time.Sleep(300 * time.Millisecond)
	var h map[string]any
	getJSON(t, base+"/healthz", &h) // API alive while hub is gone
	if h["nats_connected"] != false {
		t.Fatalf("healthz = %v", h)
	}
	before := a.Sent()

	startNATS(t, port)
	waitFor(t, func() bool { return a.Sent() > before }, "heartbeat after hub restart")
}

func waitFor(t *testing.T, cond func() bool, what string) {
	t.Helper()
	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", what)
}
