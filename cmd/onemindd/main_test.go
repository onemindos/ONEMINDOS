package main

import (
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
)

func TestValidate(t *testing.T) {
	ok := []struct{ role, id string }{{"node", ""}, {"hub", "3f9c2a1b7d4e"}, {"node", "pi-kitchen_2"}}
	for _, c := range ok {
		if err := validate(c.role, c.id); err != nil {
			t.Errorf("validate(%q, %q) = %v", c.role, c.id, err)
		}
	}
	bad := []struct{ role, id string }{{"worker", ""}, {"node", "a.b"}, {"node", "node>"}, {"node", "x y"}, {"hub", "*"}}
	for _, c := range bad {
		if validate(c.role, c.id) == nil {
			t.Errorf("validate(%q, %q) = nil, want error", c.role, c.id)
		}
	}
}

func TestUpdateReportOnlyWithConfig(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	dir := t.TempDir()
	if updateReport(filepath.Join(dir, "missing.conf"), log) != nil {
		t.Fatal("no update.conf must mean no update object")
	}
	conf := filepath.Join(dir, "update.conf")
	_ = os.WriteFile(conf, []byte("channel = security\nurl = https://example.org/s\nstate_dir = "+dir+"\n"), 0o644)
	f := updateReport(conf, log)
	if f == nil || f() != nil {
		t.Fatal("configured but never run: hook set, object nil")
	}
	_ = os.WriteFile(filepath.Join(dir, "status.json"), []byte(`{"state":"idle","current_version":"0.1.0","last_result":""}`), 0o644)
	if u := f(); u == nil || u.Channel != "security" || u.State != "idle" {
		t.Fatalf("got %+v", u)
	}
}
