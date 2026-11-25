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

// nameHub answers like core/onemind_core/routers/instance_name.py: the open name, and a rename filed as an
// action awaiting approval.
func nameHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.Path+" "+string(body))
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/instance/name":
			jsonOut(w, 200, map[string]string{"name": "onemind"})
		case r.Header.Get("Authorization") != "Bearer "+ownerTok:
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
		case r.Method == http.MethodPut && r.URL.Path == "/v1/instance/name":
			var in map[string]any
			_ = json.Unmarshal(body, &in)
			jsonOut(w, 202, map[string]any{"id": "act-9", "type": "instance.rename", "state": "awaiting_approval",
				"params": map[string]any{"name": in["name"]}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestNameShow(t *testing.T) {
	var got []string
	nameHub(t, &got)
	if r := run(t, "", false, "name", "show"); r.code != 0 || r.out != "onemind\n" {
		t.Fatalf("name show %+v", r)
	}
	r := run(t, "", false, "--json", "name", "show")
	var j struct{ Name string }
	if r.code != 0 || json.Unmarshal([]byte(r.out), &j) != nil || j.Name != "onemind" {
		t.Fatalf("name show --json %+v", r)
	}
}

func TestNameSetPrintsTheApprovalIDAndNeverApproves(t *testing.T) {
	var got []string
	nameHub(t, &got)
	r := run(t, "", false, "name", "set", "kitchen", "--reason", "label")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") || !strings.Contains(r.out, "kitchen.local") {
		t.Fatalf("name set %+v", r)
	}
	if len(got) != 1 || !strings.HasPrefix(got[0], `PUT /v1/instance/name {"idempotency_key":"cli-`) || !strings.Contains(got[0], `"name":"kitchen"`) {
		t.Fatalf("asked %v", got)
	}
	for _, g := range got {
		if strings.Contains(g, "approve") {
			t.Fatalf("the CLI must never approve: %v", got)
		}
	}
	r = run(t, "", false, "--json", "name", "set", "garage")
	var act map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &act) != nil || act["state"] != "awaiting_approval" {
		t.Fatalf("name set --json %+v", r)
	}
}

func TestNameSetRefusesABadNameBeforeAskingTheHub(t *testing.T) {
	var got []string
	nameHub(t, &got)
	for _, bad := range []string{"Kitchen", "my box", "-x", "x-", "a.b", strings.Repeat("a", 64)} {
		if r := run(t, "", false, "name", "set", bad); r.code != ExitUsage {
			t.Errorf("%q: %+v", bad, r)
		}
	}
	if len(got) != 0 {
		t.Fatalf("a bad name must not reach the hub: %v", got)
	}
}
