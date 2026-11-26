// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// accountHub answers like routers/identity.py: /v1/auth/methods, /v1/auth/password and /v1/auth/totp/*.
// A request from patTok is an API token, which the gateway refuses for credential changes (session_required).
func accountHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	totp := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.Path+" "+string(body))
		auth := r.Header.Get("Authorization")
		if auth != "Bearer "+ownerTok && auth != "Bearer pat-token" {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		if r.Method == http.MethodPost && auth == "Bearer pat-token" {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "change the password needs a session", "reason": "session_required"})
			return
		}
		var in map[string]string
		_ = json.Unmarshal(body, &in)
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/methods":
			jsonOut(w, 200, map[string]any{"password": true, "totp": totp, "passkeys": 0, "passkeys_active": false})
		case r.URL.Path == "/v1/auth/password":
			if in["current_password"] != "old password 1" {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "current password is wrong", "reason": "bad_credentials"})
				return
			}
			w.WriteHeader(204)
		case r.URL.Path == "/v1/auth/totp/setup":
			jsonOut(w, 200, map[string]any{"one_time": map[string]string{"secret": "JBSWY3DPEHPK3PXP", "otpauth_uri": "otpauth://totp/OneMind:zeus?secret=JBSWY3DPEHPK3PXP"}})
		case r.URL.Path == "/v1/auth/totp/confirm":
			totp = true
			w.WriteHeader(204)
		case r.URL.Path == "/v1/auth/totp/disable":
			totp = false
			w.WriteHeader(204)
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestAccountShow(t *testing.T) {
	var got []string
	accountHub(t, &got)
	r := run(t, "", false, "account", "show")
	if r.code != 0 || !strings.Contains(r.out, "Authenticator code: off (a fallback") || !strings.Contains(r.out, "Add a passkey") {
		t.Fatalf("%+v", r)
	}
	r = run(t, "", false, "--json", "account", "show")
	var m signInMethods
	if r.code != 0 || json.Unmarshal([]byte(r.out), &m) != nil || !m.Password || m.TOTP {
		t.Fatalf("%+v", r)
	}
}

func TestAccountPasswordReadsStdinNeverFlags(t *testing.T) {
	var got []string
	accountHub(t, &got)
	r := run(t, "old password 1\nnew password 22\n", false, "account", "password", "--password-stdin")
	if r.code != 0 || !strings.Contains(r.out, "other devices were signed out") {
		t.Fatalf("%+v", r)
	}
	if last := got[len(got)-1]; !strings.Contains(last, `"current_password":"old password 1"`) || !strings.Contains(last, `"new_password":"new password 22"`) {
		t.Fatalf("sent %q", last)
	}
	if r = run(t, "wrong\nnew password 22\n", false, "account", "password", "--password-stdin"); r.code != ExitUnauthenticated {
		t.Fatalf("a wrong current password must exit unauthenticated: %+v", r)
	}
	n := len(got)
	if r = run(t, "old password 1\n", false, "account", "password", "--password-stdin"); r.code != ExitUsage || len(got) != n {
		t.Fatalf("a missing new password is a usage error and sends nothing: %+v", r)
	}
	if r = run(t, "", false, "account", "password"); r.code != ExitUsage || !strings.Contains(r.errOut, "--password-stdin") {
		t.Fatalf("no terminal and no --password-stdin: %+v", r)
	}
}

func TestAccountRefusedForAnAPIToken(t *testing.T) {
	var got []string
	accountHub(t, &got)
	t.Setenv("ONEMIND_TOKEN", "pat-token")
	r := run(t, "old password 1\nnew password 22\n", false, "account", "password", "--password-stdin")
	if r.code != ExitPermissionDenied || !strings.Contains(r.errOut, "dashboard (Settings > Account and security)") {
		t.Fatalf("%+v", r)
	}
}

func TestAccountTotpSetupConfirmDisable(t *testing.T) {
	var got []string
	accountHub(t, &got)
	r := run(t, "", false, "account", "totp", "setup")
	if r.code != 0 || !strings.Contains(r.out, "JBSWY3DPEHPK3PXP") || !strings.Contains(r.errOut, "new people should use a passkey only") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "--json", "account", "totp", "setup"); r.code != 0 || !strings.Contains(r.out, `"otpauth_uri"`) || strings.Contains(r.errOut, "passkey") {
		t.Fatalf("--json prints the gateway object only: %+v", r)
	}
	n := len(got)
	if r = run(t, "", false, "account", "totp", "confirm", "12ab56"); r.code != ExitUsage || len(got) != n {
		t.Fatalf("a non-numeric code is refused before any call: %+v", r)
	}
	if r = run(t, "", false, "account", "totp", "confirm", "123456"); r.code != 0 || !strings.Contains(got[len(got)-1], `{"code":"123456"}`) {
		t.Fatalf("%+v %v", r, got)
	}
	if r = run(t, "", false, "account", "show"); !strings.Contains(r.out, "Authenticator code: on") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "my password 1\n", false, "--json", "account", "totp", "disable", "--password-stdin"); r.code != 0 || !strings.Contains(r.out, `"totp": false`) {
		t.Fatalf("%+v", r)
	}
	if !strings.Contains(got[len(got)-1], `{"password":"my password 1"}`) {
		t.Fatalf("sent %q", got[len(got)-1])
	}
}
