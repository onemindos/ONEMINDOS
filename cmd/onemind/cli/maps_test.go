// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

func startMapsHub(t *testing.T) *[]string {
	t.Helper()
	isolate(t)
	var calls []string
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		b, _ := io.ReadAll(r.Body)
		calls = append(calls, r.Method+" "+r.URL.RequestURI()+" "+string(b))
		switch {
		case r.URL.Path == "/v1/instance":
			jsonOut(w, 200, map[string]any{"name": "Box", "version": "0.1.0", "hub_node_id": "n"})
		case r.URL.Path == "/v1/map/packs":
			jsonOut(w, 200, map[string]any{"free_bytes": 20500000000, "packs": []any{map[string]any{"id": "eu-west", "region": "Western Europe", "bytes": 412000000, "installed_at": "2026-11-01T10:00:00Z"}}})
		case r.URL.Path == "/v1/sites":
			jsonOut(w, 200, []any{map[string]any{"id": "home", "name": "Family house", "floors": []any{1}, "areas": []any{1, 2}}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/actions":
			var in map[string]any
			_ = json.Unmarshal(b, &in)
			jsonOut(w, 201, map[string]any{"id": "act-3", "type": in["type"], "state": "awaiting_approval"})
		case r.URL.Path == "/v1/subjects":
			jsonOut(w, 200, map[string]any{"kinds": []any{map[string]any{"kind": "sensor", "stream": "SENSORS", "retention": map[string]any{"policy": "limits"},
				"subjects": []any{map[string]any{"publishers": []any{"app", "node"}}}}}})
		case r.URL.Path == "/v1/subjects/check":
			jsonOut(w, 200, map[string]any{"ok": r.URL.Query().Get("publisher") == "node", "reason": "checked", "kind": "sensor", "pattern": "om.sensor.>"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &calls
}

func TestMapPacksAndSitesList(t *testing.T) {
	startMapsHub(t)
	r := run(t, "", false, "map", "packs", "list")
	for _, want := range []string{"free for map packs: 20.5 GB", "eu-west", "Western Europe", "412 MB"} {
		if r.code != 0 || !strings.Contains(r.out, want) {
			t.Fatalf("missing %q: %+v", want, r)
		}
	}
	r = run(t, "", false, "map", "sites", "list")
	if r.code != 0 || !strings.Contains(r.out, "Family house") || !strings.Contains(r.out, "1") || !strings.Contains(r.out, "2") {
		t.Fatalf("sites %+v", r)
	}
}

func TestMapPackRequestsOnlyFileAnAction(t *testing.T) {
	calls := startMapsHub(t)
	if r := run(t, "", false, "map", "packs", "remove", "eu-west"); r.code != 0 || !strings.Contains(r.out, "act-3") {
		t.Fatalf("remove %+v", r)
	}
	if r := run(t, "", false, "map", "packs", "add", "us-east", "--reason", "trip"); r.code != 0 {
		t.Fatalf("add %+v", r)
	}
	var posts []string
	for _, c := range *calls {
		if strings.HasPrefix(c, "POST /v1/actions") {
			posts = append(posts, c)
		}
		if strings.Contains(c, "/approve") {
			t.Fatalf("the CLI must never approve: %v", *calls)
		}
	}
	if len(posts) != 2 || !strings.Contains(posts[0], `"type":"map.pack.remove"`) || !strings.Contains(posts[0], `"pack_id":"eu-west"`) ||
		!strings.Contains(posts[1], `"type":"map.pack.add"`) || !strings.Contains(posts[1], `"region_id":"us-east"`) || !strings.Contains(posts[1], `"reason":"trip"`) {
		t.Fatalf("posts %q", posts)
	}
}

func TestSubjectsListAndCheck(t *testing.T) {
	calls := startMapsHub(t)
	r := run(t, "", false, "subjects", "list")
	if r.code != 0 || !strings.Contains(r.out, "sensor") || !strings.Contains(r.out, "node,app") || !strings.Contains(r.out, "SENSORS") {
		t.Fatalf("list %+v", r)
	}
	r = run(t, "", false, "subjects", "check", "om.sensor.x", "--publisher", "node", "--owner-id", "n1")
	if r.code != 0 || !strings.Contains(r.out, "allowed") || strings.Contains(r.out, "not allowed") {
		t.Fatalf("check %+v", r)
	}
	if got := (*calls)[len(*calls)-1]; !strings.Contains(got, "owner_id=n1") || !strings.Contains(got, "publisher=node") {
		t.Fatalf("query %q", got)
	}
	if r := run(t, "", false, "subjects", "check", "om.sensor.x", "--publisher", "app"); r.code != 0 || !strings.Contains(r.out, "not allowed") {
		t.Fatalf("a refusal is an answer, not an error: %+v", r)
	}
	if r := run(t, "", false, "subjects", "check", "x", "--publisher", "robot"); r.code == 0 {
		t.Fatalf("an unknown publisher is refused: %+v", r)
	}
}
