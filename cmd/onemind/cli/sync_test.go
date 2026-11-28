// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answer has the shape of GET /v1/sync/changes (SyncChanges in sdk/openapi).
const syncBody = `{"root":"shared","revision":7,"has_more":false,"next_cursor":"AAAAAAAAAAcabcdefabcdefabcdefab",
"changes":[{"id":"fil_01JD0000000000000000000001","parent_id":null,"path":"/Docs","name":"Docs","type":"dir","size":null,
"mtime":"2026-11-21T10:00:00Z","hash":null,"revision":5,"deleted":false},
{"id":"fil_01JD0000000000000000000002","parent_id":"fil_01JD0000000000000000000001","path":"/Docs/a.txt","name":"a.txt",
"type":"file","size":12,"mtime":"2026-11-21T10:00:00Z","hash":"sha256:00","revision":6,"deleted":false},
{"id":"fil_01JD0000000000000000000003","parent_id":null,"path":"/old.txt","name":"old.txt","type":"file","size":3,
"mtime":"2026-11-21T10:00:00Z","hash":null,"revision":7,"deleted":true}]}`

func syncHub(t *testing.T, seen *string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/sync/changes" || r.Method != http.MethodGet || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		*seen = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(syncBody))
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestSyncChangesTableAndCursor(t *testing.T) {
	var q string
	syncHub(t, &q)
	r := run(t, "", false, "sync", "changes", "--root", "shared", "--cursor", "AAAAAAAAAAU", "--limit", "50")
	if r.code != 0 {
		t.Fatalf("sync changes %+v", r)
	}
	if !strings.Contains(q, "root=shared") || !strings.Contains(q, "cursor=AAAAAAAAAAU") || !strings.Contains(q, "limit=50") {
		t.Fatalf("query %q", q)
	}
	for _, want := range []string{"/Docs/a.txt", "fil_01JD0000000000000000000002", "deleted", "next cursor: AAAAAAAAAAcabcdefabcdefabcdefab", "revision 7"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
}

func TestSyncChangesNeedsARoot(t *testing.T) {
	var q string
	syncHub(t, &q)
	if r := run(t, "", false, "sync", "changes"); r.code == 0 || q != "" {
		t.Fatalf("sync changes without --root ran: %+v (query %q)", r, q)
	}
}
