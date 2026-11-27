// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
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
			finishes.Add(1)
			if r.Header.Get("Authorization") != "Bearer setup-session" || body["saved"] != true ||
				body["method"] != "download" || body["recovery_code"] != "kit-code" {
				t.Errorf("finish arguments: %+v", body)
			}
			if raw, err := os.ReadFile(filepath.Join(dir, "unconfirmed.json")); err != nil || !strings.Contains(string(raw), "disk-key") {
				t.Errorf("finish ran before kit was saved: %s %v", raw, err)
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
	if r.code != 0 || finishes.Load() != 1 || kits.Load() != 1 || !strings.Contains(r.out, "setup_finished") ||
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

func TestFamilyInviteUsesOperationBoundAuthenticatorProof(t *testing.T) {
	isolate(t)
	stage := atomic.Int32{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if r.URL.Path == "/v1/auth/login" {
			jsonOut(w, 200, accountTestSession("owner-access", "owner-refresh"))
			return
		}
		if r.Header.Get("Authorization") != "Bearer owner-access" {
			t.Error("family invitation must use the owner's session")
		}
		n := stage.Add(1)
		switch r.URL.Path {
		case "/v1/users/invites":
			if body["role"] != "child" || body["display_name"] != "Sam" {
				t.Errorf("invite request %+v", body)
			}
			if n == 1 {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "step_up_required"})
				return
			}
			if n != 4 || r.Header.Get("OneMind-Step-Up") != "confirmed-proof" {
				t.Error("invite sent without exact-change proof")
			}
			jsonOut(w, 201, map[string]any{"one_time": map[string]string{"enrolment_url": "https://box.example/signin#enrol=family"}})
		case "/v1/auth/step-up/options":
			if n != 2 || body["op"] != "users.invite" || body["method"] != "password+totp" || obj(body["body"])["display_name"] != "Sam" {
				t.Errorf("step-up options %+v", body)
			}
			jsonOut(w, 200, map[string]string{"challenge": "step-challenge"})
		case "/v1/auth/step-up":
			proof := obj(body["password_totp"])
			if n != 3 || proof["challenge"] != "step-challenge" || proof["totp"] != "112233" || proof["password"] != "test passphrase" {
				t.Errorf("step-up proof %+v", body)
			}
			jsonOut(w, 200, map[string]string{"step_up": "confirmed-proof"})
		default:
			t.Errorf("unexpected request %s", r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	t.Cleanup(srv.Close)
	r := run(t, "test passphrase\n", false, "login", "--username", "owner", "--hub", srv.URL, "--secrets-stdin")
	if r.code != 0 {
		t.Fatalf("owner CLI sign-in %+v", r)
	}
	r = run(t, "test passphrase\n112233\n", false, "users", "invite", "Sam", "--role", "child", "--secrets-stdin")
	if r.code != 0 || stage.Load() != 4 || !strings.Contains(r.out, "#enrol=family") {
		t.Fatalf("invite %+v", r)
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
