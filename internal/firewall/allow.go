// SPDX-License-Identifier: Apache-2.0

package firewall

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// Owner allow rules with automatic revert (P-09 part 2).
//
// The image's host.nft has two empty chains in the OneMind table: owner_lan (jumped to from the lan
// chain, so only private source addresses ever reach it) and owner_mesh (jumped to for the mesh
// interface only). An approved rule is one `accept` line in one of them; no scope can name the
// internet, and this package has no way to write a rule anywhere else. A new rule is pending: it
// is removed again at its deadline unless the owner confirms it, and a pending rule is also dropped
// when the host service restarts (the state file keeps only confirmed rules). Every change is one
// atomic `nft -f` transaction that flushes both chains and writes the whole list, so the chains always
// equal the list. The host service itself holds no network privileges: it writes the transaction to
// live.nft and starts onemind-firewall-owner.service, a oneshot unit whose only capability is CAP_NET_ADMIN
// and whose only input is that file.
const (
	ChainLAN  = "owner_lan"
	ChainMesh = "owner_mesh"

	StatePending   = "pending"
	StateConfirmed = "confirmed"
	// StateRevertFailed: the deadline passed and taking the rule away did not load. The rule is no longer in
	// live.nft (so the next load closes it), it stays listed so the owner can see and remove it, and the
	// revert is retried with a growing delay until it loads.
	StateRevertFailed = "revert_failed"

	DefaultTTL = 5 * time.Minute
	MaxAllow   = 16

	retryFirst = 5 * time.Second
	retryMax   = 5 * time.Minute
)

var idRE = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,128}$`)

// Allow is one owner allow rule.
type Allow struct {
	ID      string     `json:"id"`
	Proto   string     `json:"proto"` // tcp or udp
	Port    int        `json:"port"`
	Scope   string     `json:"scope"` // lan or mesh
	State   string     `json:"state"` // pending or confirmed
	Created time.Time  `json:"created"`
	Expires *time.Time `json:"expires,omitempty"` // pending only: when it reverts
}

// AllowState is the "allow" part of GET /v1/firewall.
type AllowState struct {
	Supported  bool    `json:"supported"`
	Reason     string  `json:"reason,omitempty"` // why not, when Supported is false
	TTLSeconds int     `json:"ttl_seconds"`
	Rules      []Allow `json:"rules"`
}

// Refusal is an answer of "no" the caller can show: the request was understood and not done.
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Message }

// Stopper cancels a timer.
type Stopper interface{ Stop() bool }

// Allower keeps the owner allow rules. The zero value is not usable; set Dir and Exec.
type Allower struct {
	Dir string // state directory: allow.json (confirmed rules) and live.nft (what the firewall should hold now)
	// Reload makes the firewall load live.nft (systemctl restart onemind-firewall-owner.service).
	Reload func(ctx context.Context) error
	Now    func() time.Time
	TTL    time.Duration
	// After schedules the revert (time.AfterFunc; tests replace it).
	After func(d time.Duration, f func()) Stopper
	Log   *slog.Logger

	mu     sync.Mutex
	rules  []Allow
	timers map[string]Stopper
}

func (a *Allower) now() time.Time {
	if a.Now != nil {
		return a.Now().UTC()
	}
	return time.Now().UTC()
}

func (a *Allower) ttl() time.Duration {
	if a.TTL > 0 {
		return a.TTL
	}
	return DefaultTTL
}

func (a *Allower) log() *slog.Logger {
	if a.Log != nil {
		return a.Log
	}
	return slog.Default()
}

func (a *Allower) after(d time.Duration, f func()) Stopper {
	if a.After != nil {
		return a.After(d, f)
	}
	return time.AfterFunc(d, f)
}

func (a *Allower) path() string { return filepath.Join(a.Dir, "allow.json") }
func (a *Allower) live() string { return filepath.Join(a.Dir, "live.nft") }

// Open loads the confirmed rules from the state file, drops what was pending, and writes the result into
// the chains. A missing or unreadable file means no rules: the chains are flushed to match.
func (a *Allower) Open(ctx context.Context) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.rules, a.timers = nil, map[string]Stopper{}
	raw, err := os.ReadFile(a.path())
	switch {
	case err == nil:
		var doc struct {
			Rules []Allow `json:"rules"`
		}
		if json.Unmarshal(raw, &doc) != nil {
			a.log().Error("firewall allow state unreadable: no owner rules are applied", "file", a.path())
		}
		for _, r := range doc.Rules {
			if r.State == StateConfirmed && valid(r) == nil && len(a.rules) < MaxAllow {
				r.Expires = nil
				a.rules = append(a.rules, r)
			}
		}
	case !errors.Is(err, os.ErrNotExist):
		a.log().Error("firewall allow state unreadable: no owner rules are applied", "err", err)
	}
	// No rollback at startup: the previous live.nft belongs to the old process and still holds its pending
	// rules. load writes a file with only the confirmed rules; if the reload fails the file is still the
	// right one, and the load is retried with backoff until it succeeds.
	if err := a.load(ctx); err != nil {
		a.timers[openRetryKey] = a.after(retryFirst, func() { a.retryOpen(retryFirst * 2) })
		return err
	}
	return a.save()
}

// openRetryKey is the timers entry of the startup reload retry (it is not a valid rule id).
const openRetryKey = "!open"

// retryOpen loads the confirmed-only state again after a failed startup reload.
func (a *Allower) retryOpen(next time.Duration) {
	a.mu.Lock()
	defer a.mu.Unlock()
	delete(a.timers, openRetryKey)
	ctx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
	defer cancel()
	if err := a.load(ctx); err != nil {
		a.log().Error("firewall owner rules: startup load failed, will retry", "retry_in", next.String(), "err", err)
		a.timers[openRetryKey] = a.after(next, func() { a.retryOpen(min(next*2, retryMax)) })
		return
	}
	a.pruneFailed()
	if err := a.save(); err != nil {
		a.log().Error("firewall owner rules: could not save state", "err", err)
	}
	a.log().Info("firewall owner rules loaded after a retry")
}

func valid(r Allow) error {
	switch {
	case !idRE.MatchString(r.ID):
		return &Refusal{"invalid", "the rule id is not valid"}
	case r.Proto != "tcp" && r.Proto != "udp":
		return &Refusal{"invalid", "the protocol must be tcp or udp"}
	case r.Port < 1 || r.Port > 65535:
		return &Refusal{"invalid", "the port must be 1-65535"}
	case r.Scope != "lan" && r.Scope != "mesh":
		return &Refusal{"invalid", "the scope must be lan or mesh; the internet is never an option"}
	}
	return nil
}

// script is the whole desired state as one nft transaction.
func (a *Allower) script() string {
	var b strings.Builder
	fmt.Fprintf(&b, "flush chain inet %s %s\nflush chain inet %s %s\n", HostTable, ChainLAN, HostTable, ChainMesh)
	for _, r := range a.rules {
		if r.State == StateRevertFailed {
			continue // being taken away: the file the firewall reloads on a restart must not hold it
		}
		chain := ChainLAN
		if r.Scope == "mesh" {
			chain = ChainMesh
		}
		// Every field was checked by valid: numbers and two fixed words, no free text reaches nft.
		fmt.Fprintf(&b, "add rule inet %s %s %s dport %d accept comment \"onemind:allow\"\n", HostTable, chain, r.Proto, r.Port)
	}
	return b.String()
}

// apply writes the desired state and loads it. If the load fails, the previous file is written back and
// loaded again, so live.nft never holds a rule that the list does not show (a restart of the firewall
// reloads that file). The caller restores its own list on error.
func (a *Allower) apply(ctx context.Context) error {
	prev, perr := os.ReadFile(a.live())
	err := a.load(ctx)
	if err == nil {
		a.pruneFailed()
		return nil
	}
	if perr == nil {
		if werr := a.writeFile(a.live(), prev); werr != nil {
			a.log().Error("firewall owner rules: could not write the previous file back", "err", werr)
		} else {
			rctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			if rerr := a.Reload(rctx); rerr != nil {
				a.log().Error("firewall owner rules: the previous rules did not load again", "err", rerr)
			}
		}
	}
	return err
}

// load writes the desired state to live.nft and loads it, without any rollback.
func (a *Allower) load(ctx context.Context) error {
	if err := a.writeFile(a.live(), []byte(a.script())); err != nil {
		return err
	}
	if err := a.Reload(ctx); err != nil {
		a.log().Error("firewall owner rules did not load", "err", err)
		return &Refusal{"firewall_unsupported", "the box's firewall has no owner rules lists (owner_lan, owner_mesh), or it could not load them; update the OS image or look at the Firewall allow rules service"}
	}
	return nil
}

// pruneFailed forgets rules whose revert has now loaded (any successful load excludes them).
func (a *Allower) pruneFailed() {
	kept := a.rules[:0:0]
	for _, r := range a.rules {
		if r.State == StateRevertFailed {
			if t := a.timers[r.ID]; t != nil {
				t.Stop()
				delete(a.timers, r.ID)
			}
			continue
		}
		kept = append(kept, r)
	}
	a.rules = kept
}

func (a *Allower) save() error {
	keep := []Allow{}
	for _, r := range a.rules {
		if r.State == StateConfirmed {
			keep = append(keep, r)
		}
	}
	raw, _ := json.Marshal(map[string]any{"rules": keep})
	return a.writeFile(a.path(), raw)
}

func (a *Allower) writeFile(path string, data []byte) error {
	if err := os.MkdirAll(a.Dir, 0o700); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// List returns a copy of the rules.
func (a *Allower) List() []Allow {
	a.mu.Lock()
	defer a.mu.Unlock()
	return append([]Allow{}, a.rules...)
}

// State is the "allow" part of the firewall view; chains says whether the host table has both lists.
func (a *Allower) State(chains bool) *AllowState {
	st := &AllowState{Supported: chains, TTLSeconds: int(a.ttl() / time.Second), Rules: a.List()}
	if !chains {
		st.Reason = "this OS image's firewall has no owner rules lists yet; update the OS"
	}
	return st
}

// Add opens one port to the LAN or the mesh as a pending rule. The same id again returns the rule it
// made (a retry never adds twice). The rule reverts at its deadline unless Confirm is called.
func (a *Allower) Add(ctx context.Context, id, proto string, port int, scope string) (Allow, error) {
	r := Allow{ID: id, Proto: proto, Port: port, Scope: scope, State: StatePending}
	if err := valid(r); err != nil {
		return Allow{}, err
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, have := range a.rules {
		if have.ID == id {
			return have, nil
		}
		if have.Proto == proto && have.Port == port && have.Scope == scope {
			return Allow{}, &Refusal{"already_allowed", fmt.Sprintf("%s/%d is already allowed from the %s", proto, port, scope)}
		}
	}
	if len(a.rules) >= MaxAllow {
		return Allow{}, &Refusal{"too_many", fmt.Sprintf("at most %d allow rules; remove one first", MaxAllow)}
	}
	r.Created = a.now()
	exp := r.Created.Add(a.ttl())
	r.Expires = &exp
	a.rules = append(a.rules, r)
	if err := a.apply(ctx); err != nil {
		a.rules = a.rules[:len(a.rules)-1]
		return Allow{}, err
	}
	if a.timers == nil {
		a.timers = map[string]Stopper{}
	}
	a.timers[id] = a.after(a.ttl(), func() { a.expire(id) })
	return r, nil
}

// expire is the automatic revert: a rule still pending at its deadline is removed. If the reload fails the
// rule stays listed as revert_failed (it can still be removed) and the revert is retried with backoff.
func (a *Allower) expire(id string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	i := a.index(id)
	if i < 0 || a.rules[i].State != StatePending {
		return
	}
	a.rules[i].State, a.rules[i].Expires = StateRevertFailed, nil
	a.revert(id, retryFirst)
}

// revert loads the state without the rule; on failure it schedules another try after delay (doubling to retryMax).
// The caller holds a.mu and has already marked the rule revert_failed.
func (a *Allower) revert(id string, delay time.Duration) {
	ctx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
	defer cancel()
	// No rollback here: the file must stay without the rule, so even a later restart of the firewall closes it.
	if err := a.load(ctx); err != nil {
		a.log().Error("firewall allow revert failed, will retry", "id", id, "retry_in", delay.String(), "err", err)
		next := min(delay*2, retryMax)
		a.timers[id] = a.after(delay, func() { a.retry(id, next) })
		return
	}
	a.pruneFailed()
	a.log().Info("firewall allow rule reverted: not confirmed in time", "id", id)
}

func (a *Allower) retry(id string, next time.Duration) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if i := a.index(id); i < 0 || a.rules[i].State != StateRevertFailed {
		return
	}
	delete(a.timers, id)
	a.revert(id, next)
}

func (a *Allower) index(id string) int {
	for i, r := range a.rules {
		if r.ID == id {
			return i
		}
	}
	return -1
}

// Confirm keeps a pending rule for good (it survives a restart and a reboot). Confirming a confirmed rule is fine.
func (a *Allower) Confirm(_ context.Context, id string) (Allow, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	i := a.index(id)
	if i < 0 {
		return Allow{}, &Refusal{"unknown_rule", "there is no such allow rule (it may have reverted already)"}
	}
	if a.rules[i].State == StateConfirmed {
		return a.rules[i], nil
	}
	if a.rules[i].State == StateRevertFailed {
		return Allow{}, &Refusal{"reverting", "this rule is being taken away (its time ran out); it cannot be confirmed any more"}
	}
	// Change the timer and the deadline only after the state is saved: a failed save leaves a pending
	// rule that still has its deadline and its timer, so it still reverts.
	prevState, prevExp := a.rules[i].State, a.rules[i].Expires
	a.rules[i].State, a.rules[i].Expires = StateConfirmed, nil
	if err := a.save(); err != nil {
		a.rules[i].State, a.rules[i].Expires = prevState, prevExp
		return Allow{}, err
	}
	if t := a.timers[id]; t != nil {
		t.Stop()
		delete(a.timers, id)
	}
	return a.rules[i], nil
}

// Remove takes a rule away, pending or confirmed.
func (a *Allower) Remove(ctx context.Context, id string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	i := a.index(id)
	if i < 0 {
		return &Refusal{"unknown_rule", "there is no such allow rule"}
	}
	before := append([]Allow{}, a.rules...)
	a.rules = append(a.rules[:i:i], a.rules[i+1:]...)
	if err := a.apply(ctx); err != nil {
		a.rules = before
		return err
	}
	if t := a.timers[id]; t != nil {
		t.Stop()
		delete(a.timers, id)
	}
	return a.save()
}
