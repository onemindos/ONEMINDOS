// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestLegacyContactsAndClaims(t *testing.T) {
	isolate(t)
	var bodies []map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "owner only"})
			return
		}
		var b map[string]any
		_ = json.NewDecoder(r.Body).Decode(&b)
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/legacy/contacts":
			jsonOut(w, 200, []any{})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/auth/legacy/contacts":
			bodies = append(bodies, b)
			jsonOut(w, 202, map[string]any{"action_id": "action_9", "contact_id": "rc_9", "wait_days": b["wait_days"]})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/legacy/contacts/rc_9/invite":
			jsonOut(w, 200, map[string]any{"invite": "omri1.l.s", "box_key_fingerprint": "sha256:box",
				"invite_expires_at": "2026-12-02T00:00:00Z"})
		case r.URL.Path == "/v1/auth/legacy/claims":
			jsonOut(w, 200, []any{map[string]any{"id": "lcl_1", "contact_display_name": "Ana", "state": "waiting", "ends_at": "2026-12-25T00:00:00Z"}})
		case r.URL.Path == "/v1/auth/legacy/claims/lcl_1/cancel":
			bodies = append(bodies, b)
			jsonOut(w, 200, map[string]any{"id": "lcl_1", "state": "cancelled"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "legacy", "contacts", "list"); r.code != 0 ||
		!strings.Contains(r.out, "enrollment is on hold") || strings.Contains(r.out, "contacts add") {
		t.Fatalf("empty list %+v", r)
	}
	if r := run(t, "", false, "legacy", "contacts", "add", "--help"); r.code != 0 ||
		!strings.Contains(r.out, "enrollment is on hold") {
		t.Fatalf("add help %+v", r)
	}
	r := run(t, "", false, "legacy", "contacts", "add", "--name", "Ana", "--wait-days", "60")
	if r.code != 0 || !strings.Contains(r.out, "60 days") || !strings.Contains(r.out, "Approve action_9") ||
		!strings.Contains(r.out, "contacts invite rc_9") || strings.Contains(r.out, "omri1.l.s") {
		t.Fatalf("add %+v", r)
	}
	if got, _ := json.Marshal(bodies[0]); string(got) != `{"display_name":"Ana","kind":"outside","wait_days":60}` {
		t.Fatalf("add body %s", got)
	}
	if r := run(t, "", false, "legacy", "contacts", "invite", "rc_9"); r.code != 0 || !strings.Contains(r.out, "omri1.l.s") {
		t.Fatalf("approved invite %+v", r)
	}
	if r := run(t, "", false, "legacy", "claims", "list"); r.code != 0 || !strings.Contains(r.out, "lcl_1") || !strings.Contains(r.out, "Ana") {
		t.Fatalf("claims %+v", r)
	}
	if r := run(t, "", false, "legacy", "claims", "cancel", "lcl_1", "--block"); r.code != 0 || !strings.Contains(r.out, "cancelled") {
		t.Fatalf("cancel %+v", r)
	}
	if got, _ := json.Marshal(bodies[1]); string(got) != `{"block":true}` {
		t.Fatalf("cancel body %s", got)
	}
	if r := run(t, "", false, "legacy", "contacts", "add"); r.code != ExitUsage {
		t.Fatalf("empty add %+v", r)
	}
}
