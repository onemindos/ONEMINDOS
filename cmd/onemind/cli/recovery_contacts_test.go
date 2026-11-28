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

// A stand-in for the 25d owner routes: list, add (owner only; 401 step_up_required when told), remove, settings.
func recoveryGW(t *testing.T, stepUp bool) (*httptest.Server, *[]map[string]any) {
	var mu sync.Mutex
	bodies := []map[string]any{}
	contacts := []map[string]any{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "owner only"})
			return
		}
		var b map[string]any
		if r.Body != nil {
			_ = json.NewDecoder(r.Body).Decode(&b)
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/recovery/contacts":
			jsonOut(w, 200, contacts)
		case r.Method == http.MethodPost && r.URL.Path == "/v1/auth/recovery/contacts":
			if stepUp {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "sign in again", "reason": "step_up_required"})
				return
			}
			bodies = append(bodies, b)
			c := map[string]any{"id": "rc_1", "display_name": b["display_name"], "kind": b["kind"], "state": "invited",
				"cooling_off_days": 7, "invite_expires_at": "2026-12-02T00:00:00Z", "usable_at": nil,
				"invite": "omri1.payload.sig", "box_key_fingerprint": "sha256:abc"}
			contacts = append(contacts, c)
			jsonOut(w, 201, c)
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/auth/recovery/contacts/rc_1":
			contacts[0]["state"] = "removed"
			jsonOut(w, 200, contacts[0])
		case r.URL.Path == "/v1/auth/recovery/settings":
			v := 7.0
			if r.Method == http.MethodPut {
				bodies = append(bodies, b)
				v = b["cooling_off_days"].(float64)
			}
			jsonOut(w, 200, map[string]any{"values": map[string]any{"cooling_off_days": v},
				"options": map[string]any{"cooling_off_days": []any{3, 7, 14}}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	return srv, &bodies
}

func TestRecoveryContactsAddListRemoveAndSettings(t *testing.T) {
	isolate(t)
	srv, bodies := recoveryGW(t, false)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "recovery", "contacts", "list"); r.code != 0 || !strings.Contains(r.out, "No recovery contacts") {
		t.Fatalf("empty list %+v", r)
	}
	r := run(t, "", false, "recovery", "contacts", "add", "--name", "Ana", "--cooling-off-days", "14")
	if r.code != 0 || !strings.Contains(r.out, "omri1.payload.sig") || !strings.Contains(r.out, "sha256:abc") {
		t.Fatalf("add %+v", r)
	}
	if got, _ := json.Marshal((*bodies)[0]); string(got) != `{"cooling_off_days":14,"display_name":"Ana","kind":"outside"}` {
		t.Fatalf("add body %s", got)
	}
	if r := run(t, "", false, "recovery", "contacts", "list"); r.code != 0 || !strings.Contains(r.out, "rc_1") || !strings.Contains(r.out, "invited") {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "recovery", "contacts", "remove", "rc_1"); r.code != 0 || !strings.Contains(r.out, "removed") {
		t.Fatalf("remove %+v", r)
	}
	// Neither a name nor a household id is a usage error, not an empty invite.
	if r := run(t, "", false, "recovery", "contacts", "add"); r.code != ExitUsage {
		t.Fatalf("empty add %+v", r)
	}
	r = run(t, "", false, "recovery", "settings", "--cooling-off-days", "3", "--json")
	var s map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &s) != nil || s["values"].(map[string]any)["cooling_off_days"].(float64) != 3 {
		t.Fatalf("settings %+v", r)
	}
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "recovery", "contacts", "list"); r.code != ExitPermissionDenied {
		t.Fatalf("agent list %+v", r)
	}
}

func TestRecoveryContactsAddSaysHowToStepUp(t *testing.T) {
	isolate(t)
	srv, _ := recoveryGW(t, true)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "recovery", "contacts", "add", "--household", "usr_1")
	if r.code != ExitUsage || !strings.Contains(r.errOut, "passkey in the dashboard") {
		t.Fatalf("step-up %+v", r)
	}
}
