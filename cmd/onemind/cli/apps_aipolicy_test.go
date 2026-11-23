// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// #165: `onemind apps` shows each app's aiPolicy as GET /v1/apps sends it.
func TestAppsShowAIPolicy(t *testing.T) {
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/apps" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource"})
			return
		}
		row := func(id, category string, policy any) map[string]any {
			m := map[string]any{"id": id, "name": id, "version": "1.0", "category": category, "installed": false,
				"status": "not_installed", "archs": []string{"amd64"}, "requires": map[string]any{}, "links": map[string]any{}}
			if policy != nil {
				m["aiPolicy"] = policy
			}
			return m
		}
		jsonOut(w, 200, []any{row("oura", "health", "display-only"), row("notes", "productivity", "allowed"),
			row("ntfy", "tools", nil), row("odd", "tools", "unknown")})
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	r := run(t, "", false, "--hub", srv.URL, "apps", "list")
	if r.code != 0 || !strings.Contains(r.out, "\tAI\t") && !strings.Contains(r.out, " AI ") {
		t.Fatalf("no AI column: %+v", r)
	}
	for id, want := range map[string]string{"oura": "display-only", "notes": "allowed", "ntfy": "none", "odd": "unknown"} {
		line := ""
		for _, l := range strings.Split(r.out, "\n") {
			if strings.HasPrefix(l, id+" ") {
				line = l
			}
		}
		if !strings.Contains(line, " "+want+" ") {
			t.Errorf("%s: want aiPolicy %q in %q", id, want, line)
		}
	}

	for id, want := range map[string]string{
		"oura":  "display-only: shown to people, never to AI",
		"ntfy":  "none declared: agents see this catalog entry, never the app's data",
		"notes": "allowed: agents and models may use the app's data",
		"odd":   "unknown value in the manifest: treated as deny",
	} {
		r := run(t, "", false, "--hub", srv.URL, "apps", "info", id)
		if r.code != 0 || !strings.Contains(r.out, "ai policy") || !strings.Contains(r.out, want) {
			t.Errorf("info %s: want %q in %+v", id, want, r)
		}
	}

	r = run(t, "", false, "--hub", srv.URL, "--json", "apps", "info", "oura")
	if r.code != 0 || !strings.Contains(r.out, `"aiPolicy": "display-only"`) {
		t.Fatalf("json info: %+v", r)
	}
}
