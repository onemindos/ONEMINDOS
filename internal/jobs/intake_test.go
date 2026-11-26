// SPDX-License-Identifier: Apache-2.0

package jobs

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/jobs/jobtest"
)

// A plain nats-server stands in for the hub: a responder on the pull subject hands out queued
// envelopes with an ack reply subject, and records each ack verb. internal/leaf/jobs_test.go runs the
// real thing (ONEMIND_JOBS across the per-node accounts and a leaf link).

type fakeHub struct {
	mu    sync.Mutex
	queue [][]byte
	acks  []string
	pulls []map[string]any
}

func startFake(t *testing.T) (*nats.Conn, *fakeHub) {
	t.Helper()
	s, err := server.NewServer(&server.Options{Host: "127.0.0.1", Port: -1, NoLog: true, NoSigs: true})
	if err != nil {
		t.Fatal(err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("server not ready")
	}
	t.Cleanup(s.Shutdown)
	nc, err := nats.Connect(s.ClientURL())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)
	h := &fakeHub{}
	if _, err := nc.Subscribe(PullSubject("n1"), func(m *nats.Msg) {
		var req map[string]any
		_ = json.Unmarshal(m.Data, &req)
		h.mu.Lock()
		h.pulls = append(h.pulls, req)
		var body []byte
		if len(h.queue) > 0 {
			body, h.queue = h.queue[0], h.queue[1:]
		}
		h.mu.Unlock()
		out := nats.NewMsg(m.Reply)
		if body == nil {
			out.Header.Set("Status", "408")
		} else {
			out.Data, out.Reply = body, "fake.ack"
		}
		_ = nc.PublishMsg(out)
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := nc.Subscribe("fake.ack", func(m *nats.Msg) {
		h.mu.Lock()
		h.acks = append(h.acks, string(m.Data))
		h.mu.Unlock()
		_ = m.Respond(nil)
	}); err != nil {
		t.Fatal(err)
	}
	return nc, h
}

func TestIntakeRunsOnceAcksAndReports(t *testing.T) {
	nc, h := startFake(t)
	dir := t.TempDir()
	s, pub, err := jobtest.New(dir)
	if err != nil {
		t.Fatal(err)
	}
	var reports []Report
	var rmu sync.Mutex
	if _, err := nc.Subscribe("onemind.node.n1.jobresult.*", func(m *nats.Msg) {
		var r Report
		_ = json.Unmarshal(m.Data, &r)
		rmu.Lock()
		reports = append(reports, r)
		rmu.Unlock()
	}); err != nil {
		t.Fatal(err)
	}
	ran := 0
	in := &Intake{NC: nc, NodeID: "n1", Verifier: backup.NewNodeJobVerifier("n1", pub, filepath.Join(dir)),
		Handlers: map[string]Handler{
			"host.check": func(context.Context, backup.Job) Result { ran++; return Result{State: StateSucceeded, Summary: "ok"} },
			"host.fail":  func(context.Context, backup.Job) Result { return Result{State: "weird", Reason: "boom"} },
		},
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)), PollWait: 200 * time.Millisecond}
	now := time.Now()
	good, goodID := s.Job("n1", "host.check", nil, 1, now, nil)
	fail, failID := s.Job("n1", "host.fail", nil, 1, now, nil)
	other, otherID := s.Job("n2", "host.check", nil, 1, now, nil)
	h.queue = [][]byte{good, good, fail, other, []byte("not json")}
	ctx := context.Background()
	for i := 0; i < 5; i++ {
		if got, err := in.PullOnce(ctx); err != nil || !got {
			t.Fatalf("pull %d: %v %v", i, got, err)
		}
	}
	if got, err := in.PullOnce(ctx); err != nil || got {
		t.Fatalf("empty queue: got %v err %v", got, err)
	}
	_ = nc.Flush()
	time.Sleep(200 * time.Millisecond)
	if ran != 1 {
		t.Fatalf("the job ran %d times, want 1", ran)
	}
	if want := "+ACK +ACK +ACK +TERM +TERM"; strings.Join(h.acks, " ") != want {
		t.Fatalf("acks %q, want %q", h.acks, want)
	}
	if st := in.Stats(); st != (Stats{Ran: 2, Refused: 2, Replayed: 1}) {
		t.Fatalf("stats %+v", st)
	}
	if exp, _ := h.pulls[0]["expires"].(float64); exp != float64(200*time.Millisecond) || h.pulls[0]["batch"] != float64(1) {
		t.Fatalf("pull request %v", h.pulls[0])
	}
	rmu.Lock()
	defer rmu.Unlock()
	byID := map[string][]string{}
	for _, r := range reports {
		byID[r.JobID] = append(byID[r.JobID], r.State+"/"+r.Reason)
		if r.State != StateRunning && r.FinishedAt == "" {
			t.Errorf("final report without finished_at: %+v", r)
		}
	}
	for id, want := range map[string]string{goodID: "running/ succeeded/", failID: "running/ failed/boom", otherID: "failed/wrong_audience"} {
		if got := strings.Join(byID[id], " "); got != want {
			t.Errorf("%s: %q, want %q", id, got, want)
		}
	}
}

func TestIntakeNeedsMatchingNodeAndHubErrors(t *testing.T) {
	nc, _ := startFake(t)
	v := backup.NewNodeJobVerifier("n2", "/nonexistent/job.pub", t.TempDir())
	if _, err := (&Intake{NC: nc, NodeID: "n1", Verifier: v}).PullOnce(context.Background()); err == nil {
		t.Fatal("a verifier for another node was accepted")
	}
	in := &Intake{NC: nc, NodeID: "n3", Verifier: backup.NewNodeJobVerifier("n3", "/x", t.TempDir()), PollWait: 50 * time.Millisecond}
	if _, err := in.PullOnce(context.Background()); err == nil {
		t.Fatal("no responder on the pull subject must be an error (link down)")
	}
	if rawJobID([]byte(`{"job_id":"job_ok123456"}`)) != "job_ok123456" || rawJobID([]byte(`{"job_id":"x"}`)) != "" {
		t.Fatal("rawJobID")
	}
	if r := Builtin("n1")["host.check"](context.Background(), backup.Job{}); r.State != StateSucceeded || !strings.Contains(r.Summary, "node-n1") {
		t.Fatalf("host.check: %+v", r)
	}
}
