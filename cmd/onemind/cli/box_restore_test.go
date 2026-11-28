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

// Built at run time: a long literal like a real key trips the secret scanner.
var testRecoveryKey = strings.Repeat("ab", 20)

const testDest = "dst_0123456789abcdef"

type restoreHub struct {
	mu    sync.Mutex
	paths []string
	body  []map[string]any
	idem  []string
	raw   []string
}

func startRestoreHub(t *testing.T) *restoreHub {
	t.Helper()
	isolate(t)
	h := &restoreHub{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.mu.Lock()
		defer h.mu.Unlock()
		b, _ := io.ReadAll(r.Body)
		var in map[string]any
		_ = json.Unmarshal(b, &in)
		h.paths = append(h.paths, r.Method+" "+r.URL.Path)
		h.body = append(h.body, in)
		h.idem = append(h.idem, r.Header.Get("Idempotency-Key"))
		h.raw = append(h.raw, r.URL.RawQuery)
		switch r.URL.Path {
		case "/v1/onboarding/restore/candidates":
			jsonOut(w, 200, map[string]any{"destination_id": testDest, "points": []any{
				map[string]any{"run_id": "run1", "taken_at": "2026-11-20T03:00:00Z", "apps": []any{"notes", "kuma"}, "system": true, "snapshot_ids": []any{}}}})
		case "/v1/onboarding/restore/apps":
			jsonOut(w, 202, map[string]any{"id": "act-5", "type": "backup.restore", "state": "awaiting_approval", "restore": nil})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return h
}

func TestOnboardingRestoreCandidates(t *testing.T) {
	h := startRestoreHub(t)
	r := run(t, testRecoveryKey+"\n", false, "box-restore", "candidates", "--destination", testDest, "--box", "box-old", "--recovery-key-stdin")
	if r.code != 0 || !strings.Contains(r.out, "run1") || !strings.Contains(r.out, "notes, kuma") {
		t.Fatalf("candidates %+v", r)
	}
	if h.body[0]["recovery_key"] != testRecoveryKey || h.body[0]["box_id"] != "box-old" || h.raw[0] != "" {
		t.Fatalf("the key goes in the body only, never the URL: %+v %q", h.body[0], h.raw[0])
	}
	if strings.Contains(r.out+r.errOut, testRecoveryKey) {
		t.Fatalf("the key must never be printed")
	}
}

func TestOnboardingRestoreAppOnlyFilesARequest(t *testing.T) {
	h := startRestoreHub(t)
	r := run(t, testRecoveryKey+"\n", false, "box-restore", "app", "--destination", testDest, "--box", "box-old", "--run", "run1", "--app", "notes", "--recovery-key-stdin")
	if r.code != 0 || !strings.Contains(r.out, "act-5") || !strings.Contains(r.out, "Waiting for an owner") {
		t.Fatalf("app %+v", r)
	}
	if h.body[0]["approve"] != false || h.body[0]["app_id"] != "notes" || h.body[0]["run_id"] != "run1" {
		t.Fatalf("body %+v", h.body[0])
	}
	if !strings.Contains(r.errOut, "restart before approval") {
		t.Fatalf("warn that a restart drops the in-memory key: %q", r.errOut)
	}
	if !strings.HasPrefix(h.idem[0], "cli-restore-") {
		t.Fatalf("a stable Idempotency-Key: %q", h.idem[0])
	}
	if strings.Contains(r.out+r.errOut, testRecoveryKey) {
		t.Fatalf("the key must never be printed")
	}
}

func TestOnboardingRestoreRefusesBeforeAnyCall(t *testing.T) {
	h := startRestoreHub(t)
	for _, tc := range []struct {
		stdin string
		args  []string
	}{
		{testRecoveryKey, []string{"--destination", "bad", "--box", "b", "--recovery-key-stdin"}},
		{testRecoveryKey, []string{"--destination", testDest, "--recovery-key-stdin"}},
		{testRecoveryKey, []string{"--destination", testDest, "--box", "b"}},
		{"short\n", []string{"--destination", testDest, "--box", "b", "--recovery-key-stdin"}},
	} {
		args := append([]string{"box-restore", "candidates"}, tc.args...)
		if r := run(t, tc.stdin, false, args...); r.code == 0 {
			t.Fatalf("%v must be refused: %+v", tc.args, r)
		}
	}
	if r := run(t, testRecoveryKey+"\n", false, "box-restore", "app", "--destination", testDest, "--box", "b", "--recovery-key-stdin"); r.code == 0 {
		t.Fatalf("app without --run and --app must be refused: %+v", r)
	}
	if len(h.paths) != 0 {
		t.Fatalf("nothing may reach the gateway: %v", h.paths)
	}
}
