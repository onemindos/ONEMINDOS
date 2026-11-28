// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const workTask = `{"id":"tsk_1","project_id":"prj_1","revision":3,"title":"Pay rent","body":"","status":"todo",` +
	`"priority":1,"labels":["bills"],"due_at":"2026-11-26T22:00:00Z","dependencies":[]}`

// workHub answers the /v1/work routes with the shapes of core/onemind_core/routers/work.py.
func workHub(t *testing.T) *[]string {
	t.Helper()
	isolate(t)
	seen := &[]string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		*seen = append(*seen, r.Method+" "+r.URL.RequestURI()+" "+r.Header.Get("Idempotency-Key")+"|"+r.Header.Get("If-Match"))
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/work/quick-add":
			var body map[string]string
			_ = json.NewDecoder(r.Body).Decode(&body)
			*seen = append(*seen, "body "+body["text"]+"/"+body["tz"])
			w.WriteHeader(201)
			_, _ = w.Write([]byte(workTask))
		case r.Method == http.MethodGet && r.URL.Path == "/v1/work/tasks":
			if r.URL.Query().Get("view") == "inbox" {
				_, _ = w.Write([]byte("[]"))
				return
			}
			_, _ = w.Write([]byte("[" + workTask + "]"))
		case r.URL.Path == "/v1/work/projects/prj_1/tasks/tsk_1":
			_, _ = w.Write([]byte(strings.Replace(workTask, `"todo"`, `"done"`, 1)))
		case r.Method == http.MethodGet && r.URL.Path == "/v1/work/projects":
			_, _ = w.Write([]byte(`[{"id":"prj_1","name":"Home","ai_access":"none"}]`))
		case r.Method == http.MethodPatch && r.URL.Path == "/v1/work/projects/prj_1":
			_, _ = w.Write([]byte(`{"id":"prj_1","name":"House","ai_access":"read"}`))
		case r.Method == http.MethodDelete && strings.HasPrefix(r.URL.Path, "/v1/work/projects/prj_1"):
			w.WriteHeader(204)
		case r.Method == http.MethodPut && r.URL.Path == "/v1/work/projects/prj_1/members/ana":
			w.WriteHeader(204)
		case r.Method == http.MethodPost && r.URL.Path == "/v1/work/parse":
			_, _ = w.Write([]byte(`{"title":"Pay rent","project":null,"project_id":null,"project_found":true,"labels":["bills"],` +
				`"priority":1,"assignee":null,"due_at":null,"due_all_day":false}`))
		case r.URL.Path == "/v1/work/projects/prj_1/tasks/tsk_1/activity":
			_, _ = w.Write([]byte(`[{"id":2,"actor_id":"ana","kind":"completed","fields":[],"at":"2026-11-25T15:00:00Z"}]`))
		case r.Method == http.MethodGet && strings.HasSuffix(r.URL.Path, "/comments"):
			_, _ = w.Write([]byte(`[{"id":"cmt_1","author_id":"ana","body":"Call them","created_at":"2026-11-25T15:00:00Z"}]`))
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/comments"):
			w.WriteHeader(201)
			_, _ = w.Write([]byte(`{"id":"cmt_2","author_id":"ana","body":"x","created_at":"2026-11-25T15:00:00Z"}`))
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/sections"):
			w.WriteHeader(201)
			_, _ = w.Write([]byte(`{"id":"sec_1","project_id":"prj_1","name":"Later","position":0}`))
		case r.Method == http.MethodGet && strings.HasSuffix(r.URL.Path, "/sections"):
			_, _ = w.Write([]byte(`[{"id":"sec_1","project_id":"prj_1","name":"Later","position":0}]`))
		default:
			w.WriteHeader(404)
			_, _ = w.Write([]byte(`{"error":"not_found","message":"no"}`))
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return seen
}

func TestWorkAddSendsTheLineWithAnIdempotencyKey(t *testing.T) {
	seen := workHub(t)
	t.Setenv("TZ", "UTC")
	r := run(t, "", false, "work", "add", "Pay", "rent", "#Home", "--tz", "America/New_York", "--idempotency-key", "k1")
	if r.code != 0 || !strings.Contains(r.out, "Added tsk_1  Pay rent  due 2026-11-26 22:00 UTC") {
		t.Fatalf("add %+v", r)
	}
	if got := strings.Join(*seen, "\n"); !strings.Contains(got, "POST /v1/work/quick-add k1|") ||
		!strings.Contains(got, "body Pay rent #Home/America/New_York") {
		t.Fatalf("requests %s", got)
	}
}

func TestWorkListViewsAndDone(t *testing.T) {
	seen := workHub(t)
	if r := run(t, "", false, "work", "today"); r.code != 0 || !strings.Contains(r.out, "tsk_1") || !strings.Contains(r.out, "p1") {
		t.Fatalf("today %+v", r)
	}
	if r := run(t, "", false, "work", "inbox"); r.code != 0 || !strings.Contains(r.out, "Nothing here.") {
		t.Fatalf("inbox %+v", r)
	}
	if r := run(t, "", false, "work", "done", "prj_1", "tsk_1"); r.code != 0 || !strings.Contains(r.out, "tsk_1 is now done") {
		t.Fatalf("done %+v", r)
	}
	got := strings.Join(*seen, "\n")
	if !strings.Contains(got, "view=today") || !strings.Contains(got, "view=inbox") || !strings.Contains(got, "PATCH /v1/work/projects/prj_1/tasks/tsk_1 |3") {
		t.Fatalf("requests %s", got)
	}
}

func TestWorkAddDefaultsToTheMachineZoneAndPrintsDueTimeThere(t *testing.T) {
	seen := workHub(t)
	t.Setenv("TZ", "America/New_York")
	r := run(t, "", false, "work", "add", "Pay", "rent", "--idempotency-key", "k2")
	if r.code != 0 || !strings.Contains(r.out, "due 2026-11-26 17:00 EST") {
		t.Fatalf("add %+v", r)
	}
	if got := strings.Join(*seen, "\n"); !strings.Contains(got, "body Pay rent/America/New_York") {
		t.Fatalf("requests %s", got)
	}
}

func TestWorkProjectsParseActivityAndMembers(t *testing.T) {
	seen := workHub(t)
	if r := run(t, "", false, "work", "projects"); r.code != 0 || !strings.Contains(r.out, "prj_1") || !strings.Contains(r.out, "Home") {
		t.Fatalf("projects %+v", r)
	}
	if r := run(t, "", false, "work", "project-edit", "prj_1", "--name", "House", "--ai-access", "read"); r.code != 0 ||
		!strings.Contains(r.out, `"House" (AI access read)`) {
		t.Fatalf("edit %+v", r)
	}
	if r := run(t, "", false, "work", "parse", "Pay", "rent", "@bills", "p1", "--tz", "UTC"); r.code != 0 ||
		!strings.Contains(r.out, `title "Pay rent"`) {
		t.Fatalf("parse %+v", r)
	}
	if r := run(t, "", false, "work", "activity", "prj_1", "tsk_1"); r.code != 0 || !strings.Contains(r.out, "completed") {
		t.Fatalf("activity %+v", r)
	}
	for _, args := range [][]string{{"member-add", "prj_1", "ana"}, {"project-delete", "prj_1"}} {
		if r := run(t, "", false, append([]string{"work"}, args...)...); r.code != 0 {
			t.Fatalf("%v %+v", args, r)
		}
	}
	if got := strings.Join(*seen, "\n"); !strings.Contains(got, "PUT /v1/work/projects/prj_1/members/ana") ||
		!strings.Contains(got, "DELETE /v1/work/projects/prj_1 ") {
		t.Fatalf("requests %s", got)
	}
}

func TestWorkNotesAndSections(t *testing.T) {
	seen := workHub(t)
	if r := run(t, "", false, "work", "notes", "list", "prj_1", "tsk_1"); r.code != 0 || !strings.Contains(r.out, "Call them") {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "work", "notes", "add", "prj_1", "tsk_1", "Call", "them", "--idempotency-key", "n1"); r.code != 0 ||
		!strings.Contains(r.out, "Added cmt_2") {
		t.Fatalf("add %+v", r)
	}
	if r := run(t, "", false, "work", "notes", "section-add", "prj_1", "Later", "--idempotency-key", "s1"); r.code != 0 ||
		!strings.Contains(r.out, "Added sec_1") {
		t.Fatalf("section-add %+v", r)
	}
	if r := run(t, "", false, "work", "notes", "sections", "prj_1"); r.code != 0 || !strings.Contains(r.out, "Later") {
		t.Fatalf("sections %+v", r)
	}
	if got := strings.Join(*seen, "\n"); !strings.Contains(got, "POST /v1/work/projects/prj_1/tasks/tsk_1/comments n1|") {
		t.Fatalf("requests %s", got)
	}
}
