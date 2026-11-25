package agent

import (
	"bytes"
	"context"
	"encoding/json"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	natsserver "github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/leaf"
)

// startLeaf runs a JetStream-enabled NATS server standing in for the node's local leaf.
func startLeaf(t *testing.T) (string, jetstream.JetStream) {
	t.Helper()
	port := freePort(t)
	s, err := natsserver.NewServer(&natsserver.Options{Host: "127.0.0.1", Port: port, NoLog: true, NoSigs: true,
		JetStream: true, StoreDir: t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("nats not ready")
	}
	t.Cleanup(s.Shutdown)
	url := s.ClientURL()
	nc, err := nats.Connect(url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)
	js, err := jetstream.New(nc)
	if err != nil {
		t.Fatal(err)
	}
	return url, js
}

func startDurable(t *testing.T, url string, durable bool) string {
	t.Helper()
	col := detect.NewFixture(filepath.Join("..", "detect", "testdata", "rpi5"), "arm64")
	a := New(Config{NATSURL: url, Interval: time.Hour, Durable: durable, RecordEvery: 300 * time.Millisecond,
		Collector: col, Logger: quietLogger()})
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- a.Serve(ctx, ln) }()
	t.Cleanup(func() { cancel(); <-done })
	return "http://" + ln.Addr().String()
}

func postEvent(t *testing.T, base, body string) (int, map[string]string) {
	t.Helper()
	resp, err := http.Post(base+"/api/v1/events", "application/json", bytes.NewBufferString(body))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]string
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return resp.StatusCode, out
}

func TestDurableEventsLandInOutbox(t *testing.T) {
	url, js := startLeaf(t)
	base := startDurable(t, url, true)
	// The record loop creates the outbox; wait for it and for the first heartbeat of record.
	waitFor(t, func() bool {
		st, err := leaf.Status(context.Background(), js)
		return err == nil && st.Messages >= 1
	}, "heartbeat of record in the outbox")

	code, out := postEvent(t, base, `{"kind":"disk.replaced","data":{"slot":2}}`)
	if code != http.StatusAccepted || out["id"] == "" {
		t.Fatalf("post: %d %v", code, out)
	}
	cons, err := js.CreateOrUpdateConsumer(context.Background(), leaf.OutboxStream, jetstream.ConsumerConfig{
		FilterSubject: "outbox.events.disk.replaced", AckPolicy: jetstream.AckExplicitPolicy})
	if err != nil {
		t.Fatal(err)
	}
	msg, err := cons.Next(jetstream.FetchMaxWait(3 * time.Second))
	if err != nil {
		t.Fatal(err)
	}
	var ev Event
	if err := json.Unmarshal(msg.Data(), &ev); err != nil {
		t.Fatal(err)
	}
	if ev.Schema != EventSchema || ev.ID != out["id"] || ev.Kind != "disk.replaced" || ev.NodeID == "" || string(ev.Data) != `{"slot":2}` {
		t.Fatalf("event: %+v", ev)
	}
	// A heartbeat of record carries the status object.
	hb, err := js.CreateOrUpdateConsumer(context.Background(), leaf.OutboxStream, jetstream.ConsumerConfig{
		FilterSubject: "outbox.events.heartbeat", AckPolicy: jetstream.AckExplicitPolicy})
	if err != nil {
		t.Fatal(err)
	}
	m, err := hb.Next(jetstream.FetchMaxWait(3 * time.Second))
	if err != nil {
		t.Fatal(err)
	}
	var rec Event
	_ = json.Unmarshal(m.Data(), &rec)
	if rec.Kind != "heartbeat" || !bytes.Contains(rec.Data, []byte(`"schema":"onemind.node.status/v1"`)) {
		t.Fatalf("record: %s", m.Data())
	}
}

func TestEventsRejectedWhenNotDurableOrBad(t *testing.T) {
	url, _ := startLeaf(t)
	if code, _ := postEvent(t, startDurable(t, url, false), `{"kind":"x"}`); code != http.StatusNotFound {
		t.Fatalf("not durable: want 404, got %d", code)
	}
	base := startDurable(t, url, true)
	for _, body := range []string{`{"kind":"Bad Kind"}`, `{"kind":"a..b"}`, `{"kind":"ok","data":`, `not json`} {
		if code, _ := postEvent(t, base, body); code != http.StatusBadRequest {
			t.Errorf("%s: want 400, got %d", body, code)
		}
	}
}

// G1: onemindd on a joined machine signs in to a leaf that has no passwordless user. Its own
// publish and subscribe list (leaf.MachinePrograms) must be enough for everything onemindd does:
// heartbeats, the outbox it creates, the events it stores and the departure on a clean stop.
func TestAgentRunsAgainstALeafWithLocalSignIn(t *testing.T) {
	dir := t.TempDir()
	keys := filepath.Join(dir, "nats-local")
	pubs := map[string]string{}
	for _, n := range []string{leaf.ProgramOnemindd, leaf.ProgramCLI} {
		p, err := leaf.WriteLocalSeed(keys, n)
		if err != nil {
			t.Fatal(err)
		}
		pubs[n] = p
	}
	col := detect.NewFixture(filepath.Join("..", "detect", "testdata", "rpi5"), "arm64")
	progs, err := leaf.MachinePrograms(col.ID(), pubs)
	if err != nil {
		t.Fatal(err)
	}
	auth, err := leaf.RenderLocalAuth(progs)
	if err != nil {
		t.Fatal(err)
	}
	port := freePort(t)
	conf := filepath.Join(dir, "leaf.conf")
	body := "listen: \"127.0.0.1:" + strconv.Itoa(port) + "\"\njetstream { store_dir: \"" + filepath.Join(dir, "js") +
		"\", max_file_store: 256MB, max_memory_store: 0 }\n" + string(auth)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	opts, err := natsserver.ProcessConfigFile(conf)
	if err != nil {
		t.Fatal(err)
	}
	opts.NoLog, opts.NoSigs = true, true
	s, err := natsserver.NewServer(opts)
	if err != nil {
		t.Fatal(err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("nats not ready")
	}
	t.Cleanup(s.Shutdown)
	url := "nats://127.0.0.1:" + strconv.Itoa(port)

	if nc, err := nats.Connect(url); err == nil {
		nc.Close()
		t.Fatal("the leaf accepted a client with no key")
	}
	// Watch the machine's status subject as the CLI's key would not be allowed to: use onemindd's
	// own subscribe right (its own status), which is what node-check.sh does.
	opt, err := leaf.ClientOptions(leaf.ProgramOnemindd, filepath.Join(keys, "onemindd.nk"))
	if err != nil {
		t.Fatal(err)
	}
	watch, err := nats.Connect(url, opt...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(watch.Close)
	hb := make(chan *nats.Msg, 1024)
	sub, err := watch.ChanSubscribe("onemind.node."+col.ID()+".status", hb)
	if err != nil {
		t.Fatal(err)
	}
	_ = sub.SetPendingLimits(4096, 4<<20)
	watch.Flush()

	a := New(Config{NATSURL: url, NATSNkeySeed: filepath.Join(keys, "onemindd.nk"), NATSInboxPrefix: leaf.InboxPrefix(leaf.ProgramOnemindd),
		Interval: time.Second, Durable: true, RecordEvery: 300 * time.Millisecond, Collector: col, Logger: quietLogger()})
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- a.Serve(ctx, ln) }()
	base := "http://" + ln.Addr().String()

	select {
	case <-hb:
	case <-time.After(10 * time.Second):
		t.Fatal("no heartbeat came through the authenticated leaf")
	}
	// The outbox: created by the record loop, then an event is stored through the HTTP API.
	waitFor(t, func() bool {
		code, _ := postEvent(t, base, `{"kind":"sensor.reading","data":{"v":1}}`)
		return code == http.StatusAccepted
	}, "an event stored in the outbox through the authenticated leaf")
	cancel()
	<-done
	// The clean stop publishes the departure on the same status subject.
	var sawDeparture bool
	for len(hb) > 0 {
		if bytes.Contains((<-hb).Data, []byte("departure")) {
			sawDeparture = true
		}
	}
	if !sawDeparture {
		t.Error("the departure did not come through the authenticated leaf")
	}
}
