// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestServiceDisabledWithoutConfig(t *testing.T) {
	t.Setenv("ONEMIND_BACKUP_CONF", filepath.Join(t.TempDir(), "missing.json"))
	s := Service()
	if s.Enabled() {
		t.Fatal("a box without agent.json must not run the backup service")
	}
	if s.Mount != "/api/v1/backup/" || s.Handler == nil || s.Run == nil {
		t.Fatalf("service not fully described: %+v", s)
	}
}

func TestServiceBrokenConfigIsUnavailableNotFatal(t *testing.T) {
	p := filepath.Join(t.TempDir(), "agent.json")
	if err := os.WriteFile(p, []byte("{not json"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("ONEMIND_BACKUP_CONF", p)
	s := Service()
	if !s.Enabled() {
		t.Fatal("a present config enables the service")
	}
	req := httptest.NewRequest("GET", "/api/v1/backup/status", nil)
	req.RemoteAddr = "127.0.0.1:1"
	w := httptest.NewRecorder()
	s.Handler(context.Background()).ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable || !strings.Contains(w.Body.String(), "unavailable") {
		t.Fatalf("broken config: %d %s", w.Code, w.Body)
	}
	if err := s.Run(context.Background(), nil); err == nil {
		t.Fatal("Run must report the broken config so it is logged")
	}
}

func TestAPIUnknownTargetIsRejectedBeforeAccepted(t *testing.T) {
	f := newFixture(t)
	h := f.agent.Handler(context.Background())
	req := httptest.NewRequest("POST", "/api/v1/backup/run", strings.NewReader(`{"reason":"manual","target_id":"nope"}`))
	req.RemoteAddr = "127.0.0.1:5000"
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest || !strings.Contains(w.Body.String(), "unknown target") {
		t.Fatalf("unknown target: %d %s", w.Code, w.Body)
	}
}
