// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// desktopHub answers like core/onemind_core/routers/desktop_apps.py and files desktop.app.* actions.
func desktopHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.RequestURI()+" "+string(body))
		switch {
		case r.URL.Path == "/v1/instance":
			jsonOut(w, 200, map[string]any{"name": "box", "time": "2026-11-25T12:00:00Z"})
		case r.URL.Path == "/v1/desktop-apps":
			jsonOut(w, 200, map[string]any{"service": map[string]any{"available": true, "remote": "flathub"},
				"installed": []map[string]any{{"app_id": "md.obsidian.Obsidian", "name": "Obsidian", "version": "1.8.9",
					"update_available": true, "folder": "/data/onemind/desktop-apps/md.obsidian.Obsidian/files"}}})
		case r.URL.Path == "/v1/desktop-apps/search":
			jsonOut(w, 200, map[string]any{"results": []map[string]any{{"app_id": "md.obsidian.Obsidian", "name": "Obsidian\x1b[31m",
				"summary": "Knowledge base", "version": "1.8.9"}}})
		case r.URL.Path == "/v1/desktop-apps/md.obsidian.Obsidian/launch":
			if r.Method != http.MethodPost || r.Header.Get("Idempotency-Key") == "" {
				t.Error("launch must be an idempotent POST")
			}
			jsonOut(w, 202, map[string]any{"id": "launch-9", "state": "awaiting_approval"})
		case r.URL.Path == "/v1/actions" && r.Method == http.MethodPost:
			jsonOut(w, 201, map[string]any{"id": "act-9", "state": "awaiting_approval"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestDesktopAppSearchAndListAreTablesWithoutControlCodes(t *testing.T) {
	var got []string
	desktopHub(t, &got)
	r := run(t, "", false, "desktop-app", "search", "obsidian", "app")
	if r.code != 0 || !strings.Contains(r.out, "md.obsidian.Obsidian") || strings.Contains(r.out, "\x1b") {
		t.Fatalf("search %+v", r)
	}
	if !strings.Contains(got[len(got)-1], "q=obsidian+app") {
		t.Fatalf("asked %v", got)
	}
	r = run(t, "", false, "desktop-app", "list")
	if r.code != 0 || !strings.Contains(r.out, "update waiting") || !strings.Contains(r.out, "/files") {
		t.Fatalf("list %+v", r)
	}
	r = run(t, "", false, "--json", "desktop-app", "list")
	if r.code != 0 || !strings.Contains(r.out, `"app_id": "md.obsidian.Obsidian"`) {
		t.Fatalf("list --json %+v", r)
	}
}

func TestDesktopAppInstallUpdateRemoveOnlyFileARequest(t *testing.T) {
	for _, verb := range []string{"install", "update", "remove"} {
		var got []string
		desktopHub(t, &got)
		r := run(t, "", false, "desktop-app", verb, "md.obsidian.Obsidian")
		if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") || !strings.Contains(r.out, "An owner approves") {
			t.Fatalf("%s %+v", verb, r)
		}
		var posted string
		for _, g := range got {
			if strings.HasPrefix(g, "POST /v1/actions ") {
				posted = g
			}
			if strings.Contains(g, "/approve") {
				t.Fatalf("the CLI must never approve: %v", got)
			}
		}
		if !strings.Contains(posted, `"type":"desktop.app.`+verb+`"`) || !strings.Contains(posted, `"app_id":"md.obsidian.Obsidian"`) ||
			!strings.Contains(posted, `"expires_at":"`+time.Now().UTC().Add(24*time.Hour).Format("2006-01-02")+`T`) {
			t.Fatalf("%s posted %q", verb, posted)
		}
	}
}

func TestDesktopAppLaunch(t *testing.T) {
	var got []string
	desktopHub(t, &got)
	r := run(t, "", false, "desktop-app", "launch", "md.obsidian.Obsidian")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: launch-9") || !strings.Contains(r.out, "An owner approves") {
		t.Fatalf("launch %+v", r)
	}
	if len(got) != 1 || !strings.HasPrefix(got[0], "POST /v1/desktop-apps/md.obsidian.Obsidian/launch ") {
		t.Fatalf("launch must only file the request: %v", got)
	}
	if r := run(t, "", false, "desktop-app", "launch", "nope.nope.Nope"); r.code == 0 {
		t.Fatalf("an unknown app must fail: %+v", r)
	}
}
