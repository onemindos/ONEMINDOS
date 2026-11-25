// SPDX-License-Identifier: Apache-2.0

package host

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/storage/ops"
)

type fakePower struct {
	mu       sync.Mutex
	reboots  int
	poweroff int
	err      error
}

func (f *fakePower) Reboot(context.Context) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.reboots++
	return f.err
}

func (f *fakePower) PowerOff(context.Context) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.poweroff++
	return f.err
}

type fakeOS struct {
	why      string
	busy     string
	offered  string
	rebooted bool
	got      []string
}

func (f *fakeOS) Unavailable() string { return f.why }
func (f *fakeOS) UpdateBusy() string  { return f.busy }
func (f *fakeOS) Install(_ context.Context, v string, goingDown func()) (string, bool, error) {
	f.got = append(f.got, v)
	if v != f.offered {
		return "", false, &Refusal{"version_not_offered", "not offered"}
	}
	if f.rebooted {
		goingDown()
		return "", true, nil
	}
	return "installed; reboot deferred", false, nil
}

func newService(t *testing.T, dir, boot string) (*Service, *fakePower) {
	t.Helper()
	st, err := OpenStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	p := &fakePower{}
	return &Service{Store: st, Power: p, OS: &fakeOS{offered: "1.2.0", rebooted: true}, BootID: boot}, p
}

func TestRestartJournalsThenReportsAfterReboot(t *testing.T) {
	dir := t.TempDir()
	s, p := newService(t, dir, "boot-1")
	op, created, err := s.Submit(context.Background(), Request{ActionID: "act-1", Kind: KindRestart})
	if err != nil || !created || op.State != StateAccepted {
		t.Fatalf("submit: %+v %v %v", op, created, err)
	}
	s.Wait()
	if p.reboots != 1 {
		t.Fatalf("reboots = %d", p.reboots)
	}
	got, _ := s.Store.Get("act-1")
	if got.State != StateGoingDown {
		t.Fatalf("before the reboot the journal says %q", got.State)
	}
	// Same action id again (the gateway retried): nothing new runs.
	again, created, err := s.Submit(context.Background(), Request{ActionID: "act-1", Kind: KindRestart})
	if err != nil || created || again.State != StateGoingDown {
		t.Fatalf("retry: %+v %v %v", again, created, err)
	}
	if p.reboots != 1 {
		t.Fatal("a retried action id rebooted twice")
	}
	// A new boot: the service starts again and settles the journal.
	s2, _ := newService(t, dir, "boot-2")
	if err := s2.Resume(); err != nil {
		t.Fatal(err)
	}
	got, _ = s2.Store.Get("act-1")
	if got.State != StateSucceeded || got.FinishedAt == nil || got.Message != "the box restarted" {
		t.Fatalf("after reboot: %+v", got)
	}
}

func TestShutdownFailureIsReported(t *testing.T) {
	s, p := newService(t, t.TempDir(), "b")
	p.err = errors.New("access denied")
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "a2", Kind: KindShutdown}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	got, _ := s.Store.Get("a2")
	if p.poweroff != 1 || got.State != StateFailed || got.Reason != "host_error" || !strings.Contains(got.Message, "access denied") {
		t.Fatalf("%+v", got)
	}
	if s.Active() != nil {
		t.Fatal("a failed action stays active")
	}
}

func TestRefusals(t *testing.T) {
	s, _ := newService(t, t.TempDir(), "b")
	s.Delay = time.Hour // keep the first action active
	ctx, cancel := context.WithCancel(context.Background())
	defer func() { cancel(); s.Wait() }()
	if _, _, err := s.Submit(ctx, Request{ActionID: "x1", Kind: KindRestart}); err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		req    Request
		reason string
	}{
		{Request{ActionID: "x2", Kind: KindShutdown}, "busy"},
		{Request{ActionID: "x1", Kind: KindShutdown}, "action_id_reused"},
	}
	for _, c := range cases {
		_, _, err := s.Submit(ctx, c.req)
		var r *Refusal
		if !errors.As(err, &r) || r.Reason != c.reason {
			t.Errorf("%+v: got %v, want %s", c.req, err, c.reason)
		}
	}
	for _, bad := range []Request{
		{ActionID: "../etc/passwd", Kind: KindRestart},
		{ActionID: "ok", Kind: "reboot-now"},
		{ActionID: "ok", Kind: KindRestart, Version: "1.0"},
		{ActionID: "ok", Kind: KindOSInstall},
		{ActionID: "ok", Kind: KindOSInstall, Version: "1.0; rm -rf /"},
	} {
		if err := bad.Validate(); err == nil {
			t.Errorf("accepted malformed %+v", bad)
		}
	}
	// No factory reset in this build: refused with the reason, never pretended.
	idle, _ := newService(t, t.TempDir(), "b")
	_, _, err := idle.Submit(ctx, Request{ActionID: "r1", Kind: KindFactoryReset, PlanSHA256: strings.Repeat("a", 64)})
	var r *Refusal
	if !errors.As(err, &r) || r.Reason != "unavailable" {
		t.Fatalf("factory reset without a resetter: %v", err)
	}
	if _, err := idle.Store.Get("r1"); !errors.Is(err, ErrNotFound) {
		t.Fatal("a refused request was journaled")
	}
	// An OS update between install and the gate's verdict: the box must not go down.
	upd, _ := newService(t, t.TempDir(), "b")
	upd.OS = &fakeOS{busy: "an OS update is trial"}
	for _, k := range []string{KindRestart, KindShutdown} {
		_, _, err = upd.Submit(ctx, Request{ActionID: "busy-" + k, Kind: k})
		if !errors.As(err, &r) || r.Reason != "update_in_progress" {
			t.Errorf("%s during an update: %v", k, err)
		}
	}
	// No journal: nothing may start.
	nj := &Service{Power: &fakePower{}}
	if _, _, err := nj.Submit(ctx, Request{ActionID: "n1", Kind: KindRestart}); !errors.Is(err, ErrNoJournal) {
		t.Fatalf("without a journal: %v", err)
	}
}

func TestInterruptedActionsAreFailedNotRerun(t *testing.T) {
	dir := t.TempDir()
	st, _ := OpenStore(dir)
	at := time.Date(2026, 11, 19, 1, 0, 0, 0, time.UTC)
	for _, op := range []Op{
		{ID: "same-boot", Kind: KindRestart, State: StateAccepted, BootID: "b2", AcceptedAt: at},
		{ID: "power-cut", Kind: KindOSInstall, Version: "1.2.0", State: StateRunning, BootID: "b1", AcceptedAt: at},
		{ID: "installed", Kind: KindOSInstall, Version: "1.2.0", State: StateGoingDown, BootID: "b1", AcceptedAt: at},
		{ID: "reset", Kind: KindFactoryReset, State: StateGoingDown, BootID: "b1", AcceptedAt: at},
		{ID: "done", Kind: KindRestart, State: StateSucceeded, BootID: "b0", AcceptedAt: at, Message: "kept"},
	} {
		if err := st.Put(op); err != nil {
			t.Fatal(err)
		}
	}
	p := &fakePower{}
	s := &Service{Store: st, Power: p, BootID: "b2"}
	if err := s.Resume(); err != nil {
		t.Fatal(err)
	}
	want := map[string]string{"same-boot": StateFailed, "power-cut": StateFailed, "installed": StateSucceeded,
		"done": StateSucceeded, "reset": StateFailed}
	for id, w := range want {
		op, _ := st.Get(id)
		if op.State != w {
			t.Errorf("%s: %s, want %s (%s)", id, op.State, w, op.Message)
		}
	}
	if op, _ := st.Get("reset"); op.Reason != "not_wiped" {
		t.Errorf("a reset record that survived the reboot: %+v", op)
	}
	if op, _ := st.Get("done"); op.Message != "kept" {
		t.Error("a finished record was rewritten")
	}
	if p.reboots+p.poweroff != 0 || s.Active() != nil {
		t.Fatal("resume acted on its own")
	}
}

func TestOSInstall(t *testing.T) {
	s, _ := newService(t, t.TempDir(), "b")
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "u1", Kind: KindOSInstall, Version: "1.2.0"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("u1"); op.State != StateGoingDown {
		t.Fatalf("install that reboots: %+v", op)
	}
	s.active = nil // the box "rebooted"
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "u2", Kind: KindOSInstall, Version: "9.9.9"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("u2"); op.State != StateFailed || op.Reason != "version_not_offered" {
		t.Fatalf("other version: %+v", op)
	}
	s.OS = &fakeOS{why: "no update.conf"}
	if st := (&Server{S: s}).Status(); st.Operations[3].Available || *st.Operations[3].Reason != "no update.conf" {
		t.Fatalf("status: %+v", st.Operations[3])
	}
}

type fakeReset struct{ armed []string }

func (f *fakeReset) Unavailable() string { return "" }
func (f *fakeReset) Plan(context.Context) ResetPlan {
	return ResetPlan{Available: true, SHA256: strings.Repeat("a", 64)}
}
func (f *fakeReset) Arm(_ context.Context, op Op) error {
	f.armed = append(f.armed, op.ID)
	return nil
}

func TestFactoryResetArmsThenReboots(t *testing.T) {
	s, p := newService(t, t.TempDir(), "b")
	r := &fakeReset{}
	s.Reset = r
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "fr", Kind: KindFactoryReset, PlanSHA256: strings.Repeat("a", 64)}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("fr"); len(r.armed) != 1 || p.reboots != 1 || op.State != StateGoingDown {
		t.Fatalf("armed %v reboots %d op %+v", r.armed, p.reboots, op)
	}
}

// The socket: wrong peer credentials are refused before any handler runs; the
// gateway's group gets through.
func TestSocketPeerCredentials(t *testing.T) {
	dir, err := shortTempDir(t)
	if err != nil {
		t.Fatal(err)
	}
	s, p := newService(t, filepath.Join(dir, "j"), "b")
	sock := filepath.Join(dir, "h.sock")
	l, err := ops.Listen(sock, -1)
	if err != nil {
		t.Fatal(err)
	}
	peer := struct{ uid, gid int }{1000, 1000}
	srv := &Server{S: s, AllowUID: -1, AllowGID: 961,
		PeerCred: func(*net.UnixConn) (int, int, bool) { return peer.uid, peer.gid, true }}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- srv.Serve(ctx, l) }()
	defer func() { cancel(); <-done }()
	c := &http.Client{Transport: &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", sock)
	}}}
	post := func(body string) (int, map[string]any) {
		resp, err := c.Post("http://host/v1/operations", "application/json", bytes.NewBufferString(body))
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		b, _ := io.ReadAll(resp.Body)
		m := map[string]any{}
		_ = json.Unmarshal(b, &m)
		return resp.StatusCode, m
	}
	if code, m := post(`{"action_id":"a","kind":"restart"}`); code != http.StatusForbidden || m["error"] != "permission_denied" {
		t.Fatalf("stranger: %d %v", code, m)
	}
	if p.reboots != 0 {
		t.Fatal("a refused peer rebooted the box")
	}
	peer.gid = 961 // the gateway's group
	if code, m := post(`{"action_id":"a","kind":"restart","extra":1}`); code != http.StatusBadRequest {
		t.Fatalf("unknown field: %d %v", code, m)
	}
	if code, m := post(`{"action_id":"a","kind":"restart"}`); code != http.StatusAccepted || m["state"] != StateAccepted {
		t.Fatalf("gateway: %d %v", code, m)
	}
	if code, m := post(`{"action_id":"a","kind":"restart"}`); code != http.StatusOK || m["action_id"] != "a" {
		t.Fatalf("retry: %d %v", code, m)
	}
	if code, m := post(`{"action_id":"b","kind":"os-install","version":"2.0.0"}`); code != http.StatusConflict || m["reason"] != "busy" {
		t.Fatalf("busy: %d %v", code, m)
	}
	s.Wait()
	resp, err := c.Get("http://host/v1/operations/a")
	if err != nil {
		t.Fatal(err)
	}
	var op Op
	_ = json.NewDecoder(resp.Body).Decode(&op)
	resp.Body.Close()
	if op.State != StateGoingDown || p.reboots != 1 {
		t.Fatalf("operation: %+v, reboots %d", op, p.reboots)
	}
	resp, _ = c.Get("http://host/v1/status")
	var st Status
	_ = json.NewDecoder(resp.Body).Decode(&st)
	resp.Body.Close()
	// One entry per kind, in Kinds order. Without their hooks only restart, shutdown and os-install are offered
	// (round-2 integration: checked by kind so every PR's new kind fits).
	if st.Schema != Schema || len(st.Operations) != len(Kinds) {
		t.Fatalf("status: %+v", st)
	}
	for i, o := range st.Operations {
		want := o.Kind == KindRestart || o.Kind == KindShutdown || o.Kind == KindOSInstall
		if o.Kind != Kinds[i] || o.Available != want {
			t.Fatalf("status operation %d: %+v (want available=%v)", i, o, want)
		}
	}
}

func TestCorruptRecordFailsClosed(t *testing.T) {
	dir := t.TempDir()
	st, _ := OpenStore(dir)
	if err := os.WriteFile(filepath.Join(dir, "half.json"), []byte(`{"action_id": "half", "st`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := st.List(); err == nil {
		t.Fatal("a corrupt record was skipped")
	}
	if err := (&Service{Store: st, BootID: "b"}).Resume(); err == nil {
		t.Fatal("resume went on past a corrupt record")
	}
}

func TestActivationListener(t *testing.T) {
	env := map[string]string{}
	get := func(k string) string { return env[k] }
	if l, err := ActivationListener(get, 42, 3); l != nil || err != nil {
		t.Fatalf("not activated: %v %v", l, err)
	}
	dir, err := shortTempDir(t)
	if err != nil {
		t.Fatal(err)
	}
	ul, err := net.ListenUnix("unix", &net.UnixAddr{Name: filepath.Join(dir, "a.sock"), Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	defer ul.Close()
	f, err := ul.File()
	if err != nil {
		t.Fatal(err)
	}
	env["LISTEN_PID"], env["LISTEN_FDS"] = "42", "2"
	if _, err := ActivationListener(get, 42, f.Fd()); err == nil {
		t.Fatal("two sockets accepted")
	}
	env["LISTEN_FDS"] = "1"
	l, err := ActivationListener(get, 42, f.Fd())
	if err != nil || l == nil {
		t.Fatalf("activated: %v", err)
	}
	l.Close()
}
