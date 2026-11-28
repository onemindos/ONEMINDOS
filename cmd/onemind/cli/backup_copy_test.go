// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSovereignCopyCLI(t *testing.T) {
	isolate(t)
	key := strings.Repeat("AAAA-", 12) + "AAAA"
	fingerprint := strings.Repeat("a", 64)
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body["destination_id"] != "dst-test" || body["recovery_key"] != key {
			t.Error("request did not carry the kit and destination in its body")
		}
		switch r.URL.Path {
		case "/v1/backups/copies":
			if _, ok := body["approve"]; ok || r.Header.Get("Idempotency-Key") == "" {
				t.Error("copy should file an idempotent request only")
			}
			jsonOut(w, 202, map[string]any{"id": "act_copy", "state": "awaiting_approval"})
		case "/v1/onboarding/restore/copy":
			if body["box_id"] != "old-box" || body["root_fingerprint"] != fingerprint {
				t.Error("discovery did not bind the kit to the source box and root")
			}
			jsonOut(w, 200, map[string]any{"candidate": map[string]any{"copy_id": "verified-copy"}})
		default:
			t.Errorf("wrong request path %s", r.URL.Path)
			jsonOut(w, 404, nil)
		}
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	invalid := run(t, key+"\n", false, "--token-stdin", "backup", "copy", "start", "dst-test")
	if invalid.code == 0 || strings.Contains(invalid.out+invalid.errOut, key) {
		t.Fatal("copy start must reserve stdin for the recovery key")
	}
	start := run(t, key+"\n", false, "backup", "copy", "start", "dst-test", "--json")
	if start.code != 0 || !strings.Contains(start.out, "awaiting_approval") || strings.Contains(start.out+start.errOut, key) {
		t.Fatal("copy start did not report a pending approval without disclosure")
	}
	discover := run(t, key+"\n", false, "backup", "copy", "discover", "dst-test", "old-box", fingerprint)
	if discover.code != 0 || !strings.Contains(discover.out, "verified-copy") || strings.Contains(discover.out+discover.errOut, key) {
		t.Fatal("copy discover did not report the verified copy without disclosure")
	}
}
