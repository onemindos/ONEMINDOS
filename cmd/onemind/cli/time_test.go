// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// timeHub answers like core/onemind_core/routers/time.py.
func timeHub(t *testing.T, got *[]string) {
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
		case r.Method == http.MethodGet && r.URL.Path == "/v1/system/time":
			jsonOut(w, 200, map[string]any{"available": true, "zone": "Europe/Berlin", "ntp_enabled": true, "ntp_synchronized": true,
				"server": "0.debian.pool.ntp.org", "stratum": 2, "last_sync_at": "2026-11-25T12:00:00Z", "at": "2026-11-25T12:30:00Z"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/system/time/zone":
			if strings.Contains(string(body), "Mars/Olympus") {
				jsonOut(w, 409, map[string]string{"error": "conflict", "reason": "unknown_zone", "message": "this box does not know that time zone"})
				return
			}
			jsonOut(w, 202, map[string]any{"id": "act-9", "type": "system.set_timezone", "state": "awaiting_approval", "params": map[string]string{"zone": "Europe/Berlin"}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestTimeStatus(t *testing.T) {
	var got []string
	timeHub(t, &got)
	r := run(t, "", false, "time", "status")
	for _, want := range []string{"Europe/Berlin", "Synchronised: yes", "0.debian.pool.ntp.org (stratum 2)", "2026-11-25T12:00:00Z"} {
		if r.code != 0 || !strings.Contains(r.out, want) {
			t.Fatalf("time status missing %q: %+v", want, r)
		}
	}
	if r := run(t, "", false, "-q", "time", "status"); r.out != "Europe/Berlin\n" {
		t.Fatalf("-q prints the zone alone: %+v", r)
	}
	if r := run(t, "", false, "--json", "time", "status"); r.code != 0 || !strings.Contains(r.out, `"ntp_synchronized": true`) {
		t.Fatalf("--json: %+v", r)
	}
}

func TestTimeSetZoneFilesARequestAndNeverApproves(t *testing.T) {
	var got []string
	timeHub(t, &got)
	r := run(t, "", false, "time", "set-zone", "Europe/Berlin", "--reason", "moved")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") {
		t.Fatalf("set-zone %+v", r)
	}
	if !strings.Contains(got[0], `"zone":"Europe/Berlin"`) || !strings.Contains(got[0], `"reason":"moved"`) {
		t.Fatalf("request %v", got)
	}
	if r := run(t, "", false, "time", "set-zone", "Mars/Olympus"); r.code != ExitConflict || !strings.Contains(r.errOut, "does not know") {
		t.Fatalf("an unknown zone: %+v", r)
	}
	for _, g := range got {
		if strings.Contains(g, "/approve") {
			t.Fatalf("the CLI approved something: %s", g)
		}
	}
}

func TestSyncWordsNeverInventsAnAnswer(t *testing.T) {
	if got := syncWords(map[string]any{}); got != "not reported" {
		t.Fatal(got)
	}
	if got := syncWords(map[string]any{"ntp_synchronized": false, "ntp_enabled": true}); !strings.Contains(got, "no time server") {
		t.Fatal(got)
	}
}
