// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
)

const configSettings = "schema: onemind.io/config-as-code/settings/v1\nbox:\n  box_name: hub\n"
const configApps = "schema: onemind.io/config-as-code/apps/v1\napps: []\n"

func TestConfigExport(t *testing.T) {
	isolate(t)
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
		jsonOut(w, http.StatusOK, map[string]string{"yaml": configSettings})
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	dir := filepath.Join(t.TempDir(), "private-config")
	path := filepath.Join(dir, "settings.yaml")
	if err := os.Mkdir(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	writeTestConfig(t, dir, "apps.yaml", configApps)
	for range 2 {
		if r := run(t, "", false, "config", "export", "--dir", dir); r.code != 0 {
			t.Fatalf("config export failed: %+v", r)
		}
		data, err := os.ReadFile(path)
		if err != nil || string(data) != configSettings {
			t.Fatalf("settings.yaml = %q, error %v", data, err)
		}
	}

	t.Setenv("ONEMIND_TOKEN", "invalid")
	if r := run(t, "", false, "config", "export", "--dir", dir); r.code == 0 {
		t.Fatal("expected the gateway to refuse an unauthenticated export")
	}
	if data, err := os.ReadFile(path); err != nil || string(data) != configSettings {
		t.Fatalf("failed export replaced settings.yaml: %q, error %v", data, err)
	}
	if data, err := os.ReadFile(filepath.Join(dir, "apps.yaml")); err != nil || string(data) != configApps {
		t.Fatalf("legacy export touched an unsupported file: %q, error %v", data, err)
	}
}

func TestConfigExportDirectory(t *testing.T) {
	isolate(t)
	const users = "schema: onemind.io/config-as-code/users/v1\nusers: []\n"
	const schedules = "schema: onemind.io/config-as-code/schedules/v1\nschedules: []\n"
	var response atomic.Value
	response.Store(map[string]string{
		"settings.yaml": configSettings, "apps.yaml": configApps, "users.yaml": users, "schedules.yaml": schedules,
	})
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/v1/config/export" {
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		jsonOut(w, http.StatusOK, map[string]any{"yaml": configSettings, "files": response.Load()})
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	dir := t.TempDir()
	writeTestConfig(t, dir, "README.md", "private repository")
	writeTestConfig(t, dir, "settings.yaml", "old YAML")
	settingsPath := filepath.Join(dir, "settings.yaml")
	oldFile, err := os.Open(settingsPath)
	if err != nil {
		t.Fatal(err)
	}
	defer oldFile.Close()
	if r := run(t, "", false, "config", "export", "--dir", dir, "--json"); r.code != 0 {
		t.Fatalf("config export failed: %+v", r)
	} else {
		var result struct {
			Path  string
			Paths []string
		}
		if err := json.Unmarshal([]byte(r.out), &result); err != nil || result.Path != settingsPath || len(result.Paths) != 4 {
			t.Fatalf("export paths = %+v, error %v, output %s", result, err, r.out)
		}
	}
	previous := make([]byte, len("old YAML"))
	if _, err := oldFile.Read(previous); err != nil || string(previous) != "old YAML" {
		t.Fatalf("old file changed in place: %q, error %v", previous, err)
	}
	for name, want := range response.Load().(map[string]string) {
		path := filepath.Join(dir, name)
		if got, err := os.ReadFile(path); err != nil || string(got) != want {
			t.Fatalf("%s = %q, error %v", name, got, err)
		}
		if info, err := os.Stat(path); err != nil || info.Mode().Perm() != 0o600 {
			t.Fatalf("%s permissions: %v, error %v", name, info, err)
		}
	}

	changed := strings.Replace(configSettings, "hub", "other-box", 1)
	for _, files := range []map[string]string{
		{"settings.yaml": changed, "apps.yaml": "apps: []\n"},
		{"settings.yaml": changed, "../unexpected.yaml": "unexpected"},
		{"apps.yaml": configApps},
	} {
		response.Store(files)
		if r := run(t, "", false, "config", "export", "--dir", dir); r.code == 0 {
			t.Fatalf("invalid export accepted: %+v", r)
		}
		if got, err := os.ReadFile(settingsPath); err != nil || string(got) != configSettings {
			t.Fatalf("invalid export changed settings.yaml: %q, error %v", got, err)
		}
		if _, err := os.Stat(filepath.Join(dir, "schedules.yaml")); err != nil {
			t.Fatalf("invalid export removed schedules.yaml: %v", err)
		}
	}

	response.Store(map[string]string{"settings.yaml": changed, "apps.yaml": configApps})
	if r := run(t, "", false, "config", "export", "--dir", dir); r.code != 0 {
		t.Fatalf("config export failed: %+v", r)
	}
	for _, name := range []string{"users.yaml", "schedules.yaml"} {
		if _, err := os.Lstat(filepath.Join(dir, name)); !os.IsNotExist(err) {
			t.Fatalf("stale file %s remained: %v", name, err)
		}
	}
	if data, err := os.ReadFile(filepath.Join(dir, "README.md")); err != nil || string(data) != "private repository" {
		t.Fatalf("export touched unmanaged README.md: %q, error %v", data, err)
	}
}

func TestConfigDiffAndApply(t *testing.T) {
	isolate(t)
	dir := t.TempDir()
	writeTestConfig(t, dir, "settings.yaml", configSettings)
	writeTestConfig(t, dir, "apps.yaml", configApps)
	want := map[string]string{"settings.yaml": configSettings, "apps.yaml": configApps}
	var diffs, applies atomic.Int32
	var unchanged, blocked, decided atomic.Bool
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Files    map[string]string
			Revision string
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || r.Method != http.MethodPost || !reflect.DeepEqual(req.Files, want) {
			t.Errorf("unexpected config call %s %s, body %+v, error %v", r.Method, r.URL.Path, req, err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		switch r.URL.Path {
		case "/v1/config/diff":
			diffs.Add(1)
			changes := []map[string]string{}
			blockers := []string{}
			if !unchanged.Load() {
				changes = append(changes, map[string]string{
					"file": "settings.yaml", "before": strings.Replace(configSettings, "hub", "old-hub", 1), "after": configSettings,
				})
			}
			if blocked.Load() {
				blockers = append(blockers, "Manage users in People.")
			}
			jsonOut(w, http.StatusOK, map[string]any{"revision": "current-revision", "changes": changes, "blockers": blockers})
		case "/v1/config/apply":
			applies.Add(1)
			wantDiffs, state := int32(2), "awaiting_approval"
			if decided.Load() {
				wantDiffs, state = 5, "succeeded"
			}
			if diffs.Load() != wantDiffs || req.Revision != "current-revision" || r.Header.Get("Idempotency-Key") == "" {
				t.Errorf("apply request did not follow and bind the dry run: %+v, diff calls %d", req, diffs.Load())
			}
			jsonOut(w, http.StatusAccepted, map[string]string{
				"id": "act-config", "type": "config.apply", "state": state,
			})
		default:
			t.Errorf("unexpected request %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	if result := run(t, "", false, "config", "diff", "--dir", dir); result.code != 0 ||
		!strings.Contains(result.out, "old-hub") || !strings.Contains(result.out, "box_name: hub") || applies.Load() != 0 {
		t.Fatalf("dry run didn't show the change or attempted apply: %+v", result)
	}
	if result := run(t, "", false, "config", "apply", "--dir", dir, "--json"); result.code != 0 ||
		!strings.Contains(result.out, "awaiting_approval") || !strings.Contains(result.out, "act-config") || applies.Load() != 1 {
		t.Fatalf("config apply didn't queue a request: %+v", result)
	}
	unchanged.Store(true)
	if result := run(t, "", false, "config", "apply", "--dir", dir); result.code != 0 ||
		!strings.Contains(result.out, "No config changes.") || diffs.Load() != 3 || applies.Load() != 1 {
		t.Fatalf("config apply didn't stop after an empty diff: %+v", result)
	}
	unchanged.Store(false)
	blocked.Store(true)
	if result := run(t, "", false, "config", "apply", "--dir", dir); result.code != ExitRefused ||
		!strings.Contains(result.out, "Manage users in People.") || diffs.Load() != 4 || applies.Load() != 1 {
		t.Fatalf("config apply didn't show blockers or attempted to queue a request: %+v", result)
	}
	blocked.Store(false)
	decided.Store(true)
	if result := run(t, "", false, "config", "apply", "--dir", dir); result.code != 0 ||
		!strings.Contains(result.out, "Config apply (act-config) is succeeded.") || applies.Load() != 2 {
		t.Fatalf("config apply didn't report an already-decided action: %+v", result)
	}
}

func TestConfigApprovalShowsPatch(t *testing.T) {
	isolate(t)
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/actions/act-config":
			jsonOut(w, http.StatusOK, map[string]any{
				"id": "act-config", "type": "config.apply", "state": "awaiting_approval", "plan_sha256": "plan-hash",
				"params": map[string]any{"patch": map[string]any{"box": map[string]any{
					"before": map[string]string{"box_name": "old-hub"}, "after": map[string]string{"box_name": "new-hub"},
				}}},
			})
		case "GET /v1/audit/events":
			jsonOut(w, http.StatusOK, []any{})
		case "POST /v1/actions/act-config/approve":
			var body map[string]string
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body["plan_sha256"] != "plan-hash" {
				t.Errorf("approval was not bound to the reviewed plan: %+v, error %v", body, err)
			}
			jsonOut(w, http.StatusOK, map[string]string{"state": "succeeded"})
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	result := run(t, "", false, "actions", "approve", "act-config", "--yes")
	if result.code != 0 || !strings.Contains(result.out, "Configuration changes\n") ||
		!strings.Contains(result.out, "old-hub") || !strings.Contains(result.out, "new-hub") {
		t.Fatalf("approval didn't show the before and after patch: %+v", result)
	}
}

func TestConfigDiffRejectsInvalidLocalFiles(t *testing.T) {
	isolate(t)
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("invalid local file sent to the gateway: %s %s", r.Method, r.URL.Path)
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	for _, tt := range []struct {
		name, yaml string
	}{
		{"missing", "box: {}\n"},
		{"wrong file", configApps},
		{"future", strings.Replace(configSettings, "/v1", "/v2", 1)},
		{"duplicate", configSettings + "schema: onemind.io/config-as-code/settings/v1\n"},
		{"extra document", configSettings + "---\n" + configSettings},
	} {
		t.Run(tt.name, func(t *testing.T) {
			dir := t.TempDir()
			writeTestConfig(t, dir, "settings.yaml", tt.yaml)
			for _, verb := range []string{"diff", "apply"} {
				if r := run(t, "", false, "config", verb, "--dir", dir); r.code == 0 || !strings.Contains(r.errOut, "settings.yaml") {
					t.Fatalf("accepted invalid config for %s: %+v", verb, r)
				}
			}
		})
	}
	dir := t.TempDir()
	if r := run(t, "", false, "config", "diff", "--dir", dir); r.code == 0 || !strings.Contains(r.errOut, "no OneMind configuration files") {
		t.Fatalf("diff accepted an empty directory: %+v", r)
	}
	const real = "private.yaml"
	writeTestConfig(t, dir, real, configSettings)
	if err := os.Symlink(real, filepath.Join(dir, "settings.yaml")); err != nil {
		t.Fatal(err)
	}
	if r := run(t, "", false, "config", "diff", "--dir", dir); r.code == 0 || !strings.Contains(r.errOut, "must be a regular file") {
		t.Fatalf("diff read a symbolic link: %+v", r)
	}
}

func writeTestConfig(t *testing.T, dir, name, contents string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, name), []byte(contents), 0o600); err != nil {
		t.Fatal(err)
	}
}
