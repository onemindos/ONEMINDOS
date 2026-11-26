// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
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
}
