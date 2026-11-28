// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

const recID = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"

// A stand-in for the 25e routes: start (no token), the starter's routes (omr_ token only), the owner's list.
func recoveryFlowGW(t *testing.T) (*httptest.Server, *[]string) {
	var mu sync.Mutex
	seen := []string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		auth := r.Header.Get("Authorization")
		var b map[string]any
		_ = json.NewDecoder(r.Body).Decode(&b)
		seen = append(seen, r.Method+" "+r.URL.Path+" "+auth)
		view := map[string]any{"id": recID, "path": "contact", "state": "awaiting_contact", "matching_number": "42",
			"request_code": "amber-river-1234"}
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/auth/recovery":
			if auth != "" {
				jsonOut(w, 400, map[string]string{"error": "conflict", "message": "a saved token was sent"})
				return
			}
			if b["path"] == "remote" && (b["password"] != "pw-from-stdin" || b["totp"] != "123456") {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "x", "reason": "second_factor_required"})
				return
			}
			jsonOut(w, 201, map[string]any{"id": recID, "path": b["path"], "state": "awaiting_contact", "matching_number": "42",
				"request_code": "amber-river-1234", "one_time": map[string]any{"request_token": "omr_secret"}})
		case strings.HasPrefix(r.URL.Path, "/v1/auth/recovery/requests/"+recID):
			if auth != "Bearer omr_secret" {
				if strings.HasSuffix(r.URL.Path, "/cancel") && auth == "Bearer "+ownerTok {
					jsonOut(w, 200, map[string]any{"id": recID, "state": "cancelled"})
					return
				}
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "request token"})
				return
			}
			switch {
			case strings.HasSuffix(r.URL.Path, "/code"):
				view["state"], view["vouch_method"] = "waiting", "code"
			case strings.HasSuffix(r.URL.Path, "/complete"):
				if b["current_password"] != "current passphrase" || b["new_password"] != "a new passphrase" {
					jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "owner_proof_required"})
					return
				}
				jsonOut(w, 200, map[string]any{"session": map[string]any{"id": "ses_1"}})
				return
			}
			jsonOut(w, 200, view)
		case r.URL.Path == "/v1/auth/recovery":
			jsonOut(w, 200, []any{map[string]any{"id": recID, "path": "contact", "state": "waiting", "source": "203.0.113.9"}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	return srv, &seen
}

func TestRecoveryStartCodeStatusCompleteKeepsTheRequestTokenToItself(t *testing.T) {
	isolate(t)
	srv, seen := recoveryFlowGW(t)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok) // a saved credential must not ride along on a locked-out start
	r := run(t, "", false, "recovery", "start", "--user", "zeus")
	if r.code != 0 || !strings.Contains(r.out, "42") || !strings.Contains(r.out, "amber-river-1234") || strings.Contains(r.out, "omr_secret") {
		t.Fatalf("start %+v", r)
	}
	if r := run(t, "", false, "recovery", "code", recID, "1234 5678"); r.code != 0 || !strings.Contains(r.out, "waiting") {
		t.Fatalf("code %+v", r)
	}
	if r := run(t, "", false, "recovery", "status", recID); r.code != 0 || !strings.Contains(r.out, "awaiting_contact") {
		t.Fatalf("status %+v", r)
	}
	if r := run(t, "current passphrase\na new passphrase\n", false,
		"recovery", "complete", recID, "--current-password-stdin", "--new-password-stdin"); r.code != 0 || !strings.Contains(r.out, "Recovered") {
		t.Fatalf("complete %+v", r)
	}
	// The saved token is gone after completing; the owner's list uses the owner's own credential.
	if r := run(t, "", false, "recovery", "status", recID); r.code != ExitNotFound {
		t.Fatalf("status after complete %+v", r)
	}
	if r := run(t, "", false, "recovery", "status"); r.code != 0 || !strings.Contains(r.out, "203.0.113.9") {
		t.Fatalf("owner list %+v", r)
	}
	for _, s := range *seen {
		if strings.HasPrefix(s, "POST /v1/auth/recovery ") && strings.Contains(s, "Bearer") {
			t.Fatalf("start sent a credential: %s", s)
		}
	}
}

func TestRecoveryRemoteNeedsPasswordAndCodeAndCancelFallsBackToTheOwner(t *testing.T) {
	isolate(t)
	srv, _ := recoveryFlowGW(t)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "recovery", "start", "--path", "remote", "--user", "zeus"); r.code != ExitUsage {
		t.Fatalf("remote without factors %+v", r)
	}
	if r := run(t, "pw-from-stdin\n", false, "recovery", "start", "--path", "remote", "--user", "zeus", "--password-stdin", "--totp", "123456"); r.code != 0 {
		t.Fatalf("remote %+v", r)
	}
	if r := run(t, "", false, "recovery", "complete", recID); r.code != ExitUsage ||
		!strings.Contains(r.errOut, "WebAuthn client using the gateway API") {
		t.Fatalf("remote completion guidance %+v", r)
	}
	if r := run(t, "", false, "recovery", "cancel", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"); r.code == 0 {
		t.Fatalf("cancel of a request that is not ours and not found %+v", r)
	}
	if r := run(t, "", false, "recovery", "status", "not-an-id"); r.code != ExitUsage {
		t.Fatalf("bad id %+v", r)
	}
}

func TestRecoveryBearerStaysWithItsGatewayAcrossContextSwitch(t *testing.T) {
	isolate(t)
	home, _ := recoveryFlowGW(t)
	away, seen := recoveryFlowGW(t)
	cfg, err := loadConfig("")
	if err != nil {
		t.Fatal(err)
	}
	cfg.Contexts["home"] = &Context{Hub: home.URL}
	cfg.Contexts["away"] = &Context{Hub: away.URL}
	cfg.CurrentContext = "home"
	if err := cfg.save(); err != nil {
		t.Fatal(err)
	}
	if r := run(t, "", false, "recovery", "start", "--user", "zeus"); r.code != 0 {
		t.Fatalf("start %+v", r)
	}
	if r := run(t, "", false, "context", "use", "away"); r.code != 0 {
		t.Fatalf("switch context %+v", r)
	}
	for _, args := range [][]string{
		{"status", recID}, {"code", recID, "12345678"}, {"cancel", recID}, {"complete", recID, "--new-password-stdin"},
	} {
		r := run(t, "a new passphrase\n", false, append([]string{"recovery"}, args...)...)
		if r.code != ExitUsage || !strings.Contains(r.errOut, "different gateway") {
			t.Errorf("wrong gateway for %s: %+v", args[0], r)
		}
	}
	if len(*seen) != 0 {
		t.Fatal("commands contacted a different gateway")
	}
	if r := run(t, "", false, "--hub", home.URL+"/", "recovery", "status", recID); r.code != 0 {
		t.Fatalf("status on originating gateway %+v", r)
	}
}
