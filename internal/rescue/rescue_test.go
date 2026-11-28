// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

const ownerToken = "test-owner-token-not-a-secret"

// raucJSON is `rauc status --output-format=json` for a box booted from slot B.
const raucJSON = `{"compatible":"onemind-x86","booted":"B","boot_primary":"rootfs.1","slots":[
{"rootfs.0":{"class":"rootfs","bootname":"A","state":"inactive","boot_status":"good","slot_status":{"bundle":{"version":"0.4.0"}}}},
{"rootfs.1":{"class":"rootfs","bootname":"B","state":"booted","boot_status":"good","slot_status":{"bundle":{"version":"0.5.0"}}}}]}`

// fakeRunner records every command and answers like a box whose k3s is stopped.
type fakeRunner struct {
	mu    sync.Mutex
	calls []string
	logs  []byte
}

func (f *fakeRunner) Run(_ context.Context, name string, args ...string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	line := name + " " + strings.Join(args, " ")
	f.calls = append(f.calls, line)
	switch {
	case line == "rauc status --output-format=json":
		return []byte(raucJSON), nil
	case strings.HasPrefix(line, "systemctl is-active"):
		return []byte("inactive\ninactive\n"), &exitErr{}
	case name == "journalctl":
		return f.logs, nil
	}
	return nil, nil
}

func (f *fakeRunner) ran(prefix string) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, c := range f.calls {
		if strings.HasPrefix(c, prefix) {
			return true
		}
	}
	return false
}

type exitErr struct{}

func (*exitErr) Error() string { return "exit status 3" }

func tokensFile(t *testing.T, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "tokens.yaml")
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func hashedOwner() string {
	d := sha256.Sum256([]byte(ownerToken))
	return "tokens:\n  \"sha256:" + hex.EncodeToString(d[:]) + "\": {id: owner, kind: person, role: owner}\n" +
		"  \"sha256:" + strings.Repeat("ab", 32) + "\": {id: hermes, kind: agent, role: agent}\n"
}

func newServer(t *testing.T, tokens string) (*Server, *fakeRunner) {
	t.Helper()
	f := &fakeRunner{}
	return New(Config{TokensFile: tokensFile(t, tokens), Version: "0.5.0-test", Runner: f}), f
}

func do(s *Server, method, path, token string, form url.Values) *httptest.ResponseRecorder {
	var body *strings.Reader
	if form != nil {
		body = strings.NewReader(form.Encode())
	} else {
		body = strings.NewReader("")
	}
	r := httptest.NewRequest(method, path, body)
	r.RemoteAddr = "[fd00::20]:50000" // a LAN client (ULA, fc00::/7)
	if form != nil {
		r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	}
	if token != "" {
		r.SetBasicAuth("owner", token)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}

// The issue's Done-when: with k3s stopped, the owner rolls back through the console.
func TestOwnerRollsBackWithK3sStopped(t *testing.T) {
	s, f := newServer(t, hashedOwner())

	w := do(s, "GET", "/status.json", ownerToken, nil)
	if w.Code != 200 {
		t.Fatalf("status = %d %s", w.Code, w.Body)
	}
	var st Status
	if err := json.Unmarshal(w.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.K3s["k3s.service"] != "inactive" || st.RAUC.BootedSlot == nil || *st.RAUC.BootedSlot != "B" ||
		len(st.RAUC.Slots) != 2 || st.RAUC.Slots[0].BundleVersion != "0.4.0" || st.Version != "0.5.0-test" {
		t.Fatalf("status = %+v", st)
	}
	if page := do(s, "GET", "/", ownerToken, nil); page.Code != 200 || !strings.Contains(page.Body.String(), "0.4.0") ||
		!strings.Contains(page.Body.String(), st.CSRF) {
		t.Fatalf("page = %d %s", page.Code, page.Body)
	}

	w = do(s, "POST", "/rollback", ownerToken, url.Values{"csrf": {st.CSRF}, "confirm": {"rollback"}})
	if w.Code != 200 {
		t.Fatalf("rollback = %d %s", w.Code, w.Body)
	}
	if !f.ran("rauc status mark-active other") || !f.ran("systemctl reboot") {
		t.Fatalf("calls = %v", f.calls)
	}
	if f.calls[len(f.calls)-2] != "rauc status mark-active other" || f.calls[len(f.calls)-1] != "systemctl reboot" {
		t.Fatalf("mark-active must come before reboot: %v", f.calls)
	}
}

func TestRefusedRequestsRunNothing(t *testing.T) {
	s, f := newServer(t, hashedOwner())
	csrf := s.csrf
	ok := url.Values{"csrf": {csrf}, "confirm": {"rollback"}}
	agentHashOnly := strings.Repeat("ab", 32) // only the hash is known; an agent never passes anyway
	cases := []struct {
		name, method, path, token string
		form                      url.Values
		code                      int
	}{
		{"no credential", "POST", "/rollback", "", ok, 401},
		{"wrong credential", "POST", "/rollback", "wrong", ok, 401},
		{"agent hash as token", "POST", "/rollback", agentHashOnly, ok, 401},
		{"GET cannot roll back", "GET", "/rollback", ownerToken, nil, 405},
		{"no csrf", "POST", "/rollback", ownerToken, url.Values{"confirm": {"rollback"}}, 403},
		{"no confirmation", "POST", "/rollback", ownerToken, url.Values{"csrf": {csrf}}, 403},
	}
	for _, c := range cases {
		if w := do(s, c.method, c.path, c.token, c.form); w.Code != c.code {
			t.Errorf("%s: code = %d, want %d", c.name, w.Code, c.code)
		}
	}
	if len(f.calls) != 0 {
		t.Fatalf("refused requests ran commands: %v", f.calls)
	}
}

func TestCrossSiteOriginRefused(t *testing.T) {
	s, f := newServer(t, hashedOwner())
	form := url.Values{"csrf": {s.csrf}, "confirm": {"rollback"}}
	r := httptest.NewRequest("POST", "/rollback", strings.NewReader(form.Encode()))
	r.RemoteAddr = "[fd00::20]:1"
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Origin", "https://evil.example")
	r.Header.Set("Authorization", "Bearer "+ownerToken)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 403 || len(f.calls) != 0 {
		t.Fatalf("code %d calls %v", w.Code, f.calls)
	}
}

func TestNoOwnerConfiguredRefuses(t *testing.T) {
	agentOnly := "tokens:\n  - {token: " + ownerToken + ", id: bot, kind: agent, role: agent}\n"
	for name, tokens := range map[string]string{"agent only": agentOnly, "empty": "tokens: {}\n"} {
		s, f := newServer(t, tokens)
		if w := do(s, "GET", "/status.json", ownerToken, nil); w.Code != 503 || len(f.calls) != 0 {
			t.Errorf("%s: code %d calls %v", name, w.Code, f.calls)
		}
	}
	s := New(Config{TokensFile: filepath.Join(t.TempDir(), "missing.yaml"), Runner: &fakeRunner{}})
	if w := do(s, "GET", "/", ownerToken, nil); w.Code != 503 {
		t.Errorf("missing file: code %d", w.Code)
	}
}

func TestListShapeAndBearer(t *testing.T) {
	s, _ := newServer(t, "tokens:\n  - {token: "+ownerToken+", id: owner, kind: person, role: owner}\n")
	r := httptest.NewRequest("GET", "/status.json", nil)
	r.RemoteAddr = "[fe80::1]:1"
	r.Header.Set("Authorization", "Bearer "+ownerToken)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatalf("code %d", w.Code)
	}
}

func TestRateLimit(t *testing.T) {
	s, _ := newServer(t, hashedOwner())
	now := time.Unix(1_800_000_000, 0)
	s.lim.now = func() time.Time { return now }
	for range 5 {
		do(s, "GET", "/", "wrong", nil)
	}
	if w := do(s, "GET", "/", ownerToken, nil); w.Code != 429 {
		t.Fatalf("after 5 failures code = %d, want 429", w.Code)
	}
	now = now.Add(61 * time.Second)
	if w := do(s, "GET", "/", ownerToken, nil); w.Code != 200 {
		t.Fatalf("after the window code = %d", w.Code)
	}
}

func TestLANOnly(t *testing.T) {
	refused := []string{
		"198.51.100.7:1",             // TEST-NET-2: a public address
		"100.64.0.5:1",               // mesh CGNAT range
		"[fd7a:115c:a1e0::5]:1",      // mesh IPv6 (inside fc00::/7, which Go calls private)
		"[fd7a:115c:a1e0:ab12::1]:1", // anywhere in the mesh /48
	}
	for _, addr := range refused {
		s, f := newServer(t, hashedOwner())
		r := httptest.NewRequest("GET", "/", nil)
		r.RemoteAddr = addr
		r.SetBasicAuth("owner", ownerToken)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 403 || len(f.calls) != 0 {
			t.Fatalf("%s: code %d calls %v", addr, w.Code, f.calls)
		}
	}
	// Other private and link-local addresses on the LAN still get the page.
	for _, addr := range []string{"[fd00::7]:1", "[fe80::1]:1", "10.0.0.7:1"} {
		s, _ := newServer(t, hashedOwner())
		r := httptest.NewRequest("GET", "/", nil)
		r.RemoteAddr = addr
		r.SetBasicAuth("owner", ownerToken)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 200 {
			t.Fatalf("%s: LAN client refused with %d", addr, w.Code)
		}
	}
}

func TestLogsBounded(t *testing.T) {
	s, f := newServer(t, hashedOwner())
	f.logs = bytes.Repeat([]byte("x"), MaxLogBytes+12345)
	w := do(s, "GET", "/logs", ownerToken, nil)
	if w.Code != 200 || w.Body.Len() != MaxLogBytes {
		t.Fatalf("code %d len %d", w.Code, w.Body.Len())
	}
	if !strings.Contains(w.Header().Get("Content-Disposition"), "attachment") {
		t.Fatal("logs should download as a file")
	}
	if !f.ran("journalctl --no-pager") || !f.ran("journalctl --no-pager -o short-iso -n 5000 -u onemindd.service") {
		t.Fatalf("calls %v", f.calls)
	}
	var c capped
	_, _ = c.Write(bytes.Repeat([]byte("y"), MaxLogBytes+1))
	if n, _ := c.Write([]byte("z")); n != 1 || c.Len() != MaxLogBytes {
		t.Fatalf("capped writer len %d", c.Len())
	}
}

// VM 501 bug 1: "Reset k3s state" is an owner POST with the page's CSRF token and a typed confirmation, and all
// it does is start the reset unit (the console's sandbox is read-only; nothing runs without approval).
func TestResetK3sNeedsApprovalThenStartsTheUnit(t *testing.T) {
	s, f := newServer(t, hashedOwner())
	csrf := do(s, "GET", "/status.json", ownerToken, nil)
	var st Status
	if err := json.Unmarshal(csrf.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if page := do(s, "GET", "/", ownerToken, nil); !strings.Contains(page.Body.String(), "Reset k3s state") {
		t.Fatalf("page has no reset action: %s", page.Body)
	}
	for _, c := range []struct {
		name   string
		method string
		tok    string
		form   url.Values
		want   int
	}{
		{"no credential", "POST", "", url.Values{"csrf": {st.CSRF}, "confirm": {"reset k3s"}}, 401},
		{"wrong credential", "POST", "wrong", url.Values{"csrf": {st.CSRF}, "confirm": {"reset k3s"}}, 401},
		{"GET cannot reset", "GET", ownerToken, nil, 405},
		{"no csrf", "POST", ownerToken, url.Values{"confirm": {"reset k3s"}}, 403},
		{"no confirmation", "POST", ownerToken, url.Values{"csrf": {st.CSRF}}, 403},
		{"wrong confirmation", "POST", ownerToken, url.Values{"csrf": {st.CSRF}, "confirm": {"rollback"}}, 403},
	} {
		if w := do(s, c.method, "/reset-k3s", c.tok, c.form); w.Code != c.want {
			t.Errorf("%s: %d, want %d", c.name, w.Code, c.want)
		}
	}
	if f.ran("systemctl start") {
		t.Fatalf("a refused request started something: %v", f.calls)
	}
	w := do(s, "POST", "/reset-k3s", ownerToken, url.Values{"csrf": {st.CSRF}, "confirm": {" Reset  K3S "}})
	if w.Code != 200 || !f.ran("systemctl start --no-block onemind-k3s-reset.service") {
		t.Fatalf("approved reset = %d %s, calls %v", w.Code, w.Body, f.calls)
	}
	if f.ran("rauc status mark-active") || f.ran("systemctl reboot") {
		t.Fatalf("a k3s reset must not touch the slots or reboot: %v", f.calls)
	}
	// Nothing in the OS installs apps again after a reset (PR #1155 review): the page and the reply say so.
	if !strings.Contains(w.Body.String(), "install your apps again") {
		t.Fatalf("the reply must tell the owner to install apps again: %s", w.Body)
	}
	page := do(s, "GET", "/", ownerToken, nil).Body.String()
	if !strings.Contains(page, "install them again once k3s is back") || strings.Contains(page, "set up again by the gateway") {
		t.Fatalf("the page must not promise that apps come back on their own: %s", page)
	}
}

func TestStatusShowsTheLastK3sRepair(t *testing.T) {
	s, _ := newServer(t, hashedOwner())
	file := filepath.Join(t.TempDir(), "last.json")
	if err := os.WriteFile(file, []byte(`{"action":"needs-approval","at":"2026-11-25T12:00:00Z","reason":"the datastore holds the owner's apps"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	s.cfg.K3sRecoveryFile = file
	var st Status
	if err := json.Unmarshal(do(s, "GET", "/status.json", ownerToken, nil).Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.K3sRecovery == nil || st.K3sRecovery.Action != "needs-approval" {
		t.Fatalf("k3s_recovery = %+v", st.K3sRecovery)
	}
	if page := do(s, "GET", "/", ownerToken, nil).Body.String(); !strings.Contains(page, "needs-approval") || !strings.Contains(page, `role="alert"`) ||
		!strings.Contains(page, "k3s is held (not started) until you decide") {
		t.Fatalf("page does not show the repair that waits for the owner: %s", page)
	}
	s.cfg.K3sRecoveryFile = filepath.Join(t.TempDir(), "none.json")
	if do(s, "GET", "/status.json", ownerToken, nil).Body.String() == "" || s.k3sRecovery() != nil {
		t.Fatalf("no record must show nothing")
	}
}
