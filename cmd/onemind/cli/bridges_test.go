// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answers have the shape of core/onemind_core/bridges.py BridgeStatus (#610).
const pausedBridge = `{"id":"quake-feed","app_status":"installed","state":"paused","provider":"usgs","mode":"poll",
"data_class":"public","emits":[{"kind":"intel","name":"quakes"}],"events_per_second":10,"burst":20,"max_event_bytes":2048,
"paused_at":"2026-11-22T10:00:00Z","paused_reason":"layer quakes is not one of this bridge's emits","accepted":20,
"duplicates":3,"rejected":20,"throttled":980,"recent_rejects":0,"last_event_at":"2026-11-22T09:59:00Z",
"last_reject_reason":"layer quakes is not one of this bridge's emits","entities":12}`

func bridgeHub(t *testing.T) *[]string {
	t.Helper()
	isolate(t)
	seen := &[]string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*seen = append(*seen, r.Method+" "+r.URL.Path)
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/bridges":
			_, _ = w.Write([]byte("[" + pausedBridge + "]"))
		case "GET /v1/bridges/quake-feed":
			_, _ = w.Write([]byte(pausedBridge))
		case "POST /v1/bridges/quake-feed/resume":
			_, _ = w.Write([]byte(strings.Replace(pausedBridge, `"state":"paused"`, `"state":"active"`, 1)))
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such bridge"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return seen
}

func TestBridgeListStatusAndResume(t *testing.T) {
	seen := bridgeHub(t)
	r := run(t, "", false, "bridge", "list")
	for _, want := range []string{"ID", "THROTTLED", "quake-feed", "paused", "usgs", "10/s (burst 20)", "980"} {
		if r.code != 0 || !strings.Contains(r.out, want) {
			t.Fatalf("bridge list: missing %q in %+v", want, r)
		}
	}
	r = run(t, "", false, "bridge", "status", "quake-feed")
	for _, want := range []string{"Paused", "not one of this bridge's emits", "onemind bridge resume quake-feed",
		"20 (3 already seen)", "intel quakes", "10 events/s, burst 20, 2048 bytes an event"} {
		if r.code != 0 || !strings.Contains(r.out, want) {
			t.Fatalf("bridge status: missing %q in %+v", want, r)
		}
	}
	if r = run(t, "", false, "bridge", "resume", "quake-feed"); r.code != 0 || !strings.Contains(r.out, "quake-feed: active") {
		t.Fatalf("bridge resume %+v", r)
	}
	if r = run(t, "", false, "bridge", "status", "nope"); r.code == 0 {
		t.Fatalf("a missing bridge must fail: %+v", r)
	}
	want := "GET /v1/bridges,GET /v1/bridges/quake-feed,POST /v1/bridges/quake-feed/resume,GET /v1/bridges/nope"
	if got := strings.Join(*seen, ","); got != want {
		t.Fatalf("requests %s, want %s", got, want)
	}
}

func TestBridgeListJSON(t *testing.T) {
	bridgeHub(t)
	if r := run(t, "", false, "--json", "bridge", "list"); r.code != 0 || !strings.Contains(r.out, `"throttled": 980`) {
		t.Fatalf("bridge list --json %+v", r)
	}
}
