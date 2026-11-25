// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

const owner2Token = "second-owner-token-not-a-secret"

// fakeGateway stands in for the gateway's /v1/auth/rescue/* calls and records what it was sent.
type fakeGateway struct {
	mu       sync.Mutex
	options  int
	verifies int
	kits     int
	auth     []string
	hosts    []string
	bodies   []string
	verify   func(cred map[string]any) (int, string)
}

func (g *fakeGateway) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	g.mu.Lock()
	defer g.mu.Unlock()
	b, _ := io.ReadAll(r.Body)
	g.auth = append(g.auth, r.Header.Get("Authorization"))
	g.hosts = append(g.hosts, r.Host)
	g.bodies = append(g.bodies, string(b))
	switch r.URL.Path {
	case "/v1/auth/rescue/options":
		g.options++
		_, _ = w.Write([]byte(`{"challenge_id":"chl_1","publicKey":{"challenge":"AAAAAAAAAAAAAAAAAAAAAA","userVerification":"required"}}`))
	case "/v1/auth/rescue/kit":
		g.kits++
		var in struct {
			KitKey string `json:"kit_key"`
		}
		_ = json.Unmarshal(b, &in)
		if in.KitKey != "KIT-KEY-FOR-TESTS" {
			w.WriteHeader(401)
			_, _ = w.Write([]byte(`{"error":"unauthenticated","reason":"kit_key_wrong"}`))
			return
		}
		_, _ = w.Write([]byte(`{"credential_id":"kit:abc123","user_id":"usr_1"}`))
	case "/v1/auth/rescue/verify":
		g.verifies++
		var in struct {
			Credential map[string]any `json:"credential"`
		}
		_ = json.Unmarshal(b, &in)
		code, body := g.verify(in.Credential)
		w.WriteHeader(code)
		_, _ = w.Write([]byte(body))
	default:
		http.NotFound(w, r)
	}
}

func (g *fakeGateway) counts() (int, int) {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.options, g.verifies
}

// acceptOnce models the gateway's single-use challenge: the first assertion verifies, a replay does not.
func acceptOnce() func(map[string]any) (int, string) {
	used := false
	return func(c map[string]any) (int, string) {
		if used || c["id"] != "cred-1" {
			return 401, `{"error":"unauthenticated"}`
		}
		used = true
		return 200, `{"credential_id":"cred-1","user_id":"usr_1"}`
	}
}

type pkEnv struct {
	*termEnv
	gw *fakeGateway
}

func newPkEnv(t *testing.T, verify func(map[string]any) (int, string)) *pkEnv {
	t.Helper()
	gw := &fakeGateway{verify: verify}
	gs := httptest.NewServer(gw)
	t.Cleanup(gs.Close)
	re, err := NewGatewayReauth(gs.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	e := newTermEnv(t, func(tm *Terminal) { tm.Reauth = re })
	// two owners, so a session can be tried with a credential that did not start it
	o2 := sha256.Sum256([]byte(owner2Token))
	tf := tokensFile(t, tokensWithAgent()+"  \"sha256:"+hex.EncodeToString(o2[:])+"\": {id: owner2, kind: person, role: owner}\n")
	e.srv.cfg.TokensFile = tf
	e.on(t)
	return &pkEnv{e, gw}
}

const assertion = `{"webauthn":{"id":"cred-1","type":"public-key","response":{"clientDataJSON":"x","authenticatorData":"y","signature":"z"}}}`

func (e *pkEnv) startWith(t *testing.T, token, body string) *http.Response {
	t.Helper()
	r, _ := http.NewRequest("POST", e.ts.URL+"/terminal/sessions", strings.NewReader(body))
	r.SetBasicAuth("x", token)
	r.Header.Set("X-CSRF-Token", e.srv.csrf)
	r.Host = "onemind.local:7443"
	resp, err := http.DefaultClient.Do(r)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { resp.Body.Close() })
	return resp
}

func TestGatewayReauthOnlyTalksToLoopback(t *testing.T) {
	for _, bad := range []string{"http://198.51.100.7:8080", "https://example.com", "http://203.0.113.9", "ftp://127.0.0.1", "", "http://127.0.0.1.evil.example"} {
		if _, err := NewGatewayReauth(bad, nil); err == nil {
			t.Errorf("%q accepted: the owner token could leave the box", bad)
		}
	}
	for _, ok := range []string{"http://127.0.0.1:8080", "http://localhost:8080", "https://[::1]:8443"} {
		if _, err := NewGatewayReauth(ok, nil); err != nil {
			t.Errorf("%q refused: %v", ok, err)
		}
	}
}

// Done when: the terminal opens only after the gateway accepts a fresh owner passkey assertion.
func TestShellOpensOnlyAfterAGatewayVerifiedAssertion(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	for name, body := range map[string]string{"no body": "", "no assertion": `{}`, "not json": "x", "empty assertion": `{"webauthn":{}}`} {
		if got := e.startWith(t, ownerToken, body).StatusCode; got != 401 {
			t.Errorf("%s = %d, want 401", name, got)
		}
	}
	if _, v := e.gw.counts(); v != 0 {
		t.Errorf("the gateway was asked %d times about assertions that were never sent", v)
	}
	bad := strings.Replace(assertion, "cred-1", "other", 1)
	if got := e.startWith(t, ownerToken, bad).StatusCode; got != 401 {
		t.Errorf("assertion the gateway refuses = %d, want 401", got)
	}
	if e.spawn.count() != 0 || len(e.events(t)) != 0 {
		t.Fatalf("a refused start left a shell or a chain entry: spawned=%d %v", e.spawn.count(), e.eventNames(t))
	}
	resp := e.startWith(t, ownerToken, assertion)
	if resp.StatusCode != 200 || e.spawn.count() != 1 {
		t.Fatalf("verified start = %d spawned=%d", resp.StatusCode, e.spawn.count())
	}
	// The gateway got the owner's own credential and the browser's host (so it picks the right relying party).
	e.gw.mu.Lock()
	defer e.gw.mu.Unlock()
	last := len(e.gw.auth) - 1
	if e.gw.auth[last] != "Bearer "+ownerToken || e.gw.hosts[last] != "onemind.local:7443" {
		t.Errorf("gateway saw auth=%q host=%q", e.gw.auth[last], e.gw.hosts[last])
	}
	var sent map[string]map[string]any
	_ = json.Unmarshal([]byte(e.gw.bodies[last]), &sent)
	if sent["credential"]["id"] != "cred-1" {
		t.Errorf("verify body = %s", e.gw.bodies[last])
	}
	// The credential id the gateway verified is what lands on the chain.
	ev := e.events(t)
	if len(ev) != 1 || ev[0]["event"] != "terminal.start" || ev[0]["data"].(map[string]any)["credential"] != "cred-1" {
		t.Fatalf("chain = %v", ev)
	}
}

// Done when: an assertion is spent by one start; the same bytes replayed later open nothing.
func TestAReplayedAssertionOpensNoSecondShell(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	var v map[string]string
	_ = json.NewDecoder(e.startWith(t, ownerToken, assertion).Body).Decode(&v)
	if v["id"] == "" {
		t.Fatal("first start failed")
	}
	if got := e.req(t, "POST", "/terminal/sessions/"+v["id"]+"/close", ownerToken, true, "").StatusCode; got != 204 {
		t.Fatalf("close = %d", got)
	}
	waitFor(t, "end line", func() bool { return len(e.events(t)) == 2 })
	if got := e.startWith(t, ownerToken, assertion).StatusCode; got != 401 {
		t.Errorf("replay = %d, want 401", got)
	}
	if e.spawn.count() != 1 {
		t.Errorf("a replay spawned a shell (%d)", e.spawn.count())
	}
}

func TestGatewayDownOrBrokenMeansNoShell(t *testing.T) {
	e := newPkEnv(t, func(map[string]any) (int, string) { return 500, "boom" })
	if got := e.startWith(t, ownerToken, assertion).StatusCode; got != 503 {
		t.Errorf("gateway 500 = %d, want 503", got)
	}
	re, _ := NewGatewayReauth("http://127.0.0.1:1", nil) // nothing listens there
	e.srv.cfg.Terminal.Reauth = re
	if got := e.startWith(t, ownerToken, assertion).StatusCode; got != 503 {
		t.Errorf("gateway down = %d, want 503", got)
	}
	if e.spawn.count() != 0 || len(e.events(t)) != 0 {
		t.Fatalf("shell or chain entry without a passkey check: %d %v", e.spawn.count(), e.eventNames(t))
	}
}

// Done when: the passkey is asked once, at the start, and the open session is tied to the credential that started it.
func TestTheSessionNeedsNoFurtherAssertionButOnlyItsOwner(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	var v map[string]string
	_ = json.NewDecoder(e.startWith(t, ownerToken, assertion).Body).Decode(&v)
	id := v["id"]
	for i := 0; i < 3; i++ {
		if got := e.req(t, "POST", "/terminal/sessions/"+id+"/in", ownerToken, true, "ls\n").StatusCode; got != 204 {
			t.Fatalf("in = %d", got)
		}
	}
	if _, verifies := e.gw.counts(); verifies != 1 {
		t.Errorf("gateway verify calls = %d, want exactly 1 (at the start)", verifies)
	}
	// Another owner credential, a different CSRF-less caller, an agent: none can drive the session.
	if got := e.req(t, "POST", "/terminal/sessions/"+id+"/in", owner2Token, true, "id\n").StatusCode; got != 404 {
		t.Errorf("other owner token on the session = %d, want 404", got)
	}
	if got := e.req(t, "POST", "/terminal/sessions/"+id+"/in", agentToken, true, "id\n").StatusCode; got != 403 {
		t.Errorf("agent on the session = %d, want 403", got)
	}
	if got := e.req(t, "POST", "/terminal/sessions/"+id+"/close", owner2Token, true, "").StatusCode; got != 404 {
		t.Errorf("other owner closing = %d, want 404", got)
	}
	if got := e.req(t, "POST", "/terminal/sessions/"+id+"/in", ownerToken, false, "id\n").StatusCode; got != 403 {
		t.Errorf("no CSRF = %d, want 403", got)
	}
	ls := e.spawn.last
	ls.mu.Lock()
	got := ls.gotIn.String()
	ls.mu.Unlock()
	if got != "ls\nls\nls\n" {
		t.Errorf("shell input = %q", got)
	}
}

func TestChallengeRouteIsOwnerOnlyAndNeedsTheSwitch(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	post := func(path, token string, csrf bool) *http.Response { return e.req(t, "POST", path, token, csrf, "") }
	resp := post("/terminal/passkey/options", ownerToken, true)
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 || !strings.Contains(string(b), `"userVerification":"required"`) {
		t.Fatalf("options = %d %s", resp.StatusCode, b)
	}
	if o, _ := e.gw.counts(); o != 1 {
		t.Errorf("gateway options calls = %d", o)
	}
	if got := post("/terminal/passkey/options", agentToken, true).StatusCode; got != 403 {
		t.Errorf("agent = %d, want 403", got)
	}
	if got := post("/terminal/passkey/options", "", true).StatusCode; got != 401 {
		t.Errorf("anonymous = %d, want 401", got)
	}
	if got := post("/terminal/passkey/options", ownerToken, false).StatusCode; got != 403 {
		t.Errorf("no CSRF = %d, want 403", got)
	}
	_ = os.Remove(e.switch_)
	if got := post("/terminal/passkey/options", ownerToken, true).StatusCode; got != 404 {
		t.Errorf("switch off = %d, want 404", got)
	}
	e.on(t)
	e.srv.cfg.Terminal.Reauth = fakeReauth{} // no Challenger: nothing to sign
	if got := post("/terminal/passkey/options", ownerToken, true).StatusCode; got != 503 {
		t.Errorf("no challenger = %d, want 503", got)
	}
}

func TestPageSignsWithAPasskeyBeforeStarting(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	resp := e.req(t, "GET", "/terminal", ownerToken, false, "")
	b, _ := io.ReadAll(resp.Body)
	page := string(b)
	i, j, k := strings.Index(page, "terminal/passkey/options"), strings.Index(page, "navigator.credentials.get"), strings.Index(page, "fetch('terminal/sessions'")
	if resp.StatusCode != 200 || i < 0 || !(i < j && j < k) {
		t.Fatalf("page does not do options, then a passkey, then start (%d %d %d)", i, j, k)
	}
	if e.spawn.count() != 0 {
		t.Error("loading the page opened a shell")
	}
}

func TestGatewayReauthErrorsAreDistinct(t *testing.T) {
	gs := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(409) }))
	defer gs.Close()
	re, _ := NewGatewayReauth(gs.URL, &http.Client{Timeout: time.Second})
	r := httptest.NewRequest("POST", "/terminal/passkey/options", nil)
	r.Header.Set("Authorization", "Bearer "+ownerToken)
	if _, err := re.Challenge(r); !errors.Is(err, ErrNoPasskey) {
		t.Errorf("409 = %v, want ErrNoPasskey", err)
	}
}

// D-028: an owner who lost every passkey opens the terminal with the printed kit's owner key, at the box only.
func TestKitKeyOpensTheShellFromTheBoxItselfNeverFromTheLAN(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	const kit = `{"kit_key":"KIT-KEY-FOR-TESTS"}`
	if got := e.startWith(t, ownerToken, `{"kit_key":"wrong"}`).StatusCode; got != 401 {
		t.Errorf("wrong kit key = %d, want 401", got)
	}
	if got := e.startWith(t, ownerToken, `{"kit_key":"KIT-KEY-FOR-TESTS","webauthn":{"id":"cred-1"}}`).StatusCode; got != 401 {
		t.Errorf("both proofs at once = %d, want 401", got)
	}
	if e.spawn.count() != 0 || len(e.events(t)) != 0 {
		t.Fatalf("a refused kit start opened something: %d %v", e.spawn.count(), e.eventNames(t))
	}
	// a client that is not on the box never reaches the gateway's kit route
	kitsBefore := e.gw.kits
	r := httptest.NewRequest("POST", "/terminal/sessions", strings.NewReader(kit))
	r.RemoteAddr = "192.0.2.10:5555"
	r.Header.Set("Authorization", "Bearer "+ownerToken)
	if _, err := e.srv.cfg.Terminal.Reauth.Fresh(r); !errors.Is(err, ErrNoFreshAuth) {
		t.Errorf("LAN client with the kit key = %v, want ErrNoFreshAuth", err)
	}
	if e.gw.kits != kitsBefore {
		t.Error("a LAN client's kit key was forwarded to the gateway")
	}
	resp := e.startWith(t, ownerToken, kit) // the test server is on loopback
	if resp.StatusCode != 200 || e.spawn.count() != 1 {
		t.Fatalf("kit start at the box = %d spawned=%d", resp.StatusCode, e.spawn.count())
	}
	ev := e.events(t)
	if len(ev) != 1 || ev[0]["data"].(map[string]any)["credential"] != "kit:abc123" {
		t.Fatalf("chain = %v", ev)
	}
	if strings.Contains(string(mustRead(t, e.audit)), "KIT-KEY-FOR-TESTS") {
		t.Error("the kit key reached the audit chain")
	}
}

func TestPageOffersTheKitWhenThereIsNoPasskey(t *testing.T) {
	e := newPkEnv(t, acceptOnce())
	b, _ := io.ReadAll(e.req(t, "GET", "/terminal", ownerToken, false, "").Body)
	page := string(b)
	for _, want := range []string{`id="kit"`, "kit_key", "const atBox= true ", "printed emergency kit"} {
		if !strings.Contains(page, want) {
			t.Errorf("page lacks %q", want)
		}
	}
}

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return b
}
