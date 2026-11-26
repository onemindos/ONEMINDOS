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

func startFilesHub(t *testing.T) *[]string {
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
		case r.Method == http.MethodGet && r.URL.Path == "/v1/files/quotas":
			jsonOut(w, 200, []any{
				map[string]any{"person_id": "kid", "root": "home:kid", "limit_bytes": 1610612736, "used_bytes": 1048576},
				map[string]any{"person_id": nil, "root": "shared", "limit_bytes": nil, "used_bytes": 0},
			})
		case r.Method == http.MethodPut && r.URL.Path == "/v1/files/quotas/kid":
			var in map[string]any
			_ = json.Unmarshal(b, &in)
			jsonOut(w, 200, map[string]any{"person_id": "kid", "root": "home:kid", "limit_bytes": in["limit_bytes"], "used_bytes": 1048576})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/files/stat":
			jsonOut(w, 200, map[string]any{"name": "notes.txt", "path": "/notes.txt", "root": "home:owner", "type": "file", "size": 12, "mtime": "2026-11-20T10:00:00Z", "access": "read-write"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &calls
}

func TestFilesQuotasList(t *testing.T) {
	startFilesHub(t)
	r := run(t, "", false, "files", "quotas", "list")
	for _, want := range []string{"kid", "home:kid", "1.5 GB", "no limit", "shared"} {
		if r.code != 0 || !strings.Contains(r.out, want) {
			t.Fatalf("missing %q: %+v", want, r)
		}
	}
}

func TestFilesQuotasSetSendsBytesOrNull(t *testing.T) {
	calls := startFilesHub(t)
	if r := run(t, "", false, "files", "quotas", "set", "kid", "--gb", "2"); r.code != 0 || !strings.Contains(r.out, "Limit for kid is now 2 GB.") {
		t.Fatalf("set %+v", r)
	}
	if r := run(t, "", false, "files", "quotas", "set", "kid", "--none"); r.code != 0 || !strings.Contains(r.out, "no limit") {
		t.Fatalf("none %+v", r)
	}
	want := []string{`PUT /v1/files/quotas/kid {"limit_bytes":2147483648}`, `PUT /v1/files/quotas/kid {"limit_bytes":null}`}
	if strings.Join(*calls, "\n") != strings.Join(want, "\n") {
		t.Fatalf("calls %q", *calls)
	}
}

func TestFilesQuotasSetNeedsExactlyOneOption(t *testing.T) {
	calls := startFilesHub(t)
	for _, args := range [][]string{
		{"files", "quotas", "set", "kid"},
		{"files", "quotas", "set", "kid", "--gb", "1", "--none"},
		{"files", "quotas", "set", "kid", "--gb", "-1"},
	} {
		if r := run(t, "", false, args...); r.code == 0 {
			t.Fatalf("%v must be refused: %+v", args, r)
		}
	}
	if len(*calls) != 0 {
		t.Fatalf("nothing may reach the gateway: %q", *calls)
	}
}

func TestFilesStat(t *testing.T) {
	calls := startFilesHub(t)
	r := run(t, "", false, "files", "stat", "/notes.txt", "--root", "home:owner")
	if r.code != 0 || !strings.Contains(r.out, "notes.txt") || !strings.Contains(r.out, "read-write") {
		t.Fatalf("stat %+v", r)
	}
	if got := (*calls)[0]; !strings.HasPrefix(got, "GET /v1/files/stat?path=%2Fnotes.txt&root=home%3Aowner") {
		t.Fatalf("query %q", got)
	}
}
