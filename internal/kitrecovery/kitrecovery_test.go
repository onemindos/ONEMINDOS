// SPDX-License-Identifier: Apache-2.0

package kitrecovery

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type fakeGW struct {
	t     *testing.T
	calls []string
	sent  map[string]map[string]any
}

func (g *fakeGW) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("OneMind-Console") != "consolekey" {
		w.WriteHeader(403)
		return
	}
	var body map[string]any
	_ = json.NewDecoder(r.Body).Decode(&body)
	g.calls = append(g.calls, r.URL.Path)
	g.sent[r.URL.Path] = body
	if r.URL.Path != "/v1/auth/recovery/kit" && r.Header.Get("OneMind-Kit-Session") != "sess" {
		w.WriteHeader(401)
		_, _ = w.Write([]byte(`{"message":"ended","reason":"kit_session_ended"}`))
		return
	}
	switch r.URL.Path {
	case "/v1/auth/recovery/kit":
		if body["check"] == "BAD2" {
			w.WriteHeader(429)
			_, _ = w.Write([]byte(`{"message":"too many wrong kit keys","retry_after_s":900}`))
			return
		}
		_, _ = w.Write([]byte(`{"session":"sess","owners":[{"user_id":"usr_1","username":"zeus","display_name":"Zeus","authenticator":true,
			"passkeys":[{"credential_id":"c1","label":"lost phone"}]}]}`))
	case "/v1/auth/recovery/kit/sign-in-code":
		_, _ = w.Write([]byte(`{"code":"ABCD-EFGH-JKMN"}`))
	default:
		w.WriteHeader(204)
	}
}

func run(t *testing.T, input string) (string, *fakeGW, error) {
	t.Helper()
	g := &fakeGW{t: t, sent: map[string]map[string]any{}}
	srv := httptest.NewServer(g)
	t.Cleanup(srv.Close)
	key := filepath.Join(t.TempDir(), "console.key")
	_ = os.WriteFile(key, []byte("consolekey\n"), 0o600)
	var out strings.Builder
	c := &Console{Gateway: srv.URL, KeyFile: key, In: strings.NewReader(input), Out: &out}
	err := c.Run(context.Background())
	return out.String(), g, err
}

const kitKey = "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH-IIII-JJJJ-KKKK-LLLL-MMMM\n"

func TestConsoleRecoversAnOwner(t *testing.T) {
	in := kitKey + "wxyz\n" + "1\nnew passphrase!\nnew passphrase!\n" + "2\n" + "3\n1\n" + "4\n" + "5\n"
	out, g, err := run(t, in)
	if err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	want := []string{"/v1/auth/recovery/kit", "/v1/auth/recovery/kit/password", "/v1/auth/recovery/kit/authenticator/clear",
		"/v1/auth/recovery/kit/passkeys/remove", "/v1/auth/recovery/kit/sign-in-code"}
	if strings.Join(g.calls, " ") != strings.Join(want, " ") {
		t.Fatalf("calls %v", g.calls)
	}
	if g.sent["/v1/auth/recovery/kit"]["check"] != "WXYZ" || len(g.sent["/v1/auth/recovery/kit"]["groups"].([]any)) != 13 {
		t.Fatalf("kit sent %v", g.sent["/v1/auth/recovery/kit"])
	}
	if g.sent["/v1/auth/recovery/kit/passkeys/remove"]["credential_id"] != "c1" {
		t.Fatalf("removed %v", g.sent["/v1/auth/recovery/kit/passkeys/remove"])
	}
	if !strings.Contains(out, "ABCD-EFGH-JKMN") || strings.Contains(out, "AAAA-BBBB") || strings.Contains(out, "new passphrase") {
		t.Fatalf("shows the sign-in code, never the kit key or the password:\n%s", out)
	}
}

func TestConsoleRefusesShortKeysAndShowsTheWait(t *testing.T) {
	if _, g, err := run(t, "AAAA BBBB\n"); err == nil || len(g.calls) != 0 {
		t.Fatalf("a short key is refused before anything is sent: %v %v", err, g.calls)
	}
	_, _, err := run(t, kitKey+"bad2\n")
	if err == nil || !strings.Contains(err.Error(), "15m") || !strings.Contains(err.Error(), "nothing was deleted") {
		t.Fatalf("the lockout says how long and that nothing was deleted: %v", err)
	}
	if _, _, err := run(t, kitKey+"wxyz\n1\nabcdefghijk\nother words!\n5\n"); err != nil {
		t.Fatalf("two different passwords are refused, then Done: %v", err)
	}
}

func TestConsoleNeedsTheKeyFile(t *testing.T) {
	c := &Console{Gateway: "http://127.0.0.1:1", KeyFile: filepath.Join(t.TempDir(), "none"), In: strings.NewReader(""), Out: &strings.Builder{}}
	if err := c.Run(context.Background()); err == nil || !strings.Contains(err.Error(), "only on the box") {
		t.Fatalf("%v", err)
	}
}
