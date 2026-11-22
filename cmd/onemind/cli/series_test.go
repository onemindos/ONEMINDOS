// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSeriesQuery(t *testing.T) {
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if r.Method != "GET" || r.URL.Path != "/v1/series" || r.Header.Get("Authorization") != "Bearer "+ownerTok ||
			q.Get("node_id") != "node-1" || q.Get("metric") != "cpu_pct" || q.Get("window_s") != "3600" || q.Get("points") != "12" {
			http.Error(w, "unexpected series request", http.StatusBadRequest)
			return
		}
		jsonOut(w, http.StatusOK, []map[string]any{{"at": "2026-11-11T22:00:00Z", "value": 17.25}})
	}))
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	got := run(t, "", false, "series", "query", "node-1", "cpu_pct", "--window-s", "3600", "--points", "12")
	if got.code != 0 || !strings.Contains(got.out, "17.25") || !strings.Contains(got.out, "2026-11-11T22:00:00Z") {
		t.Fatalf("series query: %+v", got)
	}
}
