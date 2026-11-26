// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTokensListCreateRotateRevoke(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/tokens": ok([]any{map[string]any{"id": "tok_1", "name": "laptop", "kind": "person", "principal_id": "usr_1",
			"scopes": []any{"apps:read", "files:read"}, "expires_at": "2027-01-01T00:00:00Z", "last_used_at": nil}}),
		"POST /v1/tokens": func(b map[string]any) (int, any) {
			return 201, map[string]any{"id": "tok_2", "name": b["name"], "expires_at": "2027-02-01T00:00:00Z", "one_time": map[string]any{"token": "omt_SECRET"}}
		},
		"POST /v1/tokens/tok_1/rotate": func(b map[string]any) (int, any) {
			return 201, map[string]any{"id": "tok_1", "name": "laptop", "one_time": map[string]any{"token": "omt_NEW"}}
		},
		"DELETE /v1/tokens/tok_1": func(map[string]any) (int, any) { return 204, nil },
	})
	r := run(t, "", false, "tokens", "list")
	outHas(t, r.out, "tok_1", "laptop", "apps:read, files:read", "-")
	if r := run(t, "", false, "tokens", "list", "--json"); len(jsonOf(t, r.out).([]any)) != 1 {
		t.Fatalf("json %+v", r)
	}

	r = run(t, "", false, "tokens", "create", "ci", "--agent", "builder", "--scopes", "apps:read,files:read", "--days", "30")
	outHas(t, r.out, "omt_SECRET", "shown once")
	b := g.sent("POST", "/v1/tokens")[0].body
	p := obj(b["principal"])
	if p["kind"] != "agent" || p["id"] != "agent:builder" || b["expires_in_days"] != float64(30) || len(list(b["scopes"])) != 2 {
		t.Fatalf("body %+v", b)
	}
	// Without flags the token is the person's own and no scope or lifetime is invented.
	run(t, "", false, "tokens", "create", "mine")
	b = g.sent("POST", "/v1/tokens")[1].body
	if b["principal"] != "self" || b["scopes"] != nil || b["expires_in_days"] != nil {
		t.Fatalf("defaults %+v", b)
	}
	if r := run(t, "", false, "tokens", "create", "q", "-q"); strings.TrimSpace(r.out) != "omt_SECRET" {
		t.Fatalf("quiet %q", r.out)
	}
	if r := run(t, "", false, "tokens", "rotate", "tok_1", "--grace", "60"); r.code != 0 || !strings.Contains(r.out, "omt_NEW") {
		t.Fatalf("rotate %+v", r)
	}
	if g.sent("POST", "/v1/tokens/tok_1/rotate")[0].body["grace_s"] != float64(60) {
		t.Fatal("grace not sent")
	}
	// Revoking needs --yes, then is a plain delete.
	if r := run(t, "", false, "tokens", "revoke", "tok_1"); r.code != ExitUsage || len(g.sent("DELETE", "/v1/tokens/tok_1")) != 0 {
		t.Fatalf("no --yes %+v", r)
	}
	if r := run(t, "", false, "tokens", "revoke", "tok_1", "--yes", "--json"); r.code != 0 || obj(jsonOf(t, r.out))["revoked"] != true {
		t.Fatalf("revoke %+v", r)
	}
	g.neverApproved(t)
}

func TestSecretsShowAndRequests(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/apps/nextcloud/secrets": ok(map[string]any{"app_id": "nextcloud", "missing_required": []any{"admin/password"}, "secrets": []any{
			map[string]any{"name": "admin", "keys": []any{
				map[string]any{"key": "password", "kind": "password", "required": true, "set": false},
				map[string]any{"key": "token", "kind": "token", "required": false, "set": true, "version": 3.0, "updated_at": "2026-11-20T00:00:00Z"}}}}}),
		"GET /v1/secrets/public-key":      ok(map[string]any{"alg": "X25519", "key": "abc", "key_id": "k1", "sealed_alg": "x"}),
		"POST /v1/apps/nextcloud/secrets": waitingAction,
	})
	r := run(t, "", false, "secrets", "show", "nextcloud")
	outHas(t, r.out, "admin/password", "required", "not set", "set (v3)", "Still missing: admin/password")
	if strings.Contains(r.out, "value") {
		t.Fatalf("a value column: %s", r.out)
	}
	outHas(t, run(t, "", false, "secrets", "public-key").out, "k1", "X25519")

	r = run(t, "", false, "secrets", "generate", "nextcloud", "admin/token", "--reason", "rotate")
	outHas(t, r.out, "Requested", "act_7", "onemind actions approve act_7")
	b := g.sent("POST", "/v1/apps/nextcloud/secrets")[0].body
	if len(list(b["generate"])) != 1 || b["reason"] != "rotate" || b["sealed"] != nil {
		t.Fatalf("body %+v", b)
	}
	run(t, "", false, "secrets", "clear", "nextcloud", "admin/token")
	if len(list(g.sent("POST", "/v1/apps/nextcloud/secrets")[1].body["clear"])) != 1 {
		t.Fatal("clear not sent")
	}
	if r := run(t, "", false, "secrets", "generate", "nextcloud", "--json"); r.code == 0 {
		t.Fatalf("needs a key %+v", r)
	}
	g.neverApproved(t)
}

func TestFamilyShowSetAndStepUp(t *testing.T) {
	stepUp := false
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/family/profiles/usr_2": ok(map[string]any{"max_age_rating": 12.0, "blocked_tags": []any{"social"}, "allowed_apps": nil,
			"timezone": "America/New_York", "windows": []any{map[string]any{"days": []any{"mon", "tue"}, "start_minute": 420.0, "end_minute": 1230.0}}}),
		"PUT /v1/family/profiles/usr_2": func(b map[string]any) (int, any) {
			if stepUp {
				return 401, map[string]any{"error": "unauthenticated", "reason": "step_up_required", "message": "sign in again"}
			}
			return 200, b
		},
		"GET /v1/family/apps/chess": ok(map[string]any{"min_age": 6.0, "tags": []any{"games"}}),
		"PUT /v1/family/apps/chess": func(b map[string]any) (int, any) { return 200, b },
	})
	outHas(t, run(t, "", false, "family", "profile", "show", "usr_2").out, "12", "social", "mon, tue 07:00-20:30", "every app that passes")
	outHas(t, run(t, "", false, "family", "app", "show", "chess").out, "6", "games")

	f := filepath.Join(t.TempDir(), "p.json")
	_ = os.WriteFile(f, []byte(`{"max_age_rating": 10, "blocked_tags": [], "timezone": "UTC"}`), 0o600)
	if r := run(t, "", false, "family", "profile", "set", "usr_2", "--file", f); r.code != 0 || !strings.Contains(r.out, "Saved") {
		t.Fatalf("set %+v", r)
	}
	if g.sent("PUT", "/v1/family/profiles/usr_2")[0].body["max_age_rating"] != float64(10) {
		t.Fatal("body")
	}
	if r := run(t, `{"min_age": 8, "tags": []}`, false, "family", "app", "set", "chess", "--file", "-"); r.code != 0 {
		t.Fatalf("stdin %+v", r)
	}
	if r := run(t, "", false, "family", "profile", "set", "usr_2"); r.code != ExitUsage {
		t.Fatalf("no file %+v", r)
	}
	if r := run(t, "not json", false, "family", "profile", "set", "usr_2", "--file", "-"); r.code != ExitUsage {
		t.Fatalf("bad json %+v", r)
	}
	stepUp = true
	r := run(t, "", false, "family", "profile", "set", "usr_2", "--file", f)
	if r.code == 0 || !strings.Contains(r.errOut, "passkey") {
		t.Fatalf("step-up must be explained: %+v", r)
	}
}

func TestBrowsersOpenCloseReset(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"POST /v1/browsers/firefox/session":       ok(map[string]any{"app_id": "firefox", "url": "https://b1.box.example/", "state": "starting", "password": "pw-1"}),
		"POST /v1/browsers/firefox/session/close": ok(map[string]any{"app_id": "firefox", "state": "stopped"}),
		"POST /v1/browsers/firefox/profile/reset": waitingAction,
	})
	outHas(t, run(t, "", false, "browsers", "open", "firefox").out, "https://b1.box.example/", "pw-1")
	if r := run(t, "", false, "browsers", "open", "firefox", "-q"); strings.TrimSpace(r.out) != "https://b1.box.example/" {
		t.Fatalf("quiet %q", r.out)
	}
	outHas(t, run(t, "", false, "browsers", "close", "firefox").out, "profile is kept")
	outHas(t, run(t, "", false, "browsers", "reset-profile", "firefox").out, "Requested", "act_7")
	g.neverApproved(t)
	if len(g.sent("POST", "/v1/browsers/firefox/profile/reset")) != 1 {
		t.Fatal("reset not filed")
	}
}
