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

func startShareHub(t *testing.T) *[]string {
	t.Helper()
	isolate(t)
	var calls []string
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		b, _ := io.ReadAll(r.Body)
		calls = append(calls, r.Method+" "+r.URL.RequestURI()+" "+string(b)+" idem="+r.Header.Get("Idempotency-Key"))
		switch {
		case r.URL.Path == "/v1/share/types":
			jsonOut(w, 200, map[string]any{"types": []any{map[string]any{"name": "file", "title": "File", "data_class": "private", "ref": "a Files location"}}})
		case r.URL.Path == "/v1/share/targets":
			jsonOut(w, 200, map[string]any{"type": r.URL.Query().Get("type"), "targets": []any{map[string]any{"app_id": "photos", "name": "Photos", "verbs": []any{"open", "add"}}}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/share":
			var in map[string]any
			_ = json.Unmarshal(b, &in)
			if in["to"] == "nope" {
				jsonOut(w, 409, map[string]string{"error": "conflict", "message": "Nope does not accept a file", "reason": "type_not_accepted"})
				return
			}
			jsonOut(w, 201, map[string]any{"id": "evt1", "to": in["to"], "verb": in["verb"], "link": "onemind://photos/file/x"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &calls
}

func TestShareTypesAndTargets(t *testing.T) {
	calls := startShareHub(t)
	if r := run(t, "", false, "share", "types"); r.code != 0 || !strings.Contains(r.out, "file") || !strings.Contains(r.out, "private") {
		t.Fatalf("types %+v", r)
	}
	r := run(t, "", false, "share", "targets", "file")
	if r.code != 0 || !strings.Contains(r.out, "photos") || !strings.Contains(r.out, "open, add") {
		t.Fatalf("targets %+v", r)
	}
	if !strings.HasPrefix((*calls)[1], "GET /v1/share/targets?type=file") {
		t.Fatalf("query %q", (*calls)[1])
	}
}

func TestShareSendHandsOverAReference(t *testing.T) {
	calls := startShareHub(t)
	r := run(t, "", false, "share", "send", "--to", "photos", "--type", "file", "--ref", "home:alex:/notes.txt", "--verb", "add")
	if r.code != 0 || !strings.Contains(r.out, "photos") || !strings.Contains(r.out, "onemind://photos/file/x") {
		t.Fatalf("send %+v", r)
	}
	got := (*calls)[0]
	if !strings.Contains(got, `"object":{"ref":"home:alex:/notes.txt","type":"file"}`) || !strings.Contains(got, `"verb":"add"`) || !strings.Contains(got, "idem=cli-share-") {
		t.Fatalf("body %q", got)
	}
}

func TestShareSendRefusalsAndUsage(t *testing.T) {
	calls := startShareHub(t)
	if r := run(t, "", false, "share", "send", "--to", "nope", "--type", "file", "--ref", "x"); r.code == 0 || !strings.Contains(r.errOut, "does not accept") {
		t.Fatalf("the gateway's refusal must reach the person: %+v", r)
	}
	n := len(*calls)
	for _, args := range [][]string{
		{"share", "send", "--to", "photos", "--type", "file"},
		{"share", "send", "--to", "photos", "--type", "file", "--ref", "x", "--verb", "delete"},
	} {
		if r := run(t, "", false, args...); r.code == 0 {
			t.Fatalf("%v must be refused: %+v", args, r)
		}
	}
	if len(*calls) != n {
		t.Fatalf("a usage error must not reach the gateway: %q", *calls)
	}
}
