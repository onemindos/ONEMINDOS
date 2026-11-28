// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// grantsHub answers like routers/datagrants.py and routers/host_grants.py. agentTok is an AI agent: it sees its
// own data grants, and the gateway refuses it the host list and every revoke.
func grantsHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	data := []map[string]any{
		{"id": "dgr_1", "data_class": "location", "grantee": map[string]string{"kind": "app", "id": "owntracks"}, "read": true, "write": false,
			"aggregate": true, "expires_at": "2099-01-01T00:00:00Z", "active": true},
		{"id": "dgr_old", "data_class": "activity", "grantee": map[string]string{"kind": "agent", "id": "agent:hermes"}, "read": true, "write": false,
			"aggregate": false, "expires_at": "2026-01-01T00:00:00Z", "active": false},
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*got = append(*got, r.Method+" "+r.URL.RequestURI()+" key="+r.Header.Get("Idempotency-Key"))
		owner := r.Header.Get("Authorization") == "Bearer "+ownerTok
		if !owner && r.Header.Get("Authorization") != "Bearer "+agentTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/data/grants":
			if !owner {
				jsonOut(w, 200, data[1:])
				return
			}
			jsonOut(w, 200, data)
		case !owner:
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "owner only"})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/data/grants/dgr_1":
			out := map[string]any{}
			for k, v := range data[0] {
				out[k] = v
			}
			out["active"] = false
			jsonOut(w, 200, out)
		case r.Method == http.MethodGet && r.URL.Path == "/v1/host-grants":
			jsonOut(w, 200, map[string]any{"grants": []map[string]any{
				{"id": "hg_1", "app_id": "zigbee2mqtt", "kind": "device", "device_class": "usb-serial", "path": "/dev/ttyUSB0", "reason": "Zigbee stick",
					"active": true, "granted_at": "2026-11-02T00:00:00Z"},
			}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/host-grants/hg_1/revoke":
			jsonOut(w, 200, map[string]any{"id": "hg_1", "app_id": "zigbee2mqtt", "kind": "device", "active": false, "granted_at": "2026-11-02T00:00:00Z"})
		case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/v1/host-grants/"):
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no active host grant with this id"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestGrantsDataListAndRevoke(t *testing.T) {
	var got []string
	grantsHub(t, &got)
	r := run(t, "", false, "grants", "data", "list")
	if r.code != 0 || !strings.Contains(r.out, "app:owntracks") || !strings.Contains(r.out, "read, count") || strings.Contains(r.out, "hermes") ||
		!strings.Contains(r.errOut, "1 ended or revoked") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "grants", "data", "list", "--all"); !strings.Contains(r.out, "agent:hermes") || !strings.Contains(r.out, "ended") {
		t.Fatalf("%+v", r)
	}
	var list []dataGrant
	if r = run(t, "", false, "--json", "grants", "data", "list"); r.code != 0 || json.Unmarshal([]byte(r.out), &list) != nil || len(list) != 2 {
		t.Fatalf("--json is the gateway's list unchanged: %+v", r)
	}
	r = run(t, "", false, "grants", "data", "revoke", "dgr_1")
	if r.code != 0 || !strings.Contains(r.out, "owntracks no longer reaches location data") {
		t.Fatalf("%+v", r)
	}
	if last := got[len(got)-1]; !strings.HasPrefix(last, "DELETE /v1/data/grants/dgr_1 key=cli-") {
		t.Fatalf("revoke sends an Idempotency-Key: %q", last)
	}
}

func TestGrantsHostListAndRevoke(t *testing.T) {
	var got []string
	grantsHub(t, &got)
	r := run(t, "", false, "grants", "host", "list", "--app", "zigbee2mqtt")
	if r.code != 0 || !strings.Contains(r.out, "device usb-serial /dev/ttyUSB0") || !strings.Contains(got[len(got)-1], "?app_id=zigbee2mqtt") {
		t.Fatalf("%+v %v", r, got)
	}
	if r = run(t, "", false, "grants", "host", "revoke", "hg_1"); r.code != 0 || !strings.Contains(r.out, "zigbee2mqtt no longer reaches device") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "grants", "host", "revoke", "hg_gone"); r.code != ExitNotFound {
		t.Fatalf("%+v", r)
	}
}

func TestGrantsAgentSeesOwnAndCannotRevoke(t *testing.T) {
	var got []string
	grantsHub(t, &got)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "grants", "data", "list", "--all"); r.code != 0 || !strings.Contains(r.out, "agent:hermes") || strings.Contains(r.out, "owntracks") {
		t.Fatalf("%+v", r)
	}
	for _, args := range [][]string{{"grants", "data", "revoke", "dgr_1"}, {"grants", "host", "revoke", "hg_1"}, {"grants", "host", "list"}} {
		if r := run(t, "", false, args...); r.code != ExitPermissionDenied {
			t.Fatalf("%v: %+v", args, r)
		}
	}
}
