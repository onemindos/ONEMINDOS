// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

const agentToken = "test-agent-token-not-a-secret"

func tokensWithAgent() string {
	o, a := sha256.Sum256([]byte(ownerToken)), sha256.Sum256([]byte(agentToken))
	return "tokens:\n  \"sha256:" + hex.EncodeToString(o[:]) + "\": {id: owner, kind: person, role: owner}\n" +
		"  \"sha256:" + hex.EncodeToString(a[:]) + "\": {id: hermes, kind: agent, role: agent}\n"
}

// pipeSession is a shell stand-in: what is written is echoed back, uppercased.
type pipeSession struct {
	r, w   *io.PipeReader
	pw     *io.PipeWriter
	done   chan struct{}
	once   sync.Once
	mu     sync.Mutex
	gotIn  bytes.Buffer
	closed bool
}

func newPipeSession() *pipeSession {
	r, w := io.Pipe()
	return &pipeSession{r: r, pw: w, done: make(chan struct{})}
}

func (p *pipeSession) Read(b []byte) (int, error) { return p.r.Read(b) }
func (p *pipeSession) Write(b []byte) (int, error) {
	p.mu.Lock()
	p.gotIn.Write(b)
	p.mu.Unlock()
	up := []byte(strings.ToUpper(string(b)))
	go func() { _, _ = p.pw.Write(up) }() // a shell does not block its typist
	return len(b), nil
}
func (p *pipeSession) Done() <-chan struct{} { return p.done }
func (p *pipeSession) Close() error {
	p.once.Do(func() { p.pw.Close(); p.r.Close(); close(p.done) })
	return nil
}
func (p *pipeSession) exit() { p.Close() }

type fakeSpawner struct {
	mu    sync.Mutex
	n     int
	last  *pipeSession
	fails bool
}

func (f *fakeSpawner) Spawn() (Session, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.fails {
		return nil, errors.New("no pty")
	}
	f.n++
	f.last = newPipeSession()
	return f.last, nil
}

func (f *fakeSpawner) count() int { f.mu.Lock(); defer f.mu.Unlock(); return f.n }

type fakeReauth struct{ err error }

func (f fakeReauth) Fresh(*http.Request) (string, error) { return "passkey-abc", f.err }

type termEnv struct {
	srv     *Server
	ts      *httptest.Server
	spawn   *fakeSpawner
	audit   string
	switch_ string
}

func newTermEnv(t *testing.T, mod func(*Terminal)) *termEnv {
	t.Helper()
	dir := t.TempDir()
	e := &termEnv{spawn: &fakeSpawner{}, audit: filepath.Join(dir, "audit.jsonl"), switch_: filepath.Join(dir, "terminal.on")}
	au, err := OpenAudit(e.audit, nil)
	if err != nil {
		t.Fatal(err)
	}
	term := &Terminal{SwitchFile: e.switch_, Reauth: fakeReauth{}, Spawner: e.spawn, Audit: au,
		IdleTimeout: time.Minute, MaxDuration: time.Hour}
	if mod != nil {
		mod(term)
	}
	e.srv = New(Config{TokensFile: tokensFile(t, tokensWithAgent()), Version: "t", Runner: &fakeRunner{}, Terminal: term})
	e.ts = httptest.NewServer(e.srv)
	t.Cleanup(e.ts.Close)
	return e
}

func (e *termEnv) on(t *testing.T) {
	t.Helper()
	if err := os.WriteFile(e.switch_, []byte("on\n"), 0o600); err != nil {
		t.Fatal(err)
	}
}

func (e *termEnv) req(t *testing.T, method, path, token string, csrf bool, body string) *http.Response {
	t.Helper()
	r, _ := http.NewRequest(method, e.ts.URL+path, strings.NewReader(body))
	if token != "" {
		r.SetBasicAuth("x", token)
	}
	if csrf {
		r.Header.Set("X-CSRF-Token", e.srv.csrf)
	}
	resp, err := http.DefaultClient.Do(r)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { resp.Body.Close() })
	return resp
}

func (e *termEnv) events(t *testing.T) []map[string]any {
	t.Helper()
	b, _ := os.ReadFile(e.audit)
	var out []map[string]any
	for _, l := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		if l == "" {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal([]byte(l), &m); err != nil {
			t.Fatal(err)
		}
		out = append(out, m)
	}
	return out
}

func (e *termEnv) eventNames(t *testing.T) []string {
	var n []string
	for _, m := range e.events(t) {
		n = append(n, m["event"].(string))
	}
	return n
}

func waitFor(t *testing.T, what string, ok func() bool) {
	t.Helper()
	for i := 0; i < 200; i++ {
		if ok() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", what)
}

func (e *termEnv) start(t *testing.T) string {
	t.Helper()
	resp := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "")
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("start = %d %s", resp.StatusCode, b)
	}
	var v map[string]string
	_ = json.NewDecoder(resp.Body).Decode(&v)
	return v["id"]
}

// Done when: an agent token gets 403 (and no shell, and a denial on the chain).
func TestAgentTokenGets403(t *testing.T) {
	e := newTermEnv(t, nil)
	e.on(t)
	for _, c := range []struct{ m, p string }{{"GET", "/terminal"}, {"POST", "/terminal/sessions"},
		{"GET", "/terminal/sessions/x/out"}, {"POST", "/terminal/sessions/x/in"}} {
		if got := e.req(t, c.m, c.p, agentToken, true, "ls").StatusCode; got != 403 {
			t.Errorf("agent %s %s = %d, want 403", c.m, c.p, got)
		}
	}
	if e.spawn.count() != 0 {
		t.Fatal("an agent token opened a shell")
	}
	if names := e.eventNames(t); len(names) == 0 || names[0] != "terminal.denied" {
		t.Fatalf("audit = %v", names)
	}
}

// Done when: a non-owner gets 403, and anyone without a credential or with a wrong one gets 401.
func TestNonOwnerPersonGets403AndStrangersGet401(t *testing.T) {
	d := sha256.Sum256([]byte("member-token"))
	toks := tokensWithAgent() + "  \"sha256:" + hex.EncodeToString(d[:]) + "\": {id: guest, kind: person, role: member}\n"
	e := newTermEnv(t, nil)
	e.srv.cfg.TokensFile = tokensFile(t, toks)
	e.on(t)
	if got := e.req(t, "GET", "/terminal", "member-token", true, "").StatusCode; got != 403 {
		t.Errorf("member = %d, want 403", got)
	}
	if got := e.req(t, "GET", "/terminal", "", true, "").StatusCode; got != 401 {
		t.Errorf("anonymous = %d, want 401", got)
	}
	if got := e.req(t, "GET", "/terminal", "nope", true, "").StatusCode; got != 401 {
		t.Errorf("wrong token = %d, want 401", got)
	}
	if e.spawn.count() != 0 {
		t.Fatal("a shell opened")
	}
}

func TestOffByDefaultAndWithoutPasskeyNoShell(t *testing.T) {
	e := newTermEnv(t, nil) // switch file absent
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "").StatusCode; got != 404 {
		t.Errorf("switch off = %d, want 404", got)
	}
	if err := os.WriteFile(e.switch_, nil, 0o666); err != nil { // writable by others: does not count
		t.Fatal(err)
	}
	_ = os.Chmod(e.switch_, 0o666)
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "").StatusCode; got != 404 {
		t.Errorf("world-writable switch = %d, want 404", got)
	}
	_ = os.Chmod(e.switch_, 0o600)
	e.srv.cfg.Terminal.Reauth = nil // what production runs today: no passkeys yet
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "").StatusCode; got != 503 {
		t.Errorf("no passkey support = %d, want 503", got)
	}
	e.srv.cfg.Terminal.Reauth = fakeReauth{err: errors.New("stale")}
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "").StatusCode; got != 401 {
		t.Errorf("stale passkey = %d, want 401", got)
	}
	if e.spawn.count() != 0 || len(e.events(t)) != 0 {
		t.Fatalf("a refused start left a shell or a chain entry: spawned=%d events=%v", e.spawn.count(), e.eventNames(t))
	}
}

func TestUnmountedWhenNotConfigured(t *testing.T) {
	s, _ := newServer(t, hashedOwner())
	if got := do(s, "GET", "/terminal", ownerToken, nil).Code; got != 404 {
		t.Fatalf("unmounted terminal = %d, want 404", got)
	}
	if strings.Contains(do(s, "GET", "/", ownerToken, nil).Body.String(), "/terminal") {
		t.Fatal("page links to a terminal that is not mounted")
	}
}

// Done when: every session produces an audit entry (start and end), the chain verifies, and no keystrokes are in it.
func TestSessionIsAuditedAndKeystrokesAreNot(t *testing.T) {
	e := newTermEnv(t, nil)
	e.on(t)
	id := e.start(t)
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "").StatusCode; got != 409 {
		t.Errorf("second session = %d, want 409", got)
	}
	secret := "hunter2-never-in-the-chain"
	if got := e.req(t, "POST", "/terminal/sessions/"+id+"/in", ownerToken, true, secret).StatusCode; got != 204 {
		t.Fatalf("in = %d", got)
	}
	out := e.req(t, "GET", "/terminal/sessions/"+id+"/out", ownerToken, true, "")
	buf := make([]byte, 64)
	n, _ := out.Body.Read(buf)
	if got := string(buf[:n]); got != strings.ToUpper(secret) {
		t.Fatalf("out = %q", got)
	}
	if got := e.req(t, "POST", "/terminal/sessions/"+id+"/close", ownerToken, true, "").StatusCode; got != 204 {
		t.Fatalf("close = %d", got)
	}
	waitFor(t, "end line", func() bool { return len(e.events(t)) == 2 })
	ev := e.events(t)
	if ev[0]["event"] != "terminal.start" || ev[1]["event"] != "terminal.end" {
		t.Fatalf("events = %v", e.eventNames(t))
	}
	d0, d1 := ev[0]["data"].(map[string]any), ev[1]["data"].(map[string]any)
	if d0["session"] != id || d0["credential"] != "passkey-abc" || d0["client"] != "127.0.0.1" {
		t.Errorf("start data = %v", d0)
	}
	if d1["reason"] != "owner-closed" || d1["bytes_in"].(float64) != float64(len(secret)) {
		t.Errorf("end data = %v", d1)
	}
	if ev[0]["principal"].(map[string]any)["role"] != "owner" {
		t.Errorf("principal = %v", ev[0]["principal"])
	}
	raw, _ := os.ReadFile(e.audit)
	if bytes.Contains(raw, []byte(secret)) || bytes.Contains(raw, []byte(strings.ToUpper(secret))) {
		t.Fatal("keystrokes or output reached the audit chain")
	}
	if n, _, err := verifyAuditFile(e.audit); err != nil || n != 2 {
		t.Fatalf("chain: n=%d err=%v", n, err)
	}
	if st, _ := os.Stat(e.audit); st.Mode().Perm() != 0o600 {
		t.Errorf("audit mode = %v", st.Mode().Perm())
	}
}

func TestShellExitAndIdleTimeoutAreAudited(t *testing.T) {
	e := newTermEnv(t, func(tm *Terminal) { tm.IdleTimeout = 80 * time.Millisecond })
	e.on(t)
	e.start(t)
	e.spawn.last.exit()
	waitFor(t, "shell-exited", func() bool { return len(e.events(t)) == 2 })
	if r := e.events(t)[1]["data"].(map[string]any)["reason"]; r != "shell-exited" {
		t.Fatalf("reason = %v", r)
	}
	e.start(t) // the slot is free again; nobody types
	waitFor(t, "idle end", func() bool { return len(e.events(t)) == 4 })
	if r := e.events(t)[3]["data"].(map[string]any)["reason"]; r != "idle-timeout" {
		t.Fatalf("reason = %v", r)
	}
}

func TestNoAuditNoShell(t *testing.T) {
	e := newTermEnv(t, nil)
	e.on(t)
	e.srv.cfg.Terminal.Audit.path = filepath.Join(t.TempDir(), "missing-dir", "audit.jsonl")
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, true, "").StatusCode; got != 500 {
		t.Fatalf("start with an unwritable chain = %d, want 500", got)
	}
	if e.spawn.count() != 0 {
		t.Fatal("a shell opened without a start record")
	}
}

func TestStartNeedsTheCSRFToken(t *testing.T) {
	e := newTermEnv(t, nil)
	e.on(t)
	if got := e.req(t, "POST", "/terminal/sessions", ownerToken, false, "").StatusCode; got != 403 {
		t.Fatalf("no csrf = %d, want 403", got)
	}
	if e.spawn.count() != 0 {
		t.Fatal("a shell opened without the csrf token")
	}
}

func TestPageHasNonceCSPAndOffer(t *testing.T) {
	e := newTermEnv(t, nil)
	e.on(t)
	resp := e.req(t, "GET", "/terminal", ownerToken, false, "")
	b, _ := io.ReadAll(resp.Body)
	csp := resp.Header.Get("Content-Security-Policy")
	if resp.StatusCode != 200 || !strings.Contains(csp, "script-src 'nonce-") || strings.Contains(csp, "unsafe-eval") ||
		!strings.Contains(string(b), "nonce=\""+strings.TrimSuffix(strings.SplitN(csp, "'nonce-", 2)[1], "'; connect-src 'self'; frame-ancestors 'none'")+"\"") {
		t.Fatalf("page = %d csp=%q", resp.StatusCode, csp)
	}
	main := e.req(t, "GET", "/", ownerToken, false, "")
	mb, _ := io.ReadAll(main.Body)
	if !strings.Contains(string(mb), `href="terminal"`) {
		t.Fatal("the console page does not offer the terminal when it is on")
	}
}

// The gateway's agent surface must not contain a terminal: it exists only in the rescue process.
func TestNoTerminalInTheGatewaySurface(t *testing.T) {
	root := filepath.Join("..", "..")
	for _, f := range []string{"sdk/openapi/onemind-v1.json"} {
		if b, err := os.ReadFile(filepath.Join(root, f)); err == nil && bytes.Contains(bytes.ToLower(b), []byte("terminal")) {
			t.Errorf("%s mentions a terminal", f)
		}
	}
	out, err := exec.Command("grep", "-rli", "--include=*.py", "-e", "pty.spawn", "-e", "/terminal", filepath.Join(root, "core", "onemind_core")).Output()
	if err == nil && len(bytes.TrimSpace(out)) > 0 {
		t.Errorf("the gateway code references a terminal route or pty: %s", out)
	}
}

func TestAuditChainFormatMatchesTheGatewaysVerifier(t *testing.T) {
	py, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("no python3")
	}
	p := filepath.Join(t.TempDir(), "a.jsonl")
	a, err := OpenAudit(p, nil)
	if err != nil {
		t.Fatal(err)
	}
	_ = a.Append("terminal.start", ownerPrincipal, map[string]any{"session": "s", "note": "a<b>&c é  ", "n": 3})
	_ = a.Append("terminal.end", ownerPrincipal, map[string]any{"session": "s", "reason": "x"})
	// reopen: the chain continues from the file
	a2, err := OpenAudit(p, nil)
	if err != nil {
		t.Fatal(err)
	}
	_ = a2.Append("terminal.switch", map[string]any{"kind": "local"}, nil)
	cmd := exec.Command(py, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import importlib.util as u; "+
		"s=u.spec_from_file_location('audit', sys.argv[1]+'/onemind_core/audit.py'); m=u.module_from_spec(s); s.loader.exec_module(m); "+
		"import pathlib; ok,n,r=m.verify(pathlib.Path(sys.argv[2])); print(ok,n,r); sys.exit(0 if ok and n==3 else 1)",
		filepath.Join("..", "..", "core"), p)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("the gateway's verify rejects our chain: %v\n%s", err, out)
	}
	// tampering is detected
	b, _ := os.ReadFile(p)
	if err := os.WriteFile(p, bytes.Replace(b, []byte(`"reason":"x"`), []byte(`"reason":"y"`), 1), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := OpenAudit(p, nil); err == nil {
		t.Fatal("a tampered chain was accepted")
	}
}
