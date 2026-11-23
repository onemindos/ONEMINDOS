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

const systemBody = `[{"id":"files","name":"Files","kind":"native","update":"os","disable":"never","enabled":true,"can_disable":false},
{"id":"notebook","name":"Notebook","kind":"container","update":"own","disable":"allowed","enabled":false,"can_disable":true,
"status":"stopped","version":"1.2.0","license":"MIT","update_channel":"stable"}]`

func systemHub(t *testing.T) (*sync.Mutex, *[]map[string]any) {
	t.Helper()
	isolate(t)
	var mu sync.Mutex
	var filed []map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch {
		case r.URL.Path == "/v1/system-apps":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(systemBody))
		case r.URL.Path == "/v1/actions" && r.Method == http.MethodPost:
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			filed = append(filed, b)
			jsonOut(w, 201, map[string]any{"id": "act-1", "type": b["type"], "params": b["params"], "state": "awaiting_approval",
				"requested_by": map[string]any{"id": "owner", "kind": "person"}, "idempotency_key": b["idempotency_key"],
				"created_at": "2026-11-12T09:00:00Z", "updated_at": "t", "expires_at": b["expires_at"], "version": 1})
		case r.URL.Path == "/v1/instance":
			jsonOut(w, 200, map[string]any{"name": "Test", "version": "0.1.0", "hub_node_id": "abc"})
		default:
			t.Logf("unexpected %s %s", r.Method, r.URL.Path)
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &mu, &filed
}

func TestBuiltInListShowsTheSwitchAndWhatCannotBeSwitched(t *testing.T) {
	systemHub(t)
	r := run(t, "", false, "apps", "built-in")
	if r.code != 0 || !strings.Contains(r.out, "on (always)") || !strings.Contains(r.out, "off") || !strings.Contains(r.out, "1.2.0") || !strings.Contains(r.out, "stable") {
		t.Fatalf("built-in %+v", r)
	}
}

func TestDisableFilesAnApprovalRequestForTheOwner(t *testing.T) {
	mu, filed := systemHub(t)
	r := run(t, "", false, "apps", "disable", "notebook", "--no-approve", "--json")
	mu.Lock()
	defer mu.Unlock()
	if r.code != 0 || len(*filed) != 1 || (*filed)[0]["type"] != "app.disable" {
		t.Fatalf("disable %+v filed=%v", r, *filed)
	}
	if p, _ := (*filed)[0]["params"].(map[string]any); p["app_id"] != "notebook" {
		t.Fatalf("params %v", (*filed)[0]["params"])
	}
	// no TTY and no flag: nothing is filed
	if r := run(t, "", false, "apps", "enable", "notebook"); r.code != ExitUsage || len(*filed) != 1 {
		t.Fatalf("enable without a flag %+v", r)
	}
}
