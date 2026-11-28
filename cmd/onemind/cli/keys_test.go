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
	"testing"
	"time"
)

// keysHub answers like the routes in routers/identity.py for keys, trusted models and the table.
func keysHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.RequestURI()+" "+string(body))
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.URL.Path == "/v1/instance":
			w.Header().Set("Date", time.Now().UTC().Format(http.TimeFormat))
			jsonOut(w, 200, map[string]any{"name": "box"})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/passkeys":
			jsonOut(w, 200, []map[string]any{
				{"credential_id": "c1", "label": "iPhone", "created_at": "2026-11-20T01:00:00Z", "last_used_at": nil,
					"level": "L1", "level_reason": "no_attestation", "explanation": "This passkey can't prove its make and model.",
					"model": nil, "aaguid": nil, "attestation": "none", "device_bound": false, "synced": true},
				{"credential_id": "c2", "label": "Bio key", "created_at": "2026-11-21T01:00:00Z", "last_used_at": "2026-11-24T01:00:00Z",
					"level": "L2", "level_reason": "proven", "explanation": "A proven key.", "model": "Test Bio Key",
					"aaguid": "a1b2", "attestation": "packed", "device_bound": true, "synced": false}})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/auth/passkeys/c1":
			w.WriteHeader(204)
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/authenticator-allowlist":
			jsonOut(w, 200, []map[string]any{{"aaguid": "a1b2", "name": "Test Bio Key", "user_verification": []string{"fingerprint_internal"},
				"biometric": true, "roots": 1, "source": "owner", "added_at": nil}})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/auth/authenticator-allowlist/a1b2":
			w.WriteHeader(204)
		case r.Method == http.MethodGet && r.URL.Path == "/v1/verification-requirements":
			jsonOut(w, 200, map[string]any{"rows": []map[string]any{
				{"key": "tier.T3", "label": "Approve a destructive action", "default": "L2", "current": "L2", "minimum": "L1", "maximum": "L3", "strict": false}},
				"types":           []map[string]any{{"key": "type:backup.restore", "current": "L3", "minimum": "L1", "maximum": "L3"}},
				"household_level": nil, "grace": true})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/actions":
			jsonOut(w, 201, map[string]any{"id": "act-7", "state": "awaiting_approval"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestKeysListShowsLevelsAndWhyAKeyIsL1(t *testing.T) {
	var got []string
	keysHub(t, &got)
	r := run(t, "", false, "keys", "list")
	if r.code != 0 || !strings.Contains(r.out, "L2 Proven key") || !strings.Contains(r.out, "L1 Device check") ||
		!strings.Contains(r.out, "synced") || !strings.Contains(r.out, "device-bound") ||
		!strings.Contains(r.out, "iPhone: This passkey can't prove") {
		t.Fatalf("%+v", r)
	}
	r = run(t, "", false, "--json", "keys", "list")
	var list []map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &list) != nil || len(list) != 2 {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "keys", "remove", "c1"); r.code != 0 || !strings.Contains(got[len(got)-1], "DELETE /v1/auth/passkeys/c1") {
		t.Fatalf("%+v %v", r, got)
	}
}

func TestPermissionsVerifyGetAndSetOnlyRequests(t *testing.T) {
	var got []string
	keysHub(t, &got)
	r := run(t, "", false, "permissions", "verify", "get")
	if r.code != 0 || !strings.Contains(r.out, "tier.T3") || !strings.Contains(r.out, "type:backup.restore") ||
		!strings.Contains(r.out, "No owner has a proven key yet") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "permissions", "verify", "set", "tier.T3", "l9"); r.code != ExitUsage {
		t.Fatalf("a bad level must be a usage error: %+v", r)
	}
	r = run(t, "", false, "permissions", "verify", "set", "tier.T3", "l1")
	last := got[len(got)-1]
	if r.code != 0 || !strings.Contains(last, "POST /v1/actions") || !strings.Contains(last, `"type":"verification.requirement.set"`) ||
		!strings.Contains(last, `"level":"L1"`) || !strings.Contains(r.out, "act-7") {
		t.Fatalf("%+v %s", r, last)
	}
}

func TestKeysModelsListAddRemove(t *testing.T) {
	var got []string
	keysHub(t, &got)
	if r := run(t, "", false, "keys", "models", "list"); r.code != 0 || !strings.Contains(r.out, "Test Bio Key") || !strings.Contains(r.out, "yes") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "keys", "models", "add", "a1b2"); r.code != ExitUsage {
		t.Fatalf("missing flags must be a usage error: %+v", r)
	}
	pem := filepath.Join(t.TempDir(), "root.pem")
	if err := os.WriteFile(pem, []byte("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	r := run(t, "", false, "keys", "models", "add", "a1b2", "--name", "Test Bio Key", "--root", pem, "--uv", "fingerprint_internal")
	last := got[len(got)-1]
	if r.code != 0 || !strings.Contains(last, `"type":"authenticator.allowlist.add"`) || !strings.Contains(last, "BEGIN CERTIFICATE") {
		t.Fatalf("%+v %s", r, last)
	}
	if r = run(t, "", false, "keys", "models", "remove", "a1b2"); r.code != 0 || !strings.Contains(r.out, "no longer trusted") {
		t.Fatalf("%+v", r)
	}
}
