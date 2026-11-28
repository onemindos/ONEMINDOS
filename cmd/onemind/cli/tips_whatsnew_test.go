// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTipsWhatsNew(t *testing.T) {
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/tips/whats-new" || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		jsonOut(w, 200, map[string]any{"os_version": "0.1.2", "entries": []any{
			map[string]any{"version": "0.1.2", "title": "Faster \x1b[31mbackups", "body": "Backups now verify themselves."}}})
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "tips", "whats-new")
	if r.code != 0 || !strings.Contains(r.out, "OneMind 0.1.2") || !strings.Contains(r.out, "Backups now verify themselves.") {
		t.Fatalf("whats-new %+v", r)
	}
	if strings.Contains(r.out, "\x1b") {
		t.Fatalf("terminal escapes from the pack must not reach the terminal: %q", r.out)
	}
	if j := run(t, "", false, "tips", "whats-new", "--json"); j.code != 0 || !strings.Contains(j.out, `"os_version": "0.1.2"`) {
		t.Fatalf("--json %+v", j)
	}
}
