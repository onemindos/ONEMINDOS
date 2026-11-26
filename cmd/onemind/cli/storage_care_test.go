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

// careHub answers like core/onemind_core/routers/storage_care.py.
func careHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.Path+" "+string(body))
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/storage/housekeeping":
			jsonOut(w, 200, map[string]any{"available": true,
				"trim": map[string]any{"enabled": true, "timer_state": "active", "last_run_at": "2026-11-23T00:07:14Z", "last_result": "success",
					"last_trimmed_bytes": 13314398208, "next_run_at": "2026-11-30T00:00:00Z"},
				"smart": map[string]any{"daemon_state": "active", "alerts": []any{map[string]any{"id": "x", "at": "2026-11-25T01:00:00Z",
					"device": "/dev/sda", "kind": "Health", "message": "SMART health \x1b[31mfailed"}}},
				"removable": []any{
					map[string]any{"device": "/dev/sdb", "name": "sdb", "model": "Cruzer", "label": "HOLIDAY", "size_bytes": 16e9, "ejectable": true},
					map[string]any{"device": "/dev/sdc", "name": "sdc", "size_bytes": 5e11, "ejectable": false, "why_not": "the box is using this drive (/data/odd)"}}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/storage/removable/sdb/eject":
			jsonOut(w, 202, map[string]any{"id": "act-9", "type": "storage.eject", "state": "awaiting_approval", "params": map[string]string{"device": "/dev/sdb"}})
		case r.URL.Path == "/v1/storage/removable/sdc/eject":
			jsonOut(w, 409, map[string]string{"error": "conflict", "reason": "in_use", "message": "the box is using this drive (/data/odd)"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no removable drive with that name is plugged in"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestStorageTrimStatusPrintsTrimWarningsAndDrives(t *testing.T) {
	var got []string
	careHub(t, &got)
	r := run(t, "", false, "storage", "trim-status")
	if r.code != 0 {
		t.Fatalf("%+v", r)
	}
	for _, want := range []string{"last ran 2026-11-23 00:07 UTC, freed 12.4 GiB", "Next TRIM:  2026-11-30 00:00 UTC", "smartd:     active, 1 warning(s)",
		"/dev/sda  Health: SMART health failed", "sdb", "can be removed", "in use: the box is using this drive (/data/odd)"} {
		if !strings.Contains(r.out, want) {
			t.Errorf("missing %q in\n%s", want, r.out)
		}
	}
	if strings.Contains(r.out, "\x1b") {
		t.Fatalf("a drive's own text must not carry terminal control characters: %q", r.out)
	}
	r = run(t, "", false, "storage", "trim-status", "--json")
	var v map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || v["available"] != true {
		t.Fatalf("--json %+v", r)
	}
}

func TestStorageEjectFilesAnApprovalAndNeverApproves(t *testing.T) {
	var got []string
	careHub(t, &got)
	r := run(t, "", false, "storage", "eject", "/dev/sdb", "--reason", "backup done")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") || !strings.Contains(r.out, "owner approves") {
		t.Fatalf("%+v", r)
	}
	if len(got) != 1 || !strings.HasPrefix(got[0], "POST /v1/storage/removable/sdb/eject ") || !strings.Contains(got[0], `"reason":"backup done"`) {
		t.Fatalf("asked %v: the CLI files one request and approves nothing", got)
	}
	if r := run(t, "", false, "storage", "eject", "sdc"); r.code != ExitConflict {
		t.Fatalf("a drive in use: %+v", r)
	}
	if r := run(t, "", false, "storage", "eject", "sdz"); r.code != ExitNotFound {
		t.Fatalf("a drive that is not there: %+v", r)
	}
	if r := run(t, "", false, "storage", "eject"); r.code != ExitUsage {
		t.Fatalf("no drive named: %+v", r)
	}
}
