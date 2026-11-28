// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func accountTestSession(access, refresh string) map[string]any {
	return map[string]any{"access_token": access, "refresh_token": refresh, "expires_at": time.Now().Add(time.Minute),
		"principal": map[string]string{"id": "usr_Owner"}}
}

func TestAccountSetupRequiresSavingAndConfirmingKit(t *testing.T) {
	dir := isolate(t)
	var kits, finishes atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		switch r.Method + " " + r.URL.Path {
		case "POST /v1/auth/setup/options":
			jsonOut(w, 200, map[string]string{"challenge_id": "challenge"})
		case "POST /v1/auth/setup":
			if body["box_code"] != "123456" || body["challenge_id"] != "challenge" ||
				body["password"] != " twelve or more " || body["username"] != "homeowner" || body["client"] != "cli" {
				t.Errorf("setup arguments: %+v", body)
			}
			jsonOut(w, 201, accountTestSession("setup-session", "setup-refresh"))
		case "POST /v1/auth/setup/kit":
			kits.Add(1)
			if r.Header.Get("Authorization") != "Bearer setup-session" {
				t.Error("kit request omitted the setup session")
			}
			jsonOut(w, 200, map[string]string{"recovery_code": "kit-code", "disk_recovery_key": "disk-key"})
		case "POST /v1/auth/setup/finish":
			attempt := finishes.Add(1)
			if r.Header.Get("Authorization") != "Bearer setup-session" || body["saved"] != true ||
				body["method"] != "download" || body["recovery_code"] != "kit-code" {
				t.Errorf("finish arguments: %+v", body)
			}
			if raw, err := os.ReadFile(filepath.Join(dir, "unconfirmed.json")); err != nil || !strings.Contains(string(raw), "disk-key") {
				t.Errorf("finish ran before kit was saved: %s %v", raw, err)
			}
			if attempt == 1 {
				if body["disk_recovery_key"] != nil {
					t.Error("sent disk recovery key before it was needed")
				}
				jsonOut(w, 503, map[string]string{"error": "unavailable", "reason": "disk_recovery_key_missing",
					"message": "The encrypted disk handoff was lost after reboot."})
				return
			}
			if body["disk_recovery_key"] != "disk-key" {
				t.Error("did not confirm using the saved disk key")
			}
			w.WriteHeader(204)
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	t.Cleanup(srv.Close)
	r := run(t, "123456\n twelve or more \n", false, "--hub", srv.URL, "account", "setup", "homeowner", "--name", "home", "--secrets-stdin")
	if r.code != 0 || !strings.Contains(r.out, "setup-finish") || strings.Contains(r.out+r.errOut, "setup-session") {
		t.Fatalf("setup %+v", r)
	}
	path := filepath.Join(dir, "unconfirmed.json")
	r = run(t, "", false, "account", "setup-finish", "--kit", path)
	if r.code != ExitUsage || finishes.Load() != 0 || kits.Load() != 1 || !strings.Contains(r.errOut, "safe") {
		t.Fatalf("unconfirmed setup %+v, finishes %d", r, finishes.Load())
	}
	existing := filepath.Join(dir, "unrelated.json")
	if err := os.WriteFile(existing, []byte("another file"), 0o600); err != nil {
		t.Fatal(err)
	}
	r = run(t, "", false, "account", "setup-finish", "--kit", existing, "--yes")
	if r.code == 0 || finishes.Load() != 0 || kits.Load() != 1 {
		t.Fatalf("must not overwrite kit %+v", r)
	}
	r = run(t, "", false, "account", "setup-finish", "--kit", path, "--yes", "--json")
	if r.code != 0 || finishes.Load() != 2 || kits.Load() != 1 || !strings.Contains(r.out, "setup_finished") ||
		strings.Contains(r.out+r.errOut, "kit-code") || strings.Contains(r.out+r.errOut, "disk-key") {
		t.Fatalf("confirm setup %+v", r)
	}
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("kit should be private: %v %v", info, err)
	}
}

func TestAccountLoginPromptsForTOTPAndRenewsTheSavedSessionOnce(t *testing.T) {
	dir := isolate(t)
	var logins, refreshes atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		switch r.Method + " " + r.URL.Path {
		case "POST /v1/auth/login":
			logins.Add(1)
			if body["username"] != "person" || body["password"] != " private phrase " || body["client"] != "cli" {
				t.Errorf("login %v", body)
			}
			if body["totp"] != "654321" {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "totp_required"})
				return
			}
			jsonOut(w, 200, accountTestSession("first-access", "first-refresh"))
		case "POST /v1/auth/refresh":
			refreshes.Add(1)
			if body["refresh_token"] != "first-refresh" || r.Header.Get("Authorization") != "" {
				t.Errorf("refresh %v", body)
			}
			jsonOut(w, 200, accountTestSession("next-access", "next-refresh"))
		case "GET /v1/nodes":
			if r.Header.Get("Authorization") != "Bearer next-access" {
				t.Errorf("missing renewed session: %s", r.Header.Get("Authorization"))
			}
			jsonOut(w, 200, []any{})
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	t.Cleanup(srv.Close)
	r := run(t, " private phrase \n654321\n", false, "login", "--username", "person", "--name", "home", "--hub", srv.URL, "--secrets-stdin", "--json")
	if r.code != 0 || logins.Load() != 2 || !strings.Contains(r.out, "home") ||
		strings.Contains(r.out+r.errOut, "first-access") || strings.Contains(r.out+r.errOut, "first-refresh") {
		t.Fatalf("login %+v", r)
	}
	cfg, err := loadConfig(filepath.Join(dir, "onemind", "config.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	credentials, err := cfg.loadCreds()
	if err != nil {
		t.Fatal(err)
	}
	session := credentials.Sessions["home"]
	session.Expires = time.Now().Add(-time.Minute)
	credentials.Sessions["home"] = session
	if err := cfg.saveCreds(credentials); err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	for range 2 {
		wg.Go(func() {
			if r := run(t, "", false, "nodes", "--json"); r.code != 0 || r.out != "[]\n" {
				t.Errorf("renewed CLI session %+v", r)
			}
		})
	}
	wg.Wait()
	if refreshes.Load() != 1 {
		t.Fatalf("expected one renewal, got %d", refreshes.Load())
	}
}

func TestFamilyInvitationUsesTheSignedInSessionAndBoundStepUp(t *testing.T) {
	isolate(t)
	var invites, options, verification, replacements atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if r.Method+" "+r.URL.Path == "POST /v1/auth/login" {
			jsonOut(w, 200, accountTestSession("owner-access", "owner-refresh"))
			return
		}
		if r.Header.Get("Authorization") != "Bearer owner-access" {
			t.Error("a family invitation must use the signed-in owner's session")
		}
		switch r.Method + " " + r.URL.Path {
		case "POST /v1/users":
			if len(body) != 3 || body["role"] != "child" || body["display_name"] != "Sam" || body["username"] != "sam" {
				t.Errorf("incorrect invite request: %+v", body)
			}
			if invites.Add(1) > 3 {
				jsonOut(w, 503, map[string]string{"error": "unavailable", "message": "gateway unavailable"})
				return
			}
			if r.Header.Get("OneMind-Step-Up") == "" {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "step_up_required"})
				return
			}
			if r.Header.Get("OneMind-Step-Up") != "invitation-proof" || verification.Load() != 1 {
				t.Error("invitation did not carry the verified single-use grant")
			}
			jsonOut(w, 201, map[string]any{"id": "usr_sam", "display_name": "Sam", "role": "child", "one_time": map[string]string{"enrolment_url": "https://box.example/signin#enrol=CODE"}})
		case "POST /v1/auth/step-up/options":
			options.Add(1)
			bound := obj(body["body"])
			if body["op"] != "users.create" || body["method"] != "password+totp" || body["at_box"] != true ||
				len(bound) != 3 || bound["role"] != "child" || bound["display_name"] != "Sam" || bound["username"] != "sam" {
				t.Errorf("step-up options did not bind the invitation: %+v", body)
			}
			jsonOut(w, 200, map[string]any{"challenge": "invite-challenge", "box_code_required": true})
		case "POST /v1/auth/step-up":
			verification.Add(1)
			proof := obj(body["password_totp"])
			if proof["challenge"] != "invite-challenge" || proof["password"] != "test passphrase" ||
				proof["totp"] != "112233" || body["box_code"] != "445566" {
				t.Error("step-up did not use the challenge and the operator's verification")
			}
			jsonOut(w, 200, map[string]string{"step_up": "invitation-proof"})
		case "POST /v1/users/usr_sam/invite":
			replacements.Add(1)
			if body != nil || r.Header.Get("OneMind-Step-Up") != "" {
				t.Error("replacement must name its target in the URL and wait for an approval")
			}
			jsonOut(w, 202, map[string]any{"id": "act_replace", "type": "users.reinvite", "state": "awaiting_approval",
				"params": map[string]string{"user_id": "usr_sam"}})
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	t.Cleanup(srv.Close)
	r := run(t, "test passphrase\n", false, "login", "--username", "owner", "--hub", srv.URL, "--secrets-stdin")
	if r.code != 0 {
		t.Fatalf("owner CLI sign-in %+v", r)
	}
	invite := []string{"users", "invite", "Sam", "--role", "child", "--username", "sam"}
	r = run(t, "", false, invite...)
	if r.code != ExitUnauthenticated || invites.Load() != 1 || options.Load() != 0 || verification.Load() != 0 {
		t.Fatalf("unattended invite attempted verification: %+v", r)
	}
	r = run(t, "test passphrase\n112233\n445566\n", false, append(invite, "--secrets-stdin")...)
	if r.code != 0 || invites.Load() != 3 || options.Load() != 1 || verification.Load() != 1 ||
		!strings.Contains(r.out, "Invited Sam") || !strings.Contains(r.out, "#enrol=CODE") ||
		strings.Contains(r.out+r.errOut, "112233") || strings.Contains(r.out+r.errOut, "445566") ||
		strings.Contains(r.out+r.errOut, "test passphrase") {
		t.Fatalf("verified direct invite %+v", r)
	}
	r = run(t, "", true, invite...)
	if r.code == 0 || invites.Load() != 4 {
		t.Fatalf("failed invite request was retried or reported success: %+v (%d POSTs)", r, invites.Load())
	}
	if r := run(t, "", false, "users", "reinvite", "usr_sam"); r.code != ExitUsage || replacements.Load() != 0 ||
		!strings.Contains(r.errOut, "clears this person's sign-in credentials and sessions") {
		t.Fatalf("replacement without confirmation %+v", r)
	}
	r = run(t, "", false, "users", "reinvite", "usr_sam", "--yes", "--json")
	if r.code != 0 || replacements.Load() != 1 {
		t.Fatalf("queued replacement %+v", r)
	}
	action := obj(mustJSON2(t, r.out))
	if action["id"] != "act_replace" || action["state"] != "awaiting_approval" || action["type"] != "users.reinvite" ||
		obj(action["params"])["user_id"] != "usr_sam" || action["one_time"] != nil {
		t.Fatalf("unexpected replacement action: %+v", action)
	}
}

func TestCLIApprovalLeavesInvitationWaitingForDashboard(t *testing.T) {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	var decisions atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			decisions.Add(1)
			w.WriteHeader(404)
			return
		}
		typ := strings.TrimPrefix(r.URL.Path, "/v1/actions/")
		jsonOut(w, 200, map[string]string{"id": typ, "type": typ, "state": "awaiting_approval"})
	}))
	t.Cleanup(srv.Close)
	for _, typ := range []string{"users.invite", "users.reinvite"} {
		r := run(t, "", true, "--hub", srv.URL, "actions", "approve", typ, "--yes", "--json")
		if r.code != ExitPending || decisions.Load() != 0 || !strings.Contains(r.errOut, "Approvals in the dashboard") {
			t.Errorf("%s approval must stay in the queue for dashboard delivery: %+v", typ, r)
		}
	}
}

func TestAccountRemoteRecoveryNeverPrintsTheKitCode(t *testing.T) {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/auth/recovery/remote" {
			t.Errorf("unexpected route %s", r.URL.Path)
		}
		if r.Method == http.MethodPost {
			var body map[string]string
			_ = json.NewDecoder(r.Body).Decode(&body)
			if body["recovery_code"] != "saved-kit-code" {
				t.Errorf("missing recovery proof: %+v", body)
			}
		}
		if r.Method == http.MethodDelete {
			w.WriteHeader(204)
			return
		}
		jsonOut(w, 200, map[string]string{"state": "waiting", "available_at": "2026-11-30T00:00:00Z", "expires_at": "2026-12-01T00:00:00Z"})
	}))
	t.Cleanup(srv.Close)
	base := []string{"--hub", srv.URL, "account", "remote-recovery"}
	r := run(t, "saved-kit-code\n", false, append(base, "start", "--secrets-stdin")...)
	if r.code != 0 || strings.Contains(r.out+r.errOut, "saved-kit-code") {
		t.Fatalf("remote recovery start %+v", r)
	}
	if r := run(t, "", false, append(base, "status", "--json")...); r.code != 0 || !strings.Contains(r.out, "waiting") {
		t.Fatalf("remote recovery status %+v", r)
	}
	if r := run(t, "", false, append(base, "cancel")...); r.code != 0 {
		t.Fatalf("remote recovery cancel %+v", r)
	}
}

func TestAccountRecoveryUsesBothCodesAndWritesReplacement(t *testing.T) {
	dir := isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		switch r.Method + " " + r.URL.Path {
		case "POST /v1/auth/recovery/options":
			if body["username"] != "homeowner" {
				t.Errorf("options %+v", body)
			}
			jsonOut(w, 200, map[string]string{"challenge_id": "reset-challenge"})
		case "POST /v1/auth/recovery/reset":
			if body["box_code"] != "112233" || body["recovery_code"] != "saved-kit" ||
				body["challenge_id"] != "reset-challenge" || body["new_password"] != "new password with spaces" {
				t.Errorf("reset %+v", body)
			}
			jsonOut(w, 200, map[string]string{"recovery_code": "next-kit"})
		default:
			t.Errorf("unexpected request %s", r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	t.Cleanup(srv.Close)
	path := filepath.Join(dir, "replacement.json")
	r := run(t, "112233\nsaved-kit\nnew password with spaces\n", false,
		"--hub", srv.URL, "account", "recover", "homeowner", "--kit", path, "--secrets-stdin", "--json")
	raw, err := os.ReadFile(path)
	if r.code != 0 || err != nil || !strings.Contains(string(raw), "next-kit") || strings.Contains(r.out+r.errOut, "next-kit") {
		t.Fatalf("recover %+v, kit %s %v", r, raw, err)
	}
}

func TestAccountEnrolSendsOwnPasswordToTheSelectedBox(t *testing.T) {
	isolate(t)
	var requests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if r.Method != http.MethodPost || r.URL.Path != "/v1/auth/enrol" || r.Header.Get("Authorization") != "" ||
			body["code"] != "my-invite" || body["client"] != "cli" ||
			body["username"] != "family" || body["password"] != "my own new password" {
			t.Errorf("enrol request %s %s %+v", r.Method, r.URL.Path, body)
		}
		jsonOut(w, 201, accountTestSession("family-access", "family-refresh"))
	}))
	t.Cleanup(srv.Close)
	args := []string{"--hub", srv.URL, "account", "enrol", "family", "--secrets-stdin"}
	r := run(t, "https://other.example/signin#enrol=my-invite\nmy own new password\n", false, args...)
	if r.code != ExitUsage || requests.Load() != 0 {
		t.Fatalf("wrong box %+v", r)
	}
	r = run(t, srv.URL+"/signin#enrol=my-invite\nmy own new password\n", false, args...)
	if r.code != 0 || requests.Load() != 1 || strings.Contains(r.out+r.errOut, "family-access") {
		t.Fatalf("enrol %+v", r)
	}
}

func TestAccountLoginDoesNotForwardACredentialRedirect(t *testing.T) {
	isolate(t)
	var redirected atomic.Bool
	other := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		redirected.Store(true)
		w.WriteHeader(401)
	}))
	t.Cleanup(other.Close)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, other.URL, http.StatusTemporaryRedirect)
	}))
	t.Cleanup(srv.Close)
	r := run(t, "test passphrase\n", false, "--hub", srv.URL, "login", "--username", "owner", "--secrets-stdin")
	if r.code == 0 || redirected.Load() {
		t.Fatalf("redirected credential request %+v", r)
	}
}

func TestActionApprovalRequiresAnOperatorForStepUpAndChecksThePlan(t *testing.T) {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	var options, approvals atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/actions/act_pending":
			jsonOut(w, 200, map[string]any{"id": "act_pending", "type": "app.remove", "state": "awaiting_approval",
				"params": map[string]string{"app_id": "photos"}, "plan_sha256": "plan-reviewed"})
		case "POST /v1/actions/act_pending/approve":
			approvals.Add(1)
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "step_up_required"})
		case "POST /v1/actions/act_pending/approve-options":
			options.Add(1)
			var body map[string]any
			_ = json.NewDecoder(r.Body).Decode(&body)
			if body["method"] != "password+totp" || body["at_box"] != true {
				t.Errorf("approval options %+v", body)
			}
			jsonOut(w, 200, map[string]any{"challenge": "reviewed-proof", "plan_sha256": "changed-plan", "box_code_required": true})
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	t.Cleanup(srv.Close)
	args := []string{"--hub", srv.URL, "actions", "approve", "act_pending", "--yes", "--json"}
	r := run(t, "", false, args...)
	if r.code != ExitUnauthenticated || options.Load() != 0 || approvals.Load() != 1 {
		t.Fatalf("unattended approval %+v", r)
	}
	r = run(t, "", true, args...)
	if r.code != ExitConflict || options.Load() != 1 || approvals.Load() != 2 || !strings.Contains(r.errOut, "plan changed") {
		t.Fatalf("stale plan approval %+v", r)
	}
}

func TestAccountCredentialsRejectInsecureRemoteHTTP(t *testing.T) {
	isolate(t)
	r := run(t, "test passphrase\n", false, "--hub", "http://one.example", "login", "--username", "owner", "--secrets-stdin")
	if r.code != ExitUsage || !strings.Contains(r.errOut, "HTTPS") {
		t.Fatalf("insecure account login %+v", r)
	}
}

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
			// The real body (IdentityService._account -> deny(..., tell=True)), checked by core test_identity.
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "not allowed to change the password", "reason": "session_required"})
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

// A gateway from before reason=session_required was sent answers a bare 403; the CLI still says what to do.
func TestAccountExplainsABare403FromAnOlderGateway(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "not allowed to set up an authenticator"})
	}))
	t.Cleanup(srv.Close)
	isolate(t)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", "pat-token")
	r := run(t, "", false, "account", "totp", "setup")
	if r.code != ExitPermissionDenied || !strings.Contains(r.errOut, "not an API token") {
		t.Fatalf("%+v", r)
	}
}

func TestAccountTotpSetupConfirmDisable(t *testing.T) {
	var got []string
	accountHub(t, &got)
	r := run(t, "", false, "account", "totp", "setup")
	if r.code != 0 || !strings.Contains(r.out, "JBSWY3DPEHPK3PXP") || !strings.Contains(r.errOut, "Passkeys are recommended") {
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
