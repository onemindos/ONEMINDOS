// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestConfigExport(t *testing.T) {
	isolate(t)
	const settings = "schema: onemind.io/config-as-code/settings/v1\nbox:\n  box_name: hub\n"
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/v1/config/export" {
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, http.StatusUnauthorized, map[string]string{"error": "unauthenticated", "message": "owner required"})
			return
		}
		jsonOut(w, http.StatusOK, map[string]string{"yaml": settings})
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	dir := filepath.Join(t.TempDir(), "private-config")
	path := filepath.Join(dir, "settings.yaml")
	for range 2 {
		if r := run(t, "", false, "config", "export", "--dir", dir); r.code != 0 {
			t.Fatalf("config export failed: %+v", r)
		}
		data, err := os.ReadFile(path)
		if err != nil || string(data) != settings {
			t.Fatalf("settings.yaml = %q, error %v", data, err)
		}
	}

	t.Setenv("ONEMIND_TOKEN", "invalid")
	if r := run(t, "", false, "config", "export", "--dir", dir); r.code == 0 {
		t.Fatal("expected the gateway to refuse an unauthenticated export")
	}
	if data, err := os.ReadFile(path); err != nil || string(data) != settings {
		t.Fatalf("failed export replaced settings.yaml: %q, error %v", data, err)
	}
}
