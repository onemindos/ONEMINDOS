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

func photosHub(t *testing.T) (*sync.Mutex, *[]map[string]any, *int) {
	t.Helper()
	isolate(t)
	var mu sync.Mutex
	var put []map[string]any
	var approvals int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch {
		case r.URL.Path == "/v1/settings/photos" && r.Method == http.MethodGet:
			jsonOut(w, 200, map[string]any{"enabled": false, "owner_switch_on": false, "operator_off": false,
				"can_change": true, "pending_action_id": "act-9"})
		case r.URL.Path == "/v1/settings/photos" && r.Method == http.MethodPut:
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			put = append(put, b)
			jsonOut(w, 202, map[string]any{"id": "act-1", "type": "app.enable", "params": map[string]any{"app_id": "photos"},
				"state": "awaiting_approval", "requested_by": map[string]any{"id": "owner", "kind": "person"},
				"idempotency_key": "k", "created_at": "2026-11-27T09:00:00Z", "updated_at": "t",
				"expires_at": "2026-11-27T09:10:00Z", "version": 1})
		case r.URL.Path == "/v1/instance":
			jsonOut(w, 200, map[string]any{"name": "Test", "version": "0.1.0", "hub_node_id": "abc"})
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/approve"):
			approvals++
			jsonOut(w, 200, map[string]string{"id": "act-1", "state": "succeeded"})
		default:
			t.Logf("unexpected %s %s", r.Method, r.URL.Path)
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &mu, &put, &approvals
}

func TestPhotosSettingsShowsTheSwitchAsJSON(t *testing.T) {
	photosHub(t)
	r := run(t, "", false, "photos", "settings", "--json")
	var v photosView
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || v.Enabled || v.OwnerSwitchOn || v.PendingActionID == nil || *v.PendingActionID != "act-9" {
		t.Fatalf("photos settings --json %+v", r)
	}
	r = run(t, "", false, "photos", "settings")
	if r.code != 0 || !strings.Contains(r.out, "photos: off") || !strings.Contains(r.out, "act-9") {
		t.Fatalf("photos settings %+v", r)
	}
}

func TestPhotosSettingsOnFilesARequestAndNeverApprovesAlone(t *testing.T) {
	mu, put, approvals := photosHub(t)
	r := run(t, "", false, "photos", "settings", "--on", "--no-approve", "--json")
	var action struct {
		ID    string `json:"id"`
		State string `json:"state"`
	}
	if r.code != 0 || json.Unmarshal([]byte(r.out), &action) != nil || action.ID != "act-1" || action.State != "awaiting_approval" {
		t.Fatalf("on %+v", r)
	}
	if r := run(t, "", false, "photos", "settings", "--off"); r.code != 0 || !strings.Contains(r.out, "onemind actions approve act-1") {
		t.Fatalf("off in non-interactive shell %+v", r)
	}
	if r := run(t, "", true, "photos", "settings", "--off"); r.code != 0 || !strings.Contains(r.out, "onemind actions approve act-1") {
		t.Fatalf("off in interactive shell %+v", r)
	}
	if r := run(t, "", false, "photos", "settings", "--off", "--yes"); r.code != ExitUsage {
		t.Fatalf("off with --yes %+v", r)
	}
	if r := run(t, "", false, "photos", "settings", "--on", "--off"); r.code != ExitUsage {
		t.Fatalf("on and off %+v", r)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(*put) != 3 || (*put)[0]["enabled"] != true || (*put)[1]["enabled"] != false || (*put)[2]["enabled"] != false || *approvals != 0 {
		t.Fatalf("requests = %v, approvals = %d", *put, *approvals)
	}
}
