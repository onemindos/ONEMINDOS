// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"errors"
	"os"
	"testing"
	"time"
)

// TestLiveGateway runs against a real gateway that core/tests/test_sdk_conformance.py starts
// (ONEMIND_CONFORMANCE_HUB, _OWNER, _AGENT). Skipped otherwise.
func TestLiveGateway(t *testing.T) {
	hub := os.Getenv("ONEMIND_CONFORMANCE_HUB")
	if hub == "" {
		t.Skip("no live gateway")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	owner, _ := New(hub, WithToken(os.Getenv("ONEMIND_CONFORMANCE_OWNER")), WithPrincipal("owner"))
	agent, _ := New(hub, WithToken(os.Getenv("ONEMIND_CONFORMANCE_AGENT")))
	if ok, err := owner.Healthz(ctx); !ok || err != nil {
		t.Fatal(ok, err)
	}
	inst, err := owner.Instance.Get(ctx)
	if err != nil || inst.Name == "" {
		t.Fatal(inst, err)
	}
	if _, err := owner.Apps.Get(ctx, "uptime-kuma"); err != nil {
		t.Fatal(err)
	}
	recs, _, err := owner.Audit.List(ctx, AuditQuery{Limit: 500})
	if err != nil {
		t.Fatal(err)
	}
	since := ""
	if len(recs) > 0 {
		since = itoa(recs[len(recs)-1].Seq)
	}
	got := make(chan Event, 16)
	sctx, stop := context.WithCancel(ctx)
	go func() {
		_ = owner.Events.Subscribe(sctx, SubscribeOptions{Types: []string{"action.*"}, SinceID: since}, func(e Event) error {
			got <- e
			return nil
		})
	}()
	a, err := agent.Actions.Request(ctx, ActionRequest{Type: ActionAppInstall, AppID: "uptime-kuma", IdempotencyKey: "go-conformance"})
	if err != nil || a.State != "awaiting_approval" {
		t.Fatal(a, err)
	}
	again, err := agent.Actions.Request(ctx, ActionRequest{Type: ActionAppInstall, AppID: "uptime-kuma", IdempotencyKey: "go-conformance"})
	if err != nil || again.Id != a.Id {
		t.Fatal("idempotent replay", again, err)
	}
	if _, err := agent.Actions.Approve(ctx, a.Id); !errors.Is(err, ErrPermissionDenied) {
		t.Fatalf("agent approve: %v", err)
	}
	done, err := owner.Actions.Approve(ctx, a.Id)
	if err != nil || done.DecidedBy == nil || done.DecidedBy.Id != "owner" {
		t.Fatal(done, err)
	}
	select {
	case e := <-got:
		if e.Type != "action.requested" || e.Subject["action_id"] != a.Id {
			t.Fatalf("first event %+v", e)
		}
	case <-ctx.Done():
		t.Fatal("no event")
	}
	stop()
	v, err := owner.Audit.Verify(ctx)
	if err != nil || !v.Ok {
		t.Fatal(v, err)
	}
}

func itoa(n int) string {
	b := []byte{}
	for n > 0 || len(b) == 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}
