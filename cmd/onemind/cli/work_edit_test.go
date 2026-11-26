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

// workEditHub answers the Work routes the edit commands call, and logs method, path, If-Match and body.
func workEditHub(t *testing.T) *[]string {
	t.Helper()
	isolate(t)
	seen := &[]string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		raw, _ := io.ReadAll(r.Body)
		*seen = append(*seen, r.Method+" "+r.URL.Path+" if-match="+r.Header.Get("If-Match")+" idem="+r.Header.Get("Idempotency-Key")+" "+string(raw))
		task := `{"id":"tsk_1","project_id":"prj_1","revision":7,"title":"Pay rent","body":"","status":"todo","priority":2,"labels":[],"dependencies":[]}`
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/work/projects":
			var b map[string]any
			_ = json.Unmarshal(raw, &b)
			w.WriteHeader(201)
			_, _ = w.Write([]byte(`{"id":"prj_9","name":"` + b["name"].(string) + `","ai_access":"read"}`))
		case r.URL.Path == "/v1/work/projects/prj_1/tasks/tsk_1" && r.Method == http.MethodGet:
			_, _ = w.Write([]byte(task))
		case r.URL.Path == "/v1/work/projects/prj_1/tasks/tsk_1" && r.Method == http.MethodPatch:
			if r.Header.Get("If-Match") != "7" {
				w.WriteHeader(409)
				_, _ = w.Write([]byte(`{"error":"stale_precondition","message":"task changed"}`))
				return
			}
			_, _ = w.Write([]byte(strings.Replace(task, "Pay rent", "Pay the rent", 1)))
		case r.URL.Path == "/v1/work/projects/prj_1/tasks/tsk_1" && r.Method == http.MethodDelete:
			w.WriteHeader(204)
		default:
			w.WriteHeader(404)
			_, _ = w.Write([]byte(`{"error":"not_found","message":"x"}`))
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return seen
}

func TestWorkProjectAddSendsAKeyAndTheAccess(t *testing.T) {
	seen := workEditHub(t)
	r := run(t, "", false, "work", "project-add", "Home", "chores", "--ai-access", "read")
	if r.code != 0 || !strings.Contains(r.out, "Created project prj_9") || !strings.Contains(r.out, "Home chores") {
		t.Fatalf("add %+v", r)
	}
	if got := (*seen)[0]; !strings.HasPrefix(got, "POST /v1/work/projects ") || !strings.Contains(got, "idem=") || strings.Contains(got, "idem= ") || !strings.Contains(got, `"ai_access":"read"`) {
		t.Fatalf("request %q", got)
	}
}

func TestWorkEditReadsTheRevisionAndSendsOnlyWhatChanged(t *testing.T) {
	seen := workEditHub(t)
	r := run(t, "", false, "work", "edit", "prj_1", "tsk_1", "--title", "Pay the rent", "--priority", "1", "--due", "2026-12-01T17:00:00Z")
	if r.code != 0 || !strings.Contains(r.out, "Updated tsk_1: Pay the rent") {
		t.Fatalf("edit %+v", r)
	}
	patch := (*seen)[1]
	if !strings.HasPrefix(patch, "PATCH /v1/work/projects/prj_1/tasks/tsk_1 if-match=7") || !strings.Contains(patch, `"priority":1`) || !strings.Contains(patch, `"due_at":"2026-12-01T17:00:00Z"`) || strings.Contains(patch, `"status"`) {
		t.Fatalf("patch %q", patch)
	}
	if r := run(t, "", false, "work", "edit", "prj_1", "tsk_1", "--due", "none"); r.code != 0 || !strings.Contains((*seen)[3], `"due_at":null`) {
		t.Fatalf("clear due %+v / %v", r, *seen)
	}
}

func TestWorkEditRefusesBadInputBeforeAnyRequest(t *testing.T) {
	seen := workEditHub(t)
	for _, args := range [][]string{
		{"work", "edit", "prj_1", "tsk_1"},
		{"work", "edit", "prj_1", "tsk_1", "--priority", "9"},
		{"work", "edit", "prj_1", "tsk_1", "--due", "tomorrow"},
		{"work", "edit", "prj_1", "tsk_1", "--status", "later"},
		{"work", "edit", "prj_1", "tsk_1", "--title", ""},
	} {
		if r := run(t, "", false, args...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", args, r)
		}
	}
	if len(*seen) != 0 {
		t.Fatalf("no request expected, got %v", *seen)
	}
}

func TestWorkDeleteSendsTheRevisionItRead(t *testing.T) {
	seen := workEditHub(t)
	if r := run(t, "", false, "work", "delete", "prj_1", "tsk_1"); r.code != 0 || !strings.Contains(r.out, "Deleted tsk_1") {
		t.Fatalf("delete %+v", r)
	}
	if got := (*seen)[1]; !strings.HasPrefix(got, "DELETE /v1/work/projects/prj_1/tasks/tsk_1 if-match=7") {
		t.Fatalf("request %q", got)
	}
}
