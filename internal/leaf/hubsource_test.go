// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// Hub sourcing across the per-node accounts (#747). The hub runs the accounts file the gateway
// renders with JetStream on (testdata/hub-accounts-jetstream.golden.conf, checked byte for byte by
// core/tests/test_hub_sourcing.py); two real nats-server leaves join it as nodes aaa111 and bbb222,
// each with its own JetStream domain and outbox. The hub's ONEMIND account keeps a copy of each
// outbox in the stream the gateway creates on join approval (testdata/hub-source-stream.golden.json,
// rendered by core/onemind_core/jetstream.py hub_source).
//
// The leaf link is cut with a TCP relay between leaf and hub, so the leaf keeps running and keeps
// accepting writes while it cannot reach the hub. ONEMIND_LAB_CUT sets how long (default 20s; the
// acceptance run of #747 uses 10m, with `go test -timeout 30m`).

// hubSourceFor is the stream the gateway creates for a node: HubSourceStream plus the node's own
// delivery prefix, the one subject tree NODE_<id> exports for delivery (natsconf.py).
func hubSourceFor(t *testing.T, nodeID string) jetstream.StreamConfig {
	t.Helper()
	cfg, err := HubSourceStream("node-" + nodeID)
	if err != nil {
		t.Fatal(err)
	}
	cfg.Sources[0].External.DeliverPrefix = "onemind.node." + nodeID + ".outbox"
	return cfg
}

func TestHubSourceStreamMatchesTheGateway(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("testdata", "hub-source-stream.golden.json"))
	if err != nil {
		t.Fatal(err)
	}
	var got jetstream.StreamConfig
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatal(err)
	}
	if want := hubSourceFor(t, "aaa111"); !reflect.DeepEqual(got, want) {
		t.Fatalf("the gateway's hub source stream differs from HubSourceStream:\n got %+v %+v\nwant %+v %+v",
			got, *got.Sources[0].External, want, *want.Sources[0].External)
	}
}

// cutRelay forwards TCP from a fixed local port to the hub's leaf port until it is cut. A cut
// relay keeps listening and closes every new connection at once, so the leaf keeps redialling and
// is refused, and the port never goes free for another process to take while the link is down.
// A blackholed relay keeps the connections open but drops every byte, as a link that dies silently.
type cutRelay struct {
	addr   string
	target string
	mu     sync.Mutex
	up     bool
	conns  map[net.Conn]struct{}
	hole   atomic.Bool
}

func newCutRelay(t *testing.T, target string) *cutRelay {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("relay listen: %v", err)
	}
	r := &cutRelay{addr: ln.Addr().String(), target: target, up: true, conns: map[net.Conn]struct{}{}}
	t.Cleanup(func() {
		ln.Close()
		r.cut()
	})
	go r.serve(ln)
	return r
}

func (r *cutRelay) serve(ln net.Listener) {
	for {
		c, err := ln.Accept()
		if err != nil {
			return
		}
		r.mu.Lock()
		up := r.up
		r.mu.Unlock()
		if !up {
			c.Close()
			continue
		}
		d, err := net.Dial("tcp", r.target)
		if err != nil {
			c.Close()
			continue
		}
		r.mu.Lock()
		if !r.up { // cut while dialling: this pair must not outlive the cut
			r.mu.Unlock()
			c.Close()
			d.Close()
			continue
		}
		r.conns[c], r.conns[d] = struct{}{}, struct{}{}
		r.mu.Unlock()
		go r.pipe(c, d)
		go r.pipe(d, c)
	}
}

func (r *cutRelay) pipe(dst, src net.Conn) {
	buf := make([]byte, 32<<10)
	for {
		n, err := src.Read(buf)
		if n > 0 && !r.hole.Load() {
			if _, werr := dst.Write(buf[:n]); werr != nil {
				break
			}
		}
		if err != nil {
			break
		}
	}
	dst.Close()
	src.Close()
	r.mu.Lock()
	delete(r.conns, dst)
	delete(r.conns, src)
	r.mu.Unlock()
}

// blackhole drops every byte in both directions from now on; the TCP connections stay open.
func (r *cutRelay) blackhole() { r.hole.Store(true) }

// cut closes every relayed connection and refuses new ones until restore.
func (r *cutRelay) cut() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.up = false
	for c := range r.conns {
		c.Close()
	}
	r.conns = map[net.Conn]struct{}{}
	r.hole.Store(false)
}

func (r *cutRelay) restore() {
	r.mu.Lock()
	r.up = true
	r.mu.Unlock()
}

type sourcingLab struct {
	hubURL       string
	leafA, leafB string
	relayA       *cutRelay
	supA         *Supervisor
}

func newSourcingLab(t *testing.T) *sourcingLab {
	t.Helper()
	dir := t.TempDir()
	seedA, pubA := userKey(t)
	seedB, pubB := userKey(t)
	golden, err := os.ReadFile(filepath.Join("testdata", "hub-accounts-jetstream.golden.conf"))
	if err != nil {
		t.Fatal(err)
	}
	acc := strings.NewReplacer(goldenPubA, pubA, goldenPubB, pubB).Replace(string(golden))
	if err := os.WriteFile(filepath.Join(dir, "accounts.conf"), []byte(acc), 0o600); err != nil {
		t.Fatal(err)
	}
	p := newPKI(t, dir, "box")
	cert, key := p.issue(t, "nats-hub", true)
	leafPort, cport := freePort(t), freePort(t)
	// The hub nats.conf onemind-firstboot writes (hub_nats_conf), with loopback for the mesh IP, and
	// no_advertise: the hub would otherwise tell the leaf its own leaf address, and the leaf would
	// reconnect straight to it around the relay (a real hub advertises the address leaves dial anyway).
	conf := filepath.Join(dir, "hub.conf")
	body := fmt.Sprintf(`server_name: hub
listen: "127.0.0.1:%d"
ping_interval: "20s"
ping_max: 2
jetstream {
  store_dir: %q
  max_file_store: 1GB
  max_memory_store: 0
}
leafnodes {
  listen: "127.0.0.1:%d"
  no_advertise: true
  tls { cert_file: %q, key_file: %q, ca_file: %q, verify: true, timeout: 5 }
}
include "accounts.conf"
`, cport, filepath.Join(dir, "hub-store"), leafPort, cert, key, p.caFile)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	startServer(t, conf)
	l := &sourcingLab{hubURL: fmt.Sprintf("nats://127.0.0.1:%d", cport)}
	hubLeaf := fmt.Sprintf("127.0.0.1:%d", leafPort)
	l.relayA = newCutRelay(t, hubLeaf)
	l.leafA, l.supA = startSourcedLeaf(t, dir, "aaa111", p, l.relayA.addr, seedA)
	l.leafB, _ = startSourcedLeaf(t, dir, "bbb222", p, hubLeaf, seedB)
	return l
}

// startSourcedLeaf starts a node's leaf as onemindd renders it (Apply), dialling the hub at addr.
func startSourcedLeaf(t *testing.T, dir, name string, p *pki, addr string, seed []byte) (string, *Supervisor) {
	t.Helper()
	nd := filepath.Join(dir, name)
	nkeyFile := filepath.Join(nd, "leaf.nkey")
	if _, err := WriteNkeyFile(nkeyFile, seed); err != nil {
		t.Fatal(err)
	}
	c := &Config{
		ServerName: "node-" + name, Listen: fmt.Sprintf("127.0.0.1:%d", freePort(t)),
		Monitor: fmt.Sprintf("127.0.0.1:%d", freePort(t)), StoreDir: filepath.Join(nd, "store"),
		HubURLs: []string{"tls://" + addr}, CAFile: p.caFile, NkeyFile: nkeyFile,
	}
	c.CertFile, c.KeyFile = p.issue(t, "node-"+name, false)
	labLeaf(t, c)
	confPath := filepath.Join(nd, "leaf.conf")
	if _, err := Apply(confPath, c); err != nil {
		t.Fatal(err)
	}
	startServer(t, confPath)
	s := &Supervisor{ConfPath: confPath, Config: c}
	if h := waitHealth(t, s, StateUp, 15*time.Second); h.State != StateUp {
		t.Fatalf("leaf %s never connected: %+v", name, h)
	}
	return "nats://" + c.Listen, s
}

func labCut(t *testing.T) time.Duration {
	t.Helper()
	v := os.Getenv("ONEMIND_LAB_CUT")
	if v == "" {
		return 20 * time.Second
	}
	d, err := time.ParseDuration(v)
	if err != nil || d <= 0 {
		t.Fatalf("ONEMIND_LAB_CUT=%q is not a positive duration", v)
	}
	return d
}

func streamMsgs(ctx context.Context, js jetstream.JetStream, name string) (msgs, last uint64, err error) {
	s, err := js.Stream(ctx, name)
	if err != nil {
		return 0, 0, err
	}
	info, err := s.Info(ctx)
	if err != nil {
		return 0, 0, err
	}
	return info.State.Msgs, info.State.LastSeq, nil
}

// readAll returns the payloads of a stream in stream order.
func readAll(t *testing.T, ctx context.Context, js jetstream.JetStream, name string, n int) []string {
	t.Helper()
	s, err := js.Stream(ctx, name)
	if err != nil {
		t.Fatal(err)
	}
	out := make([]string, 0, n)
	for seq := uint64(1); len(out) < n; seq++ {
		m, err := s.GetMsg(ctx, seq)
		if err != nil {
			t.Fatalf("%s seq %d: %v", name, seq, err)
		}
		out = append(out, string(m.Data))
	}
	return out
}

// Acceptance test of #747: one leaf is cut while it writes 600 events; after the link returns the
// hub's copy holds exactly those 600, in order; the other node's copy is untouched, and node A can
// reach neither node B's stream nor its JetStream API.
func TestHubSourcesEachNodeAcrossAccountsThroughACut(t *testing.T) {
	t.Parallel()
	cut := labCut(t)
	l := newSourcingLab(t)
	ctx, cancel := context.WithTimeout(context.Background(), cut+10*time.Minute)
	defer cancel()

	jsA, jsB := connectJS(t, l.leafA), connectJS(t, l.leafB)
	for _, js := range []jetstream.JetStream{jsA, jsB} {
		if err := EnsureOutbox(ctx, js, OutboxConfig{}); err != nil {
			t.Fatal(err)
		}
	}
	// The gateway: a loopback client with no key lands in ONEMIND (hub-local) and creates both
	// nodes' source streams, as on join approval.
	hub := connectJS(t, l.hubURL)
	srcA, srcB := hubSourceFor(t, "aaa111"), hubSourceFor(t, "bbb222")
	for _, cfg := range []jetstream.StreamConfig{srcA, srcB} {
		if _, err := hub.CreateOrUpdateStream(ctx, cfg); err != nil {
			t.Fatalf("create %s: %v", cfg.Name, err)
		}
	}

	// Node B's events reach its own copy across the accounts.
	for i := 0; i < 20; i++ {
		if _, err := Enqueue(ctx, jsB, "events.sensor", []byte("b-"+strconv.Itoa(i)), fmt.Sprintf("b-%03d", i)); err != nil {
			t.Fatal(err)
		}
	}
	waitUntil(t, 90*time.Second, "node B's 20 events at the hub", func() bool {
		n, _, _ := streamMsgs(ctx, hub, srcB.Name)
		return n == 20
	})
	// Node A's source is live (its consumer on the leaf answers) before the cut.
	waitSourceLive(t, ctx, hub, srcA.Name)

	// Cut node A and write 600 events spread over the cut, each acknowledged by its own leaf.
	l.relayA.cut()
	if h := waitHealth(t, l.supA, StateDown, 30*time.Second); h.State == StateUp {
		t.Fatalf("leaf A still reports the link up after the cut: %+v", h)
	}
	const total = 600
	gap := cut / total
	start := time.Now()
	for i := 0; i < total; i++ {
		if _, err := Enqueue(ctx, jsA, "events.sensor", []byte(strconv.Itoa(i)), fmt.Sprintf("a-%04d", i)); err != nil {
			t.Fatalf("enqueue %d during the cut: %v", i, err)
		}
		if wait := time.Until(start.Add(time.Duration(i+1) * gap)); wait > 0 {
			time.Sleep(wait)
		}
	}
	if st, err := Status(ctx, jsA); err != nil || st.Messages != total {
		t.Fatalf("leaf A outbox after the cut: %+v err=%v, want %d buffered", st, err, total)
	}
	if n, _, _ := streamMsgs(ctx, hub, srcA.Name); n != 0 {
		t.Fatalf("hub copy of A holds %d events while the link is cut", n)
	}

	l.relayA.restore()
	waitCopy(t, ctx, hub, jsA, srcA.Name, total, 5*time.Minute)
	time.Sleep(3 * time.Second) // nothing more may arrive: no duplicate
	n, last, err := streamMsgs(ctx, hub, srcA.Name)
	if err != nil || n != total || last != total {
		t.Fatalf("hub copy of A: %d messages, last seq %d, err %v; want exactly %d", n, last, err, total)
	}
	for i, got := range readAll(t, ctx, hub, srcA.Name, total) {
		if got != strconv.Itoa(i) {
			t.Fatalf("hub copy of A at seq %d holds %q, want %d (order or duplicate)", i+1, got, i)
		}
	}
	if n, _, _ := streamMsgs(ctx, hub, srcB.Name); n != 20 {
		t.Fatalf("hub copy of B holds %d events, want its own 20", n)
	}
	// The WorkQueue outbox gives up what the hub has collected (#747 spec: sourcing from it works).
	waitUntil(t, 30*time.Second, "leaf A outbox drained", func() bool {
		st, err := Status(ctx, jsA)
		return err == nil && st.Messages == 0
	})

	assertNodeCannotReachOther(t, ctx, l)
}

// waitSourceLive waits until the hub's source stream hears its leaf consumer (heartbeats every second).
func waitSourceLive(t *testing.T, ctx context.Context, hub jetstream.JetStream, name string) {
	t.Helper()
	waitUntil(t, 90*time.Second, name+"'s source to reach its leaf", func() bool {
		s, err := hub.Stream(ctx, name)
		if err != nil {
			return false
		}
		info, err := s.Info(ctx)
		if err != nil || len(info.Sources) != 1 {
			return false
		}
		si := info.Sources[0]
		return si.Error == nil && si.Active > 0 && si.Active < 3*time.Second
	})
}

// #747 spec, "test sourcing from WorkQueue": nothing is lost when the link dies with events in
// flight. Sourcing does not use an AckNone consumer on the WorkQueue outbox: nats-server v2.15.3
// turns the source's consumer on a standalone server's WorkQueue (any non-Limits) stream into a
// durable one with AckFlowControl (server/jetstream_api.go, the direct sourcing consumer
// "upgrade"). The leaf then removes an event only when the hub's flow-control reply names a stream
// sequence the hub has stored (server/consumer.go processFlowControl), and a store the hub fails
// rolls its position back and asks again from there (server/stream.go processInboundSourceMsg).
//
// Node A writes without pause while its link first goes silent (every byte dropped, connections
// open, so deliveries and flow-control replies vanish mid-stream), is then closed, and comes back
// before the hub has even noticed the stall. The hub's copy must hold every event once, in order.
func TestHubSourceLosesNothingWhenTheLinkDiesMidStream(t *testing.T) {
	t.Parallel()
	l := newSourcingLab(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	jsA := connectJS(t, l.leafA)
	if err := EnsureOutbox(ctx, jsA, OutboxConfig{}); err != nil {
		t.Fatal(err)
	}
	hub := connectJS(t, l.hubURL)
	srcA := hubSourceFor(t, "aaa111")
	if _, err := hub.CreateOrUpdateStream(ctx, srcA); err != nil {
		t.Fatal(err)
	}
	waitSourceLive(t, ctx, hub, srcA.Name)
	if ci := sourceConsumerInfo(t, ctx, jsA); ci.Config.AckPolicy != jetstream.AckFlowControlPolicy || ci.Config.Durable == "" {
		t.Fatalf("the hub's consumer on the WorkQueue outbox is %s (durable %q): the leaf would drop events the hub never stored",
			ci.Config.AckPolicy, ci.Config.Durable)
	}

	const total, silentAt, closedAt = 3000, 1000, 2000
	body := strings.Repeat("e", 200)
	for i := 0; i < total; i++ {
		switch i {
		case silentAt: // deliveries are flowing when the link goes silent
			waitUntil(t, 60*time.Second, "the first events at the hub", func() bool {
				n, _, _ := streamMsgs(ctx, hub, srcA.Name)
				return n >= 100
			})
			l.relayA.blackhole()
		case closedAt:
			l.relayA.cut()
		}
		if _, err := Enqueue(ctx, jsA, "events.sensor", []byte(strconv.Itoa(i)+" "+body), fmt.Sprintf("a-%05d", i)); err != nil {
			t.Fatalf("enqueue %d: %v", i, err)
		}
		if i%10 == 0 {
			time.Sleep(time.Millisecond) // let deliveries flow between writes
		}
	}
	if n, _, _ := streamMsgs(ctx, hub, srcA.Name); n >= total {
		t.Fatalf("hub copy holds all %d events through a dead link", n)
	}
	l.relayA.restore()
	waitCopy(t, ctx, hub, jsA, srcA.Name, total, 5*time.Minute)
	time.Sleep(3 * time.Second) // nothing more may arrive: no duplicate
	n, last, err := streamMsgs(ctx, hub, srcA.Name)
	if err != nil || n != total || last != total {
		t.Fatalf("hub copy of A: %d messages, last seq %d, err %v; want exactly %d", n, last, err, total)
	}
	for i, got := range readAll(t, ctx, hub, srcA.Name, total) {
		if want := strconv.Itoa(i) + " " + body; got != want {
			t.Fatalf("hub copy of A at seq %d holds %.12q..., want event %d (lost, reordered or duplicated)", i+1, got, i)
		}
	}
	waitUntil(t, 60*time.Second, "leaf A outbox drained", func() bool {
		st, err := Status(ctx, jsA)
		return err == nil && st.Messages == 0
	})
}

// waitCopy waits until the hub's copy holds want events; on a timeout it fails with the state of
// the hub's source and of the leaf's source consumer, so a stuck source says why.
func waitCopy(t *testing.T, ctx context.Context, hub, leafJS jetstream.JetStream, name string, want uint64, d time.Duration) {
	t.Helper()
	end := time.Now().Add(d)
	for time.Now().Before(end) {
		if n, _, _ := streamMsgs(ctx, hub, name); n >= want {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %d events in %s: %s", want, name, sourceDiag(ctx, hub, leafJS, name))
}

// sourceDiag describes a hub source stream and the consumers on the leaf's outbox.
func sourceDiag(ctx context.Context, hub, leafJS jetstream.JetStream, name string) string {
	var b strings.Builder
	if s, err := hub.Stream(ctx, name); err != nil {
		fmt.Fprintf(&b, "hub stream: %v; ", err)
	} else if info, err := s.Info(ctx); err != nil {
		fmt.Fprintf(&b, "hub info: %v; ", err)
	} else {
		fmt.Fprintf(&b, "hub msgs=%d last=%d", info.State.Msgs, info.State.LastSeq)
		for _, si := range info.Sources {
			fmt.Fprintf(&b, " source active=%s lag=%d err=%v", si.Active, si.Lag, si.Error)
		}
		b.WriteString("; ")
	}
	s, err := leafJS.Stream(ctx, OutboxStream)
	if err != nil {
		fmt.Fprintf(&b, "leaf outbox: %v", err)
		return b.String()
	}
	if info, err := s.Info(ctx); err == nil {
		fmt.Fprintf(&b, "leaf outbox msgs=%d first=%d last=%d;", info.State.Msgs, info.State.FirstSeq, info.State.LastSeq)
	}
	for ci := range s.ListConsumers(ctx).Info() {
		fmt.Fprintf(&b, " consumer %s ack=%s deliver=%s bound=%v delivered=%d/%d ackfloor=%d/%d ackpending=%d pending=%d;",
			ci.Name, ci.Config.AckPolicy, ci.Config.DeliverSubject, ci.PushBound, ci.Delivered.Consumer, ci.Delivered.Stream,
			ci.AckFloor.Consumer, ci.AckFloor.Stream, ci.NumAckPending, ci.NumPending)
	}
	return b.String()
}

// assertNodeCannotReachOther: a client on node A's leaf asks node B's JetStream API and the hub's
// copy of B, and listens for B's delivery, while B writes.
func assertNodeCannotReachOther(t *testing.T, ctx context.Context, l *sourcingLab) {
	t.Helper()
	a, err := dialLeaf(l.leafA, nats.Timeout(5*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	for _, subj := range []string{
		"$JS.node-bbb222.API.STREAM.INFO.OUTBOX",
		"$JS.node-bbb222.API.STREAM.MSG.GET.OUTBOX",
		"$JS.node-bbb222.API.CONSUMER.CREATE.OUTBOX",
		"$JS.node-bbb222.API.INFO",
	} {
		if m, err := a.Request(subj, []byte(`{"seq":1}`), 2*time.Second); err == nil {
			t.Fatalf("node A reached node B's JetStream API on %s: %s", subj, m.Data)
		} else if !errors.Is(err, nats.ErrNoResponders) && !errors.Is(err, nats.ErrTimeout) {
			t.Fatalf("%s: %v", subj, err)
		}
	}
	// The hub's copies live in ONEMIND, which offers nodes no JetStream API: from node A, the plain
	// API is A's own leaf, which has no such stream.
	m, err := a.Request("$JS.API.STREAM.INFO.NODE_node_bbb222_OUTBOX", nil, 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	var resp struct {
		Error *struct {
			ErrCode int `json:"err_code"`
		} `json:"error"`
	}
	if json.Unmarshal(m.Data, &resp) != nil || resp.Error == nil || resp.Error.ErrCode != 10059 {
		t.Fatalf("node A read the hub's copy of node B: %s", m.Data)
	}

	// Then A listens (after its own requests, which its listeners would otherwise hear) while B writes.
	// A's own source traffic (its delivery heartbeats, its consumer's flow control) is A's; anything
	// else is a leak, with one known, bounded gap: the hub's flow-control replies to B's consumer
	// ($JS.FC.OUTBOX.<consumer>.<n>, empty body, two sequence counters in headers) reach every node
	// account, because nats-server v2.15.3 leaves name them without their domain unless the leaf sets
	// the js_ack_fc_v2 feature flag. They carry no event and no API answer; the follow-up on #747 turns
	// the flag on in the leaf config and narrows the import to $JS.FC.node-<id>.>.
	own := ownSourceConsumer(t, ctx, connectJS(t, l.leafA))
	leaked := make(chan string, 64)
	var fcMu sync.Mutex
	fcOther := 0
	for _, subj := range []string{"onemind.node.bbb222.>", "onemind.node.*.outbox.>", "$JS.FC.>", "$JS.ACK.>", "$JS.node-bbb222.>"} {
		if _, err := a.Subscribe(subj, func(m *nats.Msg) {
			switch {
			case strings.HasPrefix(m.Subject, "onemind.node.aaa111.outbox."), strings.Contains(m.Subject, "."+own+"."):
			case strings.HasPrefix(m.Subject, "$JS.FC.OUTBOX.") && len(m.Data) == 0:
				fcMu.Lock()
				fcOther++
				fcMu.Unlock()
			default:
				leaked <- m.Subject
			}
		}); err != nil {
			t.Fatal(err)
		}
	}
	if err := a.Flush(); err != nil {
		t.Fatal(err)
	}
	// Large enough that B's consumer asks the hub for flow control, whose replies must reach B only.
	jsB := connectJS(t, l.leafB)
	big := []byte(strings.Repeat("x", 64<<10))
	for i := 20; i < 40; i++ {
		if _, err := Enqueue(ctx, jsB, "events.sensor", big, fmt.Sprintf("b-%03d", i)); err != nil {
			t.Fatal(err)
		}
	}
	hub := connectJS(t, l.hubURL)
	waitUntil(t, 60*time.Second, "node B's next 20 events at the hub", func() bool {
		n, _, _ := streamMsgs(ctx, hub, "NODE_node_bbb222_OUTBOX")
		return n == 40
	})
	time.Sleep(time.Second)
	if len(leaked) > 0 {
		t.Fatalf("node A saw node B's traffic: %s", <-leaked)
	}
	fcMu.Lock()
	defer fcMu.Unlock()
	if fcOther > 0 {
		t.Logf("known gap (follow-up on #747): node A saw %d empty flow-control replies of node B's consumer", fcOther)
	}
}

// ownSourceConsumer is the name of the consumer the hub's source made on a leaf's outbox.
func ownSourceConsumer(t *testing.T, ctx context.Context, js jetstream.JetStream) string {
	t.Helper()
	return sourceConsumerInfo(t, ctx, js).Name
}

// sourceConsumerInfo is the one consumer the hub's source made on a leaf's outbox.
func sourceConsumerInfo(t *testing.T, ctx context.Context, js jetstream.JetStream) *jetstream.ConsumerInfo {
	t.Helper()
	s, err := js.Stream(ctx, OutboxStream)
	if err != nil {
		t.Fatal(err)
	}
	lister := s.ListConsumers(ctx)
	var found []*jetstream.ConsumerInfo
	for ci := range lister.Info() {
		found = append(found, ci)
	}
	if err := lister.Err(); err != nil {
		t.Fatal(err)
	}
	if len(found) != 1 || !strings.HasPrefix(found[0].Name, "JS_SRC_") {
		names := make([]string, 0, len(found))
		for _, ci := range found {
			names = append(names, ci.Name)
		}
		t.Fatalf("leaf outbox consumers %v, want the hub's one source consumer", names)
	}
	return found[0]
}
