// SPDX-License-Identifier: Apache-2.0

package firewall

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type fakeTimer struct{ stopped bool }

func (f *fakeTimer) Stop() bool { f.stopped = true; return true }

type rig struct {
	a      *Allower
	dir    string
	script []string // every nft transaction, in order
	fail   bool
	timers []*fakeTimer
	cbs    []func()
	now    time.Time
}

func newRig(t *testing.T) *rig {
	t.Helper()
	r := &rig{dir: t.TempDir(), now: time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC)}
	r.a = &Allower{Dir: r.dir, TTL: 5 * time.Minute, Now: func() time.Time { return r.now },
		Reload: func(context.Context) error {
			if r.fail {
				return errors.New("no such chain")
			}
			raw, err := os.ReadFile(filepath.Join(r.dir, "live.nft"))
			if err != nil {
				t.Fatal(err)
			}
			r.script = append(r.script, string(raw))
			return nil
		},
		After: func(_ time.Duration, f func()) Stopper {
			ft := &fakeTimer{}
			r.timers, r.cbs = append(r.timers, ft), append(r.cbs, f)
			return ft
		}}
	if err := r.a.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	return r
}

func (r *rig) last() string { return r.script[len(r.script)-1] }

func TestAddIsPendingAndLandsInTheRightList(t *testing.T) {
	r := newRig(t)
	lan, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan")
	if err != nil || lan.State != StatePending || lan.Expires == nil || !lan.Expires.Equal(r.now.Add(5*time.Minute)) {
		t.Fatalf("%+v %v", lan, err)
	}
	if _, err := r.a.Add(context.Background(), "act-2", "udp", 9000, "mesh"); err != nil {
		t.Fatal(err)
	}
	s := r.last()
	for _, want := range []string{
		"flush chain inet onemind_host owner_lan\n", "flush chain inet onemind_host owner_mesh\n",
		`add rule inet onemind_host owner_lan tcp dport 8123 accept comment "onemind:allow"`,
		`add rule inet onemind_host owner_mesh udp dport 9000 accept comment "onemind:allow"`,
	} {
		if !strings.Contains(s, want) {
			t.Fatalf("missing %q in\n%s", want, s)
		}
	}
	if strings.Contains(s, "input") || strings.Contains(s, "saddr") {
		t.Fatalf("a rule only ever goes into the two owner lists:\n%s", s)
	}
}

func TestScopeNeverReachesTheInternet(t *testing.T) {
	r := newRig(t)
	for _, scope := range []string{"wan", "any", "", "lan; flush ruleset", "LAN"} {
		_, err := r.a.Add(context.Background(), "x", "tcp", 80, scope)
		var ref *Refusal
		if !errors.As(err, &ref) || ref.Reason != "invalid" {
			t.Fatalf("scope %q: %v", scope, err)
		}
	}
	for _, c := range []struct {
		id, proto string
		port      int
	}{{"x", "icmp", 80}, {"x", "tcp", 0}, {"x", "tcp", 65536}, {"x y", "tcp", 80}, {"", "tcp", 80}, {"x\"; drop", "tcp", 80}} {
		if _, err := r.a.Add(context.Background(), c.id, c.proto, c.port, "lan"); err == nil {
			t.Fatalf("%+v was accepted", c)
		}
	}
	if len(r.script) != 1 { // only Open's
		t.Fatalf("a refused rule reached nft: %d scripts", len(r.script))
	}
}

func TestUnconfirmedRuleReverts(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	r.cbs[0]() // the deadline passes
	if got := r.a.List(); len(got) != 0 {
		t.Fatalf("still listed: %+v", got)
	}
	if strings.Contains(r.last(), "dport 8123") || !strings.Contains(r.last(), "flush chain inet onemind_host owner_lan") {
		t.Fatalf("the revert did not clear the list:\n%s", r.last())
	}
}

func TestConfirmKeepsTheRuleAndSurvivesARestart(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	if _, err := r.a.Add(context.Background(), "act-2", "tcp", 8124, "lan"); err != nil {
		t.Fatal(err)
	}
	got, err := r.a.Confirm(context.Background(), "act-1")
	if err != nil || got.State != StateConfirmed || got.Expires != nil || !r.timers[0].stopped {
		t.Fatalf("%+v %v stopped=%v", got, err, r.timers[0].stopped)
	}
	r.cbs[0]() // a late timer does nothing to a confirmed rule
	if len(r.a.List()) != 2 {
		t.Fatalf("%+v", r.a.List())
	}
	if _, err := r.a.Confirm(context.Background(), "act-1"); err != nil {
		t.Fatalf("confirming twice is fine: %v", err)
	}
	// The host service restarts (or the box reboots): the confirmed rule returns, the pending one does not.
	b := &Allower{Dir: r.dir, Reload: r.a.Reload, Now: r.a.Now}
	if err := b.Open(context.Background()); err != nil {
		t.Fatal(err)
	}
	l := b.List()
	if len(l) != 1 || l[0].ID != "act-1" || l[0].State != StateConfirmed {
		t.Fatalf("%+v", l)
	}
	if s := r.last(); !strings.Contains(s, "dport 8123") || strings.Contains(s, "8124") {
		t.Fatalf("restore wrote:\n%s", s)
	}
	raw, _ := os.ReadFile(filepath.Join(r.dir, "allow.json"))
	if strings.Contains(string(raw), "8124") {
		t.Fatalf("a pending rule was persisted: %s", raw)
	}
	if fi, _ := os.Stat(filepath.Join(r.dir, "allow.json")); fi.Mode().Perm() != 0o600 {
		t.Fatalf("mode %v", fi.Mode())
	}
}

func TestAddIsIdempotentAndRefusesDuplicates(t *testing.T) {
	r := newRig(t)
	first, _ := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan")
	n := len(r.script)
	again, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan")
	if err != nil || again.ID != first.ID || len(r.script) != n || len(r.timers) != 1 {
		t.Fatalf("a retry must not add twice: %+v %v", again, err)
	}
	_, err = r.a.Add(context.Background(), "act-2", "tcp", 8123, "lan")
	var ref *Refusal
	if !errors.As(err, &ref) || ref.Reason != "already_allowed" {
		t.Fatal(err)
	}
	if _, err := r.a.Add(context.Background(), "act-3", "tcp", 8123, "mesh"); err != nil {
		t.Fatalf("the same port from the mesh is a different rule: %v", err)
	}
}

func TestLimitAndRemove(t *testing.T) {
	r := newRig(t)
	for i := 0; i < MaxAllow; i++ {
		if _, err := r.a.Add(context.Background(), "a"+string(rune('a'+i)), "tcp", 2000+i, "lan"); err != nil {
			t.Fatal(err)
		}
	}
	var ref *Refusal
	if _, err := r.a.Add(context.Background(), "over", "tcp", 3000, "lan"); !errors.As(err, &ref) || ref.Reason != "too_many" {
		t.Fatal(err)
	}
	if err := r.a.Remove(context.Background(), "aa"); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(r.last(), "dport 2000 ") || !r.timers[0].stopped {
		t.Fatalf("the removed rule is still written or its timer runs:\n%s", r.last())
	}
	if err := r.a.Remove(context.Background(), "aa"); !errors.As(err, &ref) || ref.Reason != "unknown_rule" {
		t.Fatal(err)
	}
	if _, err := r.a.Confirm(context.Background(), "nope"); !errors.As(err, &ref) || ref.Reason != "unknown_rule" {
		t.Fatal(err)
	}
}

func TestAnImageWithoutTheListsRefusesAndKeepsNothing(t *testing.T) {
	r := newRig(t)
	r.fail = true
	var ref *Refusal
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); !errors.As(err, &ref) || ref.Reason != "firewall_unsupported" {
		t.Fatal(err)
	}
	if len(r.a.List()) != 0 || len(r.timers) != 0 {
		t.Fatalf("a failed rule stayed: %+v", r.a.List())
	}
}

func TestViewOffersRulesOnlyWhenTheImageHasTheLists(t *testing.T) {
	r := newRig(t)
	c := Collector{Allower: r.a, Run: func(context.Context) ([]byte, error) {
		return []byte(`{"nftables":[{"table":{"family":"inet","name":"onemind_host"}},
{"chain":{"family":"inet","table":"onemind_host","name":"input","hook":"input","policy":"drop"}},
{"chain":{"family":"inet","table":"onemind_host","name":"owner_lan"}}]}`), nil
	}}
	v, err := c.Collect(context.Background())
	if err != nil || v.Allow == nil || v.Allow.Supported || v.Allow.Reason == "" || v.Allow.TTLSeconds != 300 {
		t.Fatalf("one list missing: %+v %v", v.Allow, err)
	}
	c.Run = func(context.Context) ([]byte, error) {
		return []byte(`{"nftables":[{"table":{"family":"inet","name":"onemind_host"}},
{"chain":{"family":"inet","table":"onemind_host","name":"owner_lan"}},
{"chain":{"family":"inet","table":"onemind_host","name":"owner_mesh"}}]}`), nil
	}
	if v, _ := c.Collect(context.Background()); !v.Allow.Supported {
		t.Fatalf("%+v", v.Allow)
	}
}

func (r *rig) liveFile(t *testing.T) string {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join(r.dir, "live.nft"))
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func TestFailedReloadOnAddLeavesNoUntrackedPort(t *testing.T) {
	r := newRig(t)
	r.fail = true
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err == nil {
		t.Fatal("a failed reload must be an error")
	}
	// A later restart of the firewall reloads live.nft: it must not hold the port the list does not show.
	if strings.Contains(r.liveFile(t), "dport 8123") {
		t.Fatalf("live.nft kept a rule the list does not show:\n%s", r.liveFile(t))
	}
}

func TestFailedReloadOnRemoveKeepsRuleAndFile(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	r.fail = true
	if err := r.a.Remove(context.Background(), "act-1"); err == nil {
		t.Fatal("a failed reload must be an error")
	}
	if len(r.a.List()) != 1 || !strings.Contains(r.liveFile(t), "dport 8123") {
		t.Fatalf("list and file disagree after a failed remove: %+v\n%s", r.a.List(), r.liveFile(t))
	}
}

func TestFailedRevertStaysListedRemovableAndRetries(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	r.fail = true
	r.cbs[0]() // deadline, reload fails
	got := r.a.List()
	if len(got) != 1 || got[0].State != StateRevertFailed || got[0].Expires != nil {
		t.Fatalf("a failed revert must stay visible as revert_failed: %+v", got)
	}
	if strings.Contains(r.liveFile(t), "dport 8123") {
		t.Fatalf("the file must already be without the rule, so a restart closes it:\n%s", r.liveFile(t))
	}
	if _, err := r.a.Confirm(context.Background(), "act-1"); err == nil {
		t.Fatal("a rule being reverted cannot be confirmed")
	}
	n := len(r.cbs)
	if n < 2 {
		t.Fatal("a retry must be scheduled")
	}
	r.cbs[n-1]() // retry, still failing: another one is scheduled
	if len(r.cbs) != n+1 || len(r.a.List()) != 1 {
		t.Fatalf("a failing retry must schedule the next: cbs=%d list=%+v", len(r.cbs), r.a.List())
	}
	r.fail = false
	r.cbs[len(r.cbs)-1]() // retry loads
	if len(r.a.List()) != 0 {
		t.Fatalf("a loaded revert must clear the list: %+v", r.a.List())
	}
}

func TestFailedRevertCanBeRemoved(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	r.fail = true
	r.cbs[0]()
	r.fail = false
	if err := r.a.Remove(context.Background(), "act-1"); err != nil {
		t.Fatalf("a revert_failed rule must be removable: %v", err)
	}
	if len(r.a.List()) != 0 || strings.Contains(r.last(), "dport 8123") {
		t.Fatalf("not removed: %+v", r.a.List())
	}
}

func TestFailedConfirmKeepsDeadlineAndTimer(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	// A directory where the temp file goes makes the save fail.
	if err := os.Mkdir(filepath.Join(r.dir, "allow.json.tmp"), 0o700); err != nil {
		t.Fatal(err)
	}
	if _, err := r.a.Confirm(context.Background(), "act-1"); err == nil {
		t.Fatal("a failed save must be an error")
	}
	got := r.a.List()
	if len(got) != 1 || got[0].State != StatePending || got[0].Expires == nil {
		t.Fatalf("the rule lost its deadline: %+v", got)
	}
	if r.timers[0].stopped {
		t.Fatal("the revert timer was stopped although the confirm failed")
	}
	r.cbs[0]() // the deadline passes: the rule still reverts
	if len(r.a.List()) != 0 || strings.Contains(r.liveFile(t), "dport 8123") {
		t.Fatalf("the rule did not revert: %+v", r.a.List())
	}
}

func TestFailedStartupLoadDoesNotRestoreOldPendingRules(t *testing.T) {
	r := newRig(t)
	if _, err := r.a.Add(context.Background(), "act-1", "tcp", 8123, "lan"); err != nil {
		t.Fatal(err)
	}
	// The host service restarts and the first reload fails.
	r.fail = true
	n := len(r.cbs)
	b := &Allower{Dir: r.dir, Reload: r.a.Reload, Now: r.a.Now, After: r.a.After}
	if err := b.Open(context.Background()); err == nil {
		t.Fatal("a failed startup reload must be an error")
	}
	if strings.Contains(r.liveFile(t), "dport 8123") {
		t.Fatalf("live.nft holds the old process's pending rule:\n%s", r.liveFile(t))
	}
	if len(r.cbs) != n+1 {
		t.Fatal("no retry was scheduled")
	}
	r.cbs[n]() // retry still fails: another retry is scheduled
	if len(r.cbs) != n+2 {
		t.Fatal("the retry did not back off to another try")
	}
	r.fail = false
	loads := len(r.script)
	r.cbs[n+1]()
	if len(r.script) != loads+1 || strings.Contains(r.last(), "dport 8123") {
		t.Fatalf("the retry did not load the confirmed-only state:\n%s", r.last())
	}
}
