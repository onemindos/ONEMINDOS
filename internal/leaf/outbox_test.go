// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

func connectJS(t *testing.T, url string) jetstream.JetStream {
	t.Helper()
	nc, err := nats.Connect(url, nats.Timeout(5*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)
	js, err := jetstream.New(nc)
	if err != nil {
		t.Fatal(err)
	}
	return js
}

type outboxLab struct {
	dir                string
	hubClient, hubLeaf int
	leafClient         int
	hub, leaf          *server.Server
	hubConf            string
}

func (l *outboxLab) startHub(t *testing.T) {
	t.Helper()
	l.hub = startServer(t, l.hubConf)
}

func newOutboxLab(t *testing.T) *outboxLab {
	t.Helper()
	l := &outboxLab{dir: t.TempDir(), hubClient: freePort(t), hubLeaf: freePort(t), leafClient: freePort(t)}
	l.hubConf = filepath.Join(l.dir, "hub.conf")
	hub := fmt.Sprintf(`server_name: hub
listen: "127.0.0.1:%d"
jetstream { store_dir: %q, domain: "hub" }
leafnodes { listen: "127.0.0.1:%d" }
`, l.hubClient, filepath.Join(l.dir, "hub-store"), l.hubLeaf)
	if err := os.WriteFile(l.hubConf, []byte(hub), 0o600); err != nil {
		t.Fatal(err)
	}
	l.startHub(t)
	// The leaf config is the one a node renders, minus TLS (covered by the tests in leaf_test.go).
	leafConf := filepath.Join(l.dir, "leaf.conf")
	leaf := fmt.Sprintf(`server_name: node-n1
listen: "127.0.0.1:%d"
jetstream { store_dir: %q, domain: "node-n1", max_file_store: 256MB }
leafnodes { remotes: [ { urls: ["nats-leaf://127.0.0.1:%d"] } ] }
`, l.leafClient, filepath.Join(l.dir, "leaf-store"), l.hubLeaf)
	if err := os.WriteFile(leafConf, []byte(leaf), 0o600); err != nil {
		t.Fatal(err)
	}
	l.leaf = startServer(t, leafConf)
	return l
}

func (l *outboxLab) leafURL() string { return fmt.Sprintf("nats://127.0.0.1:%d", l.leafClient) }
func (l *outboxLab) hubURL() string  { return fmt.Sprintf("nats://127.0.0.1:%d", l.hubClient) }

// Lab test of #170: a leaf buffers through a hub outage and the hub ends up with every message
// exactly once, including one the producer retried.
func TestOutboxDeliversEveryMessageOnceThroughHubOutage(t *testing.T) {
	l := newOutboxLab(t)
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	leafJS := connectJS(t, l.leafURL())
	if err := EnsureOutbox(ctx, leafJS, OutboxConfig{}); err != nil {
		t.Fatal(err)
	}
	hubJS := connectJS(t, l.hubURL())
	src, err := HubSourceStream("node-n1")
	if err != nil {
		t.Fatal(err)
	}
	// Wait until the leaf link is up, then let the hub start collecting.
	waitUntil(t, 20*time.Second, "leaf link", func() bool {
		_, err := hubJS.CreateOrUpdateStream(ctx, src)
		return err == nil
	})

	send := func(from, to int) {
		for i := from; i < to; i++ {
			if _, err := Enqueue(ctx, leafJS, "events.sensor", []byte(fmt.Sprint(i)), fmt.Sprintf("m-%03d", i)); err != nil {
				t.Fatalf("enqueue %d: %v", i, err)
			}
		}
	}
	hubCount := func() uint64 {
		s, err := hubJS.Stream(ctx, src.Name)
		if err != nil {
			return 0
		}
		info, err := s.Info(ctx)
		if err != nil {
			return 0
		}
		return info.State.Msgs
	}

	send(0, 10)
	waitUntil(t, 20*time.Second, "first batch at the hub", func() bool { return hubCount() == 10 })

	// Hub outage: stop it, keep producing on the leaf.
	hubJS = nil
	l.hub.Shutdown()
	l.hub.WaitForShutdown()
	send(10, 30)
	if dup, err := Enqueue(ctx, leafJS, "events.sensor", []byte("10"), "m-010"); err != nil || !dup {
		t.Fatalf("retry of m-010: duplicate=%v err=%v, want duplicate", dup, err)
	}
	st, err := Status(ctx, leafJS)
	if err != nil || st.Messages != 30 {
		t.Fatalf("outbox during outage: %+v err=%v, want 30 messages buffered", st, err)
	}

	// Hub returns (same ports, same store): the backlog arrives once.
	l.startHub(t)
	hubJS = connectJS(t, l.hubURL())
	waitUntil(t, 60*time.Second, "backlog at the hub", func() bool {
		s, err := hubJS.Stream(ctx, src.Name)
		if err != nil {
			return false
		}
		info, err := s.Info(ctx)
		return err == nil && info.State.Msgs >= 30
	})
	time.Sleep(2 * time.Second) // a duplicate, if any, would show up now

	s, err := hubJS.Stream(ctx, src.Name)
	if err != nil {
		t.Fatal(err)
	}
	cons, err := s.CreateOrUpdateConsumer(ctx, jetstream.ConsumerConfig{AckPolicy: jetstream.AckNonePolicy})
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]int{}
	info, _ := s.Info(ctx)
	batch, err := cons.FetchNoWait(int(info.State.Msgs))
	if err != nil {
		t.Fatal(err)
	}
	for m := range batch.Messages() {
		seen[string(m.Data())]++
	}
	if len(seen) != 30 || info.State.Msgs != 30 {
		t.Fatalf("hub has %d messages, %d distinct, want 30 and 30", info.State.Msgs, len(seen))
	}
	for i := 0; i < 30; i++ {
		if seen[fmt.Sprint(i)] != 1 {
			t.Fatalf("message %d delivered %d times", i, seen[fmt.Sprint(i)])
		}
	}
}

func TestOutboxRefusesWhenFullInsteadOfDropping(t *testing.T) {
	l := newOutboxLab(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	js := connectJS(t, l.leafURL())
	if err := EnsureOutbox(ctx, js, OutboxConfig{MaxBytes: 4096}); err != nil {
		t.Fatal(err)
	}
	payload := make([]byte, 1024)
	var stored int
	var lastErr error
	for i := 0; i < 20; i++ {
		if _, lastErr = Enqueue(ctx, js, "events.big", payload, fmt.Sprintf("b-%d", i)); lastErr != nil {
			break
		}
		stored++
	}
	if lastErr == nil || stored == 0 || stored >= 20 {
		t.Fatalf("stored %d, last error %v: want a refusal after a few", stored, lastErr)
	}
	st, _ := Status(ctx, js)
	if int(st.Messages) != stored {
		t.Fatalf("outbox holds %d, enqueue accepted %d: an unread message was dropped", st.Messages, stored)
	}
}

func TestEnqueueRejectsBadInput(t *testing.T) {
	for _, c := range []struct{ suffix, id string }{
		{"events.x", ""}, {"events.x", "has space"}, {"", "id"}, {"ev.*", "id"}, {"ev.>", "id"}, {".ev", "id"}, {"ev..x", "id"},
	} {
		if _, err := Enqueue(context.Background(), nil, c.suffix, nil, c.id); err == nil {
			t.Errorf("Enqueue(%q,%q) accepted", c.suffix, c.id)
		}
	}
}

func TestHubSourceStream(t *testing.T) {
	cfg, err := HubSourceStream("node-n1")
	if err != nil || cfg.Name != "NODE_node_n1_OUTBOX" || cfg.Sources[0].External.APIPrefix != "$JS.node-n1.API" {
		t.Fatalf("%+v %v", cfg, err)
	}
	for _, bad := range []string{"", "hub", "a b", "x.y"} {
		if _, err := HubSourceStream(bad); err == nil {
			t.Errorf("domain %q accepted", bad)
		}
	}
}

func waitUntil(t *testing.T, d time.Duration, what string, ok func() bool) {
	t.Helper()
	end := time.Now().Add(d)
	for time.Now().Before(end) {
		if ok() {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", what)
}
