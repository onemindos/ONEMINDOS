// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// powerHub answers like core/onemind_core/routers/system.py: a request is filed as an action awaiting
// approval, 409 host_unavailable when the box cannot do it, and an owner-only diagnostic bundle.
func powerHub(t *testing.T, got *[]string, unavailable bool) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.Path+" "+string(body))
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/system/actions":
			if unavailable {
				jsonOut(w, 409, map[string]string{"error": "conflict", "reason": "host_unavailable", "message": "no host service"})
				return
			}
			var req map[string]any
			_ = json.Unmarshal(body, &req)
			jsonOut(w, 202, map[string]any{"id": "act-9", "type": req["type"], "state": "awaiting_approval"})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/system/diagnostics":
			jsonOut(w, 200, map[string]any{"schema": "onemind.diagnostics/v1"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestSystemRestartAndShutdownOnlyFileARequest(t *testing.T) {
	for verb, typ := range map[string]string{"restart": "system.restart", "shutdown": "system.shutdown"} {
		var got []string
		powerHub(t, &got, false)
		r := run(t, "", false, "system", verb, "--reason", "kernel update")
		if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") || !strings.Contains(r.out, "nothing happens before that") {
			t.Fatalf("%s: %+v", verb, r)
		}
		if len(got) != 1 || !strings.HasPrefix(got[0], "POST /v1/system/actions ") || !strings.Contains(got[0], `"type":"`+typ+`"`) ||
			!strings.Contains(got[0], `"reason":"kernel update"`) {
			t.Fatalf("%s asked %v: it files one request and never approves", verb, got)
		}
	}
}

func TestSystemRequestJSONAndUnavailable(t *testing.T) {
	var got []string
	powerHub(t, &got, false)
	r := run(t, "", false, "--json", "system", "restart")
	var act map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &act) != nil || act["state"] != "awaiting_approval" {
		t.Fatalf("--json: %+v", r)
	}
	powerHub(t, &got, true)
	if r := run(t, "", false, "system", "shutdown"); r.code == 0 || !strings.Contains(r.errOut, "no host service") {
		t.Fatalf("an unavailable host is an error, not success: %+v", r)
	}
}

func TestSystemResetNeedsTheTypedPhrase(t *testing.T) {
	var got []string
	powerHub(t, &got, false)
	for _, args := range [][]string{{"system", "reset"}, {"system", "reset", "--confirm", "yes"}} {
		if r := run(t, "", false, args...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", args, r)
		}
	}
	if len(got) != 0 {
		t.Fatalf("nothing reaches the hub without the phrase: %v", got)
	}
	r := run(t, "", false, "system", "reset", "--confirm", "factory reset")
	if r.code != 0 || !strings.Contains(r.out, "passkey") || !strings.Contains(got[0], `"confirm":"factory reset"`) {
		t.Fatalf("reset %+v %v", r, got)
	}
}

func TestSystemDiagnostics(t *testing.T) {
	var got []string
	powerHub(t, &got, false)
	if r := run(t, "", false, "system", "diagnostics"); r.code != 0 || !strings.Contains(r.out, "onemind.diagnostics/v1") {
		t.Fatalf("stdout: %+v", r)
	}
	f := filepath.Join(t.TempDir(), "bundle.json")
	if r := run(t, "", false, "system", "diagnostics", "-o", f); r.code != 0 {
		t.Fatalf("file: %+v", r)
	}
	if b, err := os.ReadFile(f); err != nil || !strings.Contains(string(b), "onemind.diagnostics/v1") {
		t.Fatalf("file: %v %s", err, b)
	}
	if r := run(t, "", false, "system", "diagnostics", "-o", f); r.code != ExitUsage {
		t.Fatalf("an existing file is never overwritten: %+v", r)
	}
}
