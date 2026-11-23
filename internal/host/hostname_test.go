// SPDX-License-Identifier: Apache-2.0
package host

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

// GET /v1/status names the box (#875): the one harmless read the gateway and the boot battery use to
// prove the socket reaches this service.
func TestStatusNamesTheBox(t *testing.T) {
	want, err := os.Hostname()
	if err != nil || want == "" {
		t.Skip("no hostname on this machine")
	}
	s, _ := newService(t, t.TempDir(), "boot-1")
	srv := &Server{S: s, AllowUID: -1, AllowGID: -1}
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/v1/status", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var st map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st["hostname"] != want {
		t.Fatalf("hostname = %v, want %q", st["hostname"], want)
	}
}

// A hostname that cannot be read is left out, never invented.
func TestStatusLeavesOutAnUnreadableHostname(t *testing.T) {
	s, _ := newService(t, t.TempDir(), "boot-1")
	srv := &Server{S: s, AllowUID: -1, AllowGID: -1, Hostname: func() (string, error) { return "", os.ErrNotExist }}
	raw, _ := json.Marshal(srv.Status())
	var st map[string]any
	_ = json.Unmarshal(raw, &st)
	if _, ok := st["hostname"]; ok {
		t.Fatalf("hostname present: %s", raw)
	}
}
