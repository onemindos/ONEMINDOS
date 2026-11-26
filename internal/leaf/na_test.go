// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"github.com/nats-io/nkeys"

	"github.com/onemindos/onemindos/internal/jobs"
)

// NA lab: the whole D-029 NATS series in one hub (test/qemu/CRITERIA-NATS.md, pre-registered). The hub
// runs hub-accounts-na.golden.conf, which the gateway renders with everything on (job queue, policy
// snapshot, auth callout block, two machines, one hub service key; core/tests/test_fabric_policy.py);
// machine A's leaf has local sign-in. The gateway's callout responder is not running: the gateway is down.
// `make na` runs this test alone.

const naPubGW = "UAIETCIAFQAMTEIL47WBJYZ7OVLKMFPNIJ4P5T6XMGO7EHNVADUNJAAR" // test_fabric_policy.py NA_PUB_GW

func TestNA(t *testing.T) {
	dir := t.TempDir()
	odSeed, odPub := localKey(t, dir, LocalOnemindd)
	_, cliPub := localKey(t, dir, LocalCLI)
	gwKP, _ := nkeys.CreateUser()
	gwSeed, _ := gwKP.Seed()
	gwPub, _ := gwKP.PublicKey()
	gwFile := filepath.Join(dir, "gateway.nk")
	if err := os.WriteFile(gwFile, gwSeed, 0o600); err != nil {
		t.Fatal(err)
	}
	gwOpt, err := nats.NkeyOptionFromSeed(gwFile)
	if err != nil {
		t.Fatal(err)
	}

	// NA1: pinned machines link up with the gateway down (newLabFrom waits for each leaf's hub link).
	sl := newLabFrom(t, "hub-accounts-na.golden.conf", []string{naPubGW, gwPub},
		[]LocalUser{OnemindUser("aaa111", odPub), CLIUser(cliPub)})
	sl.hubOpts = []nats.Option{gwOpt}
	l := jobsLabOn(t, sl, odSeed) // the hub service key signs in: pinned, no callout answer needed
	t.Log("NA1 PASS: both leaves linked and the hub service key signed in with no callout responder")

	results := l.results(t)
	now := time.Now()
	l.publishPolicy(t, l.signer.Policy("aaa111", 1, false, false, nil, nil, now))

	t.Run("NA5 unknown clients refused while the gateway is down", func(t *testing.T) {
		agentSeed, _ := userKey(t)
		f := filepath.Join(t.TempDir(), "agent.nk")
		if err := os.WriteFile(f, agentSeed, 0o600); err != nil {
			t.Fatal(err)
		}
		ank, _ := nats.NkeyOptionFromSeed(f)
		for name, opts := range map[string][]nats.Option{"unregistered agent key": {ank}, "no key": nil} {
			if nc, err := nats.Connect(l.hubURL, append(opts, nats.Timeout(5*time.Second))...); err == nil {
				nc.Close()
				t.Fatalf("NA5 FAIL: %s connected", name)
			}
		}
	})

	t.Run("NA3 local programs sign in, each for its own subjects", func(t *testing.T) {
		for name, seed := range map[string]string{"no key": "", "unknown key": func() string { s, _ := localKey(t, t.TempDir(), "x"); return s }()} {
			if nc, err := connectAs(l.leafA, seed, "x"); err == nil {
				nc.Close()
				t.Fatalf("NA3 FAIL: a client with %s connected to machine A's leaf", name)
			}
		}
		seen := make(chan string, 8)
		sub, err := l.hubNC.Subscribe("onemind.node.bbb222.status", func(m *nats.Msg) { seen <- m.Subject })
		if err != nil {
			t.Fatal(err)
		}
		defer sub.Unsubscribe()
		_ = l.hubNC.Flush()
		errs := make(chan error, 4)
		od, err := nats.Connect(l.leafA, nats.CustomInboxPrefix(InboxPrefix(LocalOnemindd)),
			func() nats.Option { o, _ := nats.NkeyOptionFromSeed(odSeed); return o }(),
			nats.ErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, e error) { errs <- e }))
		if err != nil {
			t.Fatal(err)
		}
		defer od.Close()
		before := pending(t, l.hub, "node-aaa111")
		_ = od.Publish("onemind.node.bbb222.status", []byte(`{}`))
		_ = od.Publish("onemind.node.aaa111.job.host.check", []byte(`{}`))
		_ = od.Flush()
		for i := 0; i < 2; i++ {
			select {
			case e := <-errs:
				if !strings.Contains(strings.ToLower(e.Error()), "permissions violation") {
					t.Fatalf("NA3 FAIL: %v", e)
				}
			case <-time.After(5 * time.Second):
				t.Fatalf("NA3 FAIL: only %d of 2 permission violations", i)
			}
		}
		select {
		case s := <-seen:
			t.Fatalf("NA3 FAIL: %s reached the hub", s)
		case <-time.After(time.Second):
		}
		if pending(t, l.hub, "node-aaa111") != before {
			t.Fatal("NA3 FAIL: a job the machine published reached its queue")
		}
	})

	var ran atomic.Int32
	in := l.intakeA(t, &ran)

	t.Run("NA2 a job reaches a machine that was cut off, once", func(t *testing.T) {
		l.relayA.cut()
		if h := waitHealth(t, l.supA, StateDown, 30*time.Second); h.State == StateUp {
			t.Fatalf("leaf A still up after the cut: %+v", h)
		}
		body, id := l.signer.Job("aaa111", "host.check", map[string]any{"na": 2}, 1, now, nil)
		l.publish(t, "aaa111", body, id)
		l.publish(t, "aaa111", body, id)
		if n := pending(t, l.hub, "node-aaa111"); n != 1 {
			t.Fatalf("NA2 FAIL: %d stored, want 1", n)
		}
		ctx, cancel := context.WithCancel(context.Background())
		done := make(chan error, 1)
		go func() { done <- in.Run(ctx) }()
		defer func() { cancel(); <-done }()
		l.relayA.restore()
		waitUntil(t, 60*time.Second, "NA2 result at the hub", func() bool { return last(results()[id]).State == jobs.StateSucceeded })
		l.publish(t, "aaa111", body, "")
		waitUntil(t, 30*time.Second, "NA2 replay refused", func() bool { return in.Stats().Replayed == 1 })
		if ran.Load() != 1 {
			t.Fatalf("NA2 FAIL: ran %d times", ran.Load())
		}
	})

	t.Run("NA4 the newest stop snapshot wins over queued jobs after a cut", func(t *testing.T) {
		start := ran.Load()
		l.relayA.cut()
		if h := waitHealth(t, l.supA, StateDown, 30*time.Second); h.State == StateUp {
			t.Fatalf("leaf A still up after the cut: %+v", h)
		}
		old, oldID := l.signer.Job("aaa111", "relay.set", map[string]any{"on": true}, 1, now, nil)
		act, actID := l.signer.Job("aaa111", "relay.set", map[string]any{"on": true}, 2, now, nil)
		check, checkID := l.signer.Job("aaa111", "host.check", map[string]any{"na": 4}, 2, now, nil)
		l.publish(t, "aaa111", old, oldID)
		l.publish(t, "aaa111", act, actID)
		l.publishPolicy(t, l.signer.Policy("aaa111", 2, true, false, nil, nil, now))
		l.publish(t, "aaa111", check, checkID)
		ctx, cancel := context.WithCancel(context.Background())
		done := make(chan error, 1)
		go func() { done <- in.Run(ctx) }()
		defer func() { cancel(); <-done }()
		l.relayA.restore()
		want := map[string]string{oldID: "stale_epoch", actID: "stopped"}
		defer func() {
			if t.Failed() {
				t.Logf("NA4 results %+v want %v check %s stats %+v policy %+v", results(), want, checkID, in.Stats(), in.Policy.Current())
			}
		}()
		// A pull still waiting on the hub from before the cut can take the first job and lose it with
		// the link; the hub then redelivers it after the consumer's 60 s ack wait (never twice: the
		// machine refuses a seen job id). Hence the longer wait here.
		waitUntil(t, 150*time.Second, "NA4 verdicts at the hub", func() bool {
			got := results()
			for id, code := range want {
				if r := last(got[id]); r.State != jobs.StateFailed || r.Reason != code {
					return false
				}
			}
			return last(got[checkID]).State == jobs.StateSucceeded
		})
		if ran.Load()-start != 1 {
			t.Fatalf("NA4 FAIL: handlers ran %d times (an actuating job ran under the stop)", ran.Load()-start)
		}
		raw, err := os.ReadFile(filepath.Join(l.stateA, "policy.json"))
		var p struct {
			Epoch int `json:"epoch"`
		}
		if err != nil || json.Unmarshal(raw, &p) != nil || p.Epoch != 2 || !strings.Contains(string(raw), `"motion_lockout":true`) {
			t.Fatalf("NA4 FAIL: snapshot on disk: %v %s", err, raw)
		}
	})

	// §3 amendment (2026-11-26, after the Opus review of #1210).
	t.Run("NA6 no verified note, nothing actuates", func(t *testing.T) {
		start := ran.Load()
		// The intake NA4 ran may have left one pull waiting on the hub (up to its 2 s PollWait); a job
		// published now could go to that dead pull and come back only after the 60 s ack wait.
		time.Sleep(3 * time.Second)
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		ps, err := l.hub.Stream(ctx, "ONEMIND_POLICY")
		if err != nil {
			t.Fatal(err)
		}
		if err := ps.Purge(ctx, jetstream.WithPurgeSubject("onemind.node.aaa111.policy")); err != nil {
			t.Fatalf("purge A's note: %v", err)
		}
		if err := os.WriteFile(filepath.Join(l.stateA, "policy.json"), []byte(`{"schema":"onemind.policy/v1","epoch":99}`), 0o600); err != nil {
			t.Fatal(err)
		}
		fresh := l.intakeA(t, &ran) // a restarted onemindd: reads the disk note, which does not verify
		act, actID := l.signer.Job("aaa111", "relay.set", map[string]any{"na": 6}, 2, now, nil)
		check, checkID := l.signer.Job("aaa111", "host.check", map[string]any{"na": 6}, 2, now, nil)
		l.publishKind(t, "aaa111", "relay.set", act, actID)
		l.publishKind(t, "aaa111", "host.check", check, checkID)
		rctx, rcancel := context.WithCancel(context.Background())
		done := make(chan error, 1)
		go func() { done <- fresh.Run(rctx) }()
		defer func() { rcancel(); <-done }()
		defer func() {
			if t.Failed() {
				t.Logf("NA6 results %+v stats %+v load error %v", results(), fresh.Stats(), fresh.Policy.LoadError())
			}
		}()
		waitUntil(t, 60*time.Second, "NA6 verdicts at the hub", func() bool {
			got := results()
			r := last(got[actID])
			return r.State == jobs.StateFailed && r.Reason == "no_policy" && last(got[checkID]).State == jobs.StateSucceeded
		})
		if ran.Load()-start != 1 {
			t.Fatalf("NA6 FAIL: handlers ran %d times (an actuating job ran with no verified note)", ran.Load()-start)
		}
		if fresh.Policy.LoadError() == nil {
			t.Fatal("NA6 FAIL: the unverified note on disk was not reported")
		}
	})

	t.Run("NA7 a stop purges queued actuating jobs on every machine", func(t *testing.T) {
		start := ran.Load()
		time.Sleep(3 * time.Second) // NA6's intake may still have a pull waiting on the hub (see NA6)
		l.publishPolicy(t, l.signer.Policy("aaa111", 3, true, false, nil, nil, now)) // the stop itself
		l.relayA.cut()
		if h := waitHealth(t, l.supA, StateDown, 30*time.Second); h.State == StateUp {
			t.Fatalf("leaf A still up after the cut: %+v", h)
		}
		act, actID := l.signer.Job("aaa111", "relay.set", map[string]any{"na": 7}, 3, now, nil)
		check, checkID := l.signer.Job("aaa111", "host.check", map[string]any{"na": 7}, 3, now, nil)
		move, _ := l.signer.Job("bbb222", "physical.move", map[string]any{"na": 7}, 3, now, nil)
		l.publishKind(t, "aaa111", "relay.set", act, actID)
		l.publishKind(t, "aaa111", "host.check", check, checkID)
		l.publishKind(t, "bbb222", "physical.move", move, "")
		var filters []string
		raw, err := os.ReadFile(filepath.Join("testdata", "actuating-job-subjects.golden.json"))
		if err != nil || json.Unmarshal(raw, &filters) != nil || len(filters) == 0 {
			t.Fatalf("golden filters: %v", err)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		js, err := l.hub.Stream(ctx, "ONEMIND_JOBS")
		if err != nil {
			t.Fatal(err)
		}
		for _, f := range filters { // what fabric_policy.purge_actuating_jobs sends
			if err := js.Purge(ctx, jetstream.WithPurgeSubject(f)); err != nil {
				t.Fatalf("purge %s: %v", f, err)
			}
		}
		si, err := js.Info(ctx, jetstream.WithSubjectFilter("onemind.node.>"))
		if err != nil {
			t.Fatal(err)
		}
		if want := map[string]uint64{"onemind.node.aaa111.job.host.check": 1}; !reflect.DeepEqual(si.State.Subjects, want) {
			t.Fatalf("NA7 FAIL: queued after the purge %v, want %v (A pending 1, B pending 0)", si.State.Subjects, want)
		}
		// Pending per machine is what the stream still holds on its subjects (A: host.check only, B:
		// nothing). The consumers' own num_pending is not recounted by nats-server after a purge by
		// subject, so it is logged, not judged; the run below proves nothing purged is delivered.
		t.Logf("NA7 consumer num_pending after the purge (informational): A %d, B %d",
			pending(t, l.hub, "node-aaa111"), pending(t, l.hub, "node-bbb222"))
		rctx, rcancel := context.WithCancel(context.Background())
		done := make(chan error, 1)
		go func() { done <- in.Run(rctx) }()
		defer func() { rcancel(); <-done }()
		l.relayA.restore()
		waitUntil(t, 60*time.Second, "NA7 host.check at the hub", func() bool { return last(results()[checkID]).State == jobs.StateSucceeded })
		time.Sleep(2 * time.Second)
		if r := results()[actID]; len(r) != 0 || ran.Load()-start != 1 {
			t.Fatalf("NA7 FAIL: the purged relay.set reported %+v, handlers ran %d", r, ran.Load()-start)
		}
	})
}
