// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"fmt"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
)

func jsServer(t *testing.T) string {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	s, err := server.NewServer(&server.Options{Host: "127.0.0.1", Port: port, JetStream: true, StoreDir: t.TempDir(), NoSigs: true, NoLog: true})
	if err != nil {
		t.Fatal(err)
	}
	go s.Start()
	if !s.ReadyForConnections(10 * time.Second) {
		t.Fatal("not ready")
	}
	t.Cleanup(s.Shutdown)
	return fmt.Sprintf("nats://127.0.0.1:%d", port)
}

func runOutbox(t *testing.T, args ...string) (string, error) {
	t.Helper()
	var b bytes.Buffer
	err := fabricOutbox(args, &b)
	return b.String(), err
}

func TestFabricOutboxInitSendStatus(t *testing.T) {
	url := jsServer(t)

	if _, err := runOutbox(t, "send", "events.x", "hi", "--url", url); err == nil || !strings.Contains(err.Error(), "outbox init") {
		t.Fatalf("send before init: %v, want a hint to run init", err)
	}
	if out, err := runOutbox(t, "init", "--url", url, "--max-size", "8"); err != nil || !strings.Contains(out, "ready") {
		t.Fatalf("init: %q %v", out, err)
	}
	if out, err := runOutbox(t, "send", "events.x", "hello", "--id", "e1", "--url", url); err != nil || !strings.Contains(out, "Queued") {
		t.Fatalf("send: %q %v", out, err)
	}
	if out, err := runOutbox(t, "send", "events.x", "hello", "--id", "e1", "--url", url); err != nil || !strings.Contains(out, "Already queued") {
		t.Fatalf("retry: %q %v", out, err)
	}
	out, err := runOutbox(t, "status", "--url", url, "--json")
	if err != nil || !strings.Contains(out, `"messages": 1`) {
		t.Fatalf("status: %q %v", out, err)
	}
}

func TestFabricOutboxErrors(t *testing.T) {
	if _, err := runOutbox(t); err == nil {
		t.Fatal("no args accepted")
	}
	if _, err := runOutbox(t, "bogus", "--url", "nats://127.0.0.1:1"); err == nil {
		t.Fatal("unreachable leaf accepted")
	}
	url := jsServer(t)
	if _, err := runOutbox(t, "send", "only-subject", "--url", url); err == nil {
		t.Fatal("send without text accepted")
	}
}
