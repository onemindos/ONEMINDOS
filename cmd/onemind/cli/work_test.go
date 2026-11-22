// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// `onemind work` talks to /v1/work: add sends one line of text with an Idempotency-Key, today and
// list read, done completes. The fake gateway records what it received.
func TestWorkCommands(t *testing.T) {
	isolate(t)
	var mu sync.Mutex
	var seen []string
	var keys []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		seen = append(seen, r.Method+" "+r.URL.RequestURI())
		w.Header().Set("Content-Type", "application/json")
		task := map[string]any{"id": "tsk_1", "title": "Pay rent", "status": "todo", "priority": 1, "due_at": "2026-11-12T23:59:59Z", "due_all_day": true}
		switch {
		case r.URL.Path == "/v1/work/capture":
			keys = append(keys, r.Header.Get("Idempotency-Key"))
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			if b["text"] != "Pay rent tomorrow p1" || b["tz"] != "America/New_York" {
				w.WriteHeader(422)
				_, _ = w.Write([]byte(`{"error":"conflict","message":"bad body"}`))
				return
			}
			w.WriteHeader(201)
			_ = json.NewEncoder(w).Encode(task)
		case r.URL.Path == "/v1/work/today":
			_ = json.NewEncoder(w).Encode(map[string]any{"overdue": []any{}, "today": []any{task}})
		case r.URL.Path == "/v1/work/tasks":
			_ = json.NewEncoder(w).Encode(map[string]any{"items": []any{task}})
		case r.URL.Path == "/v1/work/tasks/tsk_1/complete":
			task["status"] = "done"
			_ = json.NewEncoder(w).Encode(task)
		default:
			w.WriteHeader(404)
			_, _ = w.Write([]byte(`{"error":"not_found","message":"no"}`))
		}
	}))
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	r := run(t, "", false, "work", "add", "Pay", "rent", "tomorrow", "p1", "--tz", "America/New_York", "--idempotency-key", "k-1")
	if r.code != 0 || !strings.Contains(r.out, "Added tsk_1  Pay rent  due 2026-11-12") {
		t.Fatalf("add %+v", r)
	}
	if keys[0] != "k-1" {
		t.Fatalf("idempotency key %q", keys[0])
	}
	if r := run(t, "", false, "work", "add", "Pay", "rent", "tomorrow", "p1", "--tz", "America/New_York", "--quiet"); r.code != 0 || r.out != "tsk_1\n" || !strings.HasPrefix(keys[1], "cli-") || keys[1] == keys[0] {
		t.Fatalf("quiet add %+v keys %v", r, keys)
	}
	if r := run(t, "", false, "work", "add", "something else"); r.code == 0 {
		t.Fatalf("a refused add must not succeed: %+v", r)
	}
	if r := run(t, "", false, "work", "today"); r.code != 0 || !strings.Contains(r.out, "Pay rent") || !strings.Contains(r.out, "today") {
		t.Fatalf("today %+v", r)
	}
	if r := run(t, "", false, "work", "list", "--status", "todo", "--json"); r.code != 0 || !strings.Contains(r.out, `"tsk_1"`) {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "work", "done", "tsk_1"); r.code != 0 || !strings.Contains(r.out, "tsk_1 is now done") {
		t.Fatalf("done %+v", r)
	}
	if r := run(t, "", false, "work", "done", "tsk_9"); r.code != ExitNotFound {
		t.Fatalf("missing task %+v", r)
	}
	if r := run(t, "", false, "work", "add"); r.code == 0 {
		t.Fatalf("add without text %+v", r)
	}
	if !strings.Contains(strings.Join(seen, "|"), "GET /v1/work/tasks?status=todo") {
		t.Fatalf("seen %v", seen)
	}
}
