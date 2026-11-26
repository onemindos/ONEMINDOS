// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/jobs"
	"github.com/onemindos/onemindos/internal/jobs/jobtest"
)

// Durable signed jobs (D-029 plan N2) across the per-node accounts. The hub runs the accounts file
// the gateway renders with JetStream on (hub-accounts-jetstream.golden.conf): ONEMIND exports to each
// node only "next" and "ack" of its own job consumer. The gateway keeps jobs in ONEMIND_JOBS (the
// registry work queue) and makes each node's consumer from node-job-consumer.golden.json, which
// core/onemind_core/jetstream.py NodeJobConsumer renders (core/tests/test_jobs_stream.py).

// jobsStream is ONEMIND_JOBS as the gateway's core plan makes it (jetstream.py plan, registry kinds/node).
func jobsStream() jetstream.StreamConfig {
	return jetstream.StreamConfig{Name: "ONEMIND_JOBS", Subjects: []string{"onemind.node.*.job.>"},
		Retention: jetstream.WorkQueuePolicy, Storage: jetstream.FileStorage, Discard: jetstream.DiscardNew,
		MaxBytes: 64 << 20, MaxAge: 24 * time.Hour, Duplicates: 2 * time.Minute}
}

// jobConsumerFor is the gateway's consumer for a node: the golden file, renamed for nodeID.
func jobConsumerFor(t *testing.T, nodeID string) jetstream.ConsumerConfig {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("testdata", "node-job-consumer.golden.json"))
	if err != nil {
		t.Fatal(err)
	}
	var c jetstream.ConsumerConfig
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatal(err)
	}
	if c.Durable != "node-aaa111" || c.FilterSubject != "onemind.node.aaa111.job.>" || c.AckPolicy != jetstream.AckExplicitPolicy || c.MaxAckPending != 1 {
		t.Fatalf("golden consumer is not node aaa111's explicit-ack queue: %+v", c)
	}
	c.Durable, c.FilterSubject = "node-"+nodeID, "onemind.node."+nodeID+".job.>"
	return c
}

type jobsLab struct {
	*sourcingLab
	hub    jetstream.JetStream
	hubNC  *nats.Conn
	signer *jobtest.Signer
	pubA   string
	stateA string
}

func newJobsLab(t *testing.T) *jobsLab {
	t.Helper()
	l := &jobsLab{sourcingLab: newSourcingLab(t)}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	nc, err := nats.Connect(l.hubURL, nats.Timeout(5*time.Second))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)
	l.hubNC = nc
	if l.hub, err = jetstream.New(nc); err != nil {
		t.Fatal(err)
	}
	if _, err := l.hub.CreateOrUpdateStream(ctx, jobsStream()); err != nil {
		t.Fatal(err)
	}
	for _, n := range []string{"aaa111", "bbb222"} {
		if _, err := l.hub.CreateOrUpdateConsumer(ctx, "ONEMIND_JOBS", jobConsumerFor(t, n)); err != nil {
			t.Fatalf("consumer %s: %v", n, err)
		}
	}
	dir := t.TempDir()
	if l.signer, l.pubA, err = jobtest.New(dir); err != nil {
		t.Fatal(err)
	}
	l.stateA = filepath.Join(dir, "state-a")
	if err := os.MkdirAll(l.stateA, 0o700); err != nil {
		t.Fatal(err)
	}
	return l
}

// publish is the gateway publishing one job (rollouts.py): on the node's job subject, named by job id.
func (l *jobsLab) publish(t *testing.T, node string, body []byte, id string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	m := nats.NewMsg("onemind.node." + node + ".job.host.check")
	m.Data = body
	if id != "" {
		m.Header.Set(jetstream.MsgIDHeader, id)
	}
	if _, err := l.hub.PublishMsg(ctx, m); err != nil {
		t.Fatalf("publish: %v", err)
	}
}

func (l *jobsLab) intakeA(t *testing.T, ran *atomic.Int32) *jobs.Intake {
	t.Helper()
	nc, err := nats.Connect(l.leafA, nats.MaxReconnects(-1), nats.ReconnectWait(200*time.Millisecond))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)
	return &jobs.Intake{NC: nc, NodeID: "aaa111", Verifier: backup.NewNodeJobVerifier("aaa111", l.pubA, l.stateA),
		Handlers: map[string]jobs.Handler{"host.check": func(context.Context, backup.Job) jobs.Result {
			ran.Add(1)
			return jobs.Result{State: jobs.StateSucceeded, Summary: "ok"}
		}},
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)), PollWait: 2 * time.Second, Retry: 200 * time.Millisecond}
}

// results collects node aaa111's job results at the hub (the gateway's ONEMIND_JOBRESULTS feed).
func (l *jobsLab) results(t *testing.T) func() map[string][]jobs.Report {
	t.Helper()
	var mu sync.Mutex
	got := map[string][]jobs.Report{}
	if _, err := l.hubNC.Subscribe("onemind.node.aaa111.jobresult.>", func(m *nats.Msg) {
		var r jobs.Report
		if json.Unmarshal(m.Data, &r) == nil {
			mu.Lock()
			got[r.JobID] = append(got[r.JobID], r)
			mu.Unlock()
		}
	}); err != nil {
		t.Fatal(err)
	}
	return func() map[string][]jobs.Report {
		mu.Lock()
		defer mu.Unlock()
		out := map[string][]jobs.Report{}
		for k, v := range got {
			out[k] = append([]jobs.Report(nil), v...)
		}
		return out
	}
}

func last(rs []jobs.Report) jobs.Report {
	if len(rs) == 0 {
		return jobs.Report{}
	}
	return rs[len(rs)-1]
}

func pending(t *testing.T, js jetstream.JetStream, consumer string) uint64 {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	c, err := js.Consumer(ctx, "ONEMIND_JOBS", consumer)
	if err != nil {
		t.Fatal(err)
	}
	info, err := c.Info(ctx)
	if err != nil {
		t.Fatal(err)
	}
	return info.NumPending + uint64(info.NumAckPending)
}

// A machine cut off when its job is sent gets it on reconnect, runs it once, and reports the result.
func TestJobReachesAMachineThatWasOfflineAndRunsOnce(t *testing.T) {
	t.Parallel()
	l := newJobsLab(t)
	results := l.results(t)
	l.relayA.cut()
	if h := waitHealth(t, l.supA, StateDown, 30*time.Second); h.State == StateUp {
		t.Fatalf("leaf A still up after the cut: %+v", h)
	}
	body, id := l.signer.Job("aaa111", "host.check", map[string]any{"why": "lab"}, 1, time.Now(), nil)
	l.publish(t, "aaa111", body, id)
	l.publish(t, "aaa111", body, id) // the gateway retried: the stream keeps one copy (named by job id)
	if n := pending(t, l.hub, "node-aaa111"); n != 1 {
		t.Fatalf("pending for node A = %d, want 1 (deduplicated by job id)", n)
	}

	var ran atomic.Int32
	in := l.intakeA(t, &ran)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- in.Run(ctx) }()
	defer func() { cancel(); <-done }()
	time.Sleep(time.Second) // the intake retries against a dead link
	if ran.Load() != 0 {
		t.Fatal("a job ran while the machine was cut off")
	}
	l.relayA.restore()
	waitUntil(t, 60*time.Second, "the job's succeeded result at the hub", func() bool {
		return last(results()[id]).State == jobs.StateSucceeded
	})
	if ran.Load() != 1 || pending(t, l.hub, "node-aaa111") != 0 {
		t.Fatalf("ran %d, pending %d", ran.Load(), pending(t, l.hub, "node-aaa111"))
	}

	// The same signed job published again (no message id, so the stream takes it): refused as a
	// replay, acknowledged, never run twice.
	l.publish(t, "aaa111", body, "")
	waitUntil(t, 30*time.Second, "the replay acknowledged", func() bool {
		return in.Stats().Replayed == 1 && pending(t, l.hub, "node-aaa111") == 0
	})
	if ran.Load() != 1 {
		t.Fatalf("a replayed job ran: %d", ran.Load())
	}
}

// Jobs for another machine, unsigned or signed by another key are refused, terminated (never
// redelivered) and reported failed with the reason; node A can neither read node B's queue nor
// put a job into its own.
func TestJobRefusalsAndNodeIsolation(t *testing.T) {
	t.Parallel()
	l := newJobsLab(t)
	results := l.results(t)
	var ran atomic.Int32
	in := l.intakeA(t, &ran)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- in.Run(ctx) }()
	defer func() { cancel(); <-done }()

	other, _, err := jobtest.New(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	cases := map[string]func() ([]byte, string){
		"wrong_audience": func() ([]byte, string) { return l.signer.Job("bbb222", "host.check", nil, 1, now, nil) },
		"unknown_kid":    func() ([]byte, string) { return other.Job("aaa111", "host.check", nil, 1, now, nil) },
		"bad_signature": func() ([]byte, string) {
			b, id := l.signer.Job("aaa111", "host.check", nil, 1, now, nil)
			var env map[string]any
			_ = json.Unmarshal(b, &env)
			env["params"] = map[string]any{"forged": true}
			out, _ := json.Marshal(env)
			return out, id
		},
		"expired": func() ([]byte, string) {
			return l.signer.Job("aaa111", "host.check", nil, 1, now.Add(-time.Hour), nil)
		},
	}
	want := map[string]string{}
	for code, mk := range cases {
		body, id := mk()
		want[id] = code
		l.publish(t, "aaa111", body, id)
	}
	defer func() {
		if t.Failed() {
			t.Logf("results %+v want %v stats %+v", results(), want, in.Stats())
		}
	}()
	waitUntil(t, 60*time.Second, "every refusal reported", func() bool {
		got := results()
		for id, code := range want {
			if r := last(got[id]); r.State != jobs.StateFailed || r.Reason != code {
				return false
			}
		}
		return true
	})
	if ran.Load() != 0 || pending(t, l.hub, "node-aaa111") != 0 {
		t.Fatalf("ran %d pending %d", ran.Load(), pending(t, l.hub, "node-aaa111"))
	}
	// An unknown kind is verified but not run: this machine was never given it.
	body, id := l.signer.Job("aaa111", "update.apply", map[string]any{"version": "9.9.9"}, 1, now, nil)
	l.publish(t, "aaa111", body, id)
	waitUntil(t, 30*time.Second, "unsupported_kind reported", func() bool {
		return last(results()[id]).Reason == "unsupported_kind"
	})

	// Node A's leaf: node B's queue has no responder for it, and a job A writes stays in A's account.
	ncA, err := nats.Connect(l.leafA)
	if err != nil {
		t.Fatal(err)
	}
	defer ncA.Close()
	req, _ := json.Marshal(map[string]any{"batch": 1, "expires": int64(time.Second)})
	l.publish(t, "bbb222", func() []byte { b, _ := l.signer.Job("bbb222", "host.check", nil, 1, now, nil); return b }(), "")
	if m, err := ncA.Request(jobs.PullSubject("bbb222"), req, 3*time.Second); err == nil {
		t.Fatalf("node A read node B's queue: %q %v", m.Data, m.Header)
	}
	if n := pending(t, l.hub, "node-bbb222"); n != 1 {
		t.Fatalf("node B's job pending = %d, want 1", n)
	}
	forged, _ := l.signer.Job("aaa111", "host.check", nil, 1, now, nil)
	if err := ncA.Publish("onemind.node.aaa111.job.host.check", forged); err != nil {
		t.Fatal(err)
	}
	_ = ncA.Flush()
	time.Sleep(2 * time.Second)
	if n := pending(t, l.hub, "node-aaa111"); n != 0 || ran.Load() != 0 {
		t.Fatalf("a job published by the node itself reached its queue: pending %d ran %d", n, ran.Load())
	}
}
