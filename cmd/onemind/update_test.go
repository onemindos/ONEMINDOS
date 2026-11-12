// SPDX-License-Identifier: Apache-2.0

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/update"
	"github.com/onemindos/onemindos/internal/update/tuftest"
)

type fakeInstall struct{ got []string }

func (f *fakeInstall) Install(_ context.Context, b string) error {
	f.got = append(f.got, filepath.Base(b))
	return nil
}

type fakeReboot struct{ n int }

func (f *fakeReboot) Reboot(context.Context) error { f.n++; return nil }

func TestUpdateCheckApplyStatus(t *testing.T) {
	dir := t.TempDir()
	repo, err := tuftest.New(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	repo.AddTarget(tuftest.Meta{Board: "vm", Version: "0.1.1", Compatible: "onemind-vm", MinFromVersion: "0.1.0", Security: true}, []byte("bundle"))
	if err := repo.Publish(filepath.Join(dir, "repo"), 0); err != nil {
		t.Fatal(err)
	}
	root, _ := repo.RootJSON()
	srv := httptest.NewServer(http.FileServer(http.Dir(filepath.Join(dir, "repo"))))
	defer srv.Close()
	files := map[string]string{
		"tuf/security/root.json": string(root),
		"os-release":             "ONEMIND_VERSION=0.1.0\nONEMIND_BOARD=vm\n",
		"system.conf":            "compatible=onemind-vm\n",
		"gate/.keep":             "",
	}
	for p, s := range files {
		p = filepath.Join(dir, p)
		_ = os.MkdirAll(filepath.Dir(p), 0o755)
		if err := os.WriteFile(p, []byte(s), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	conf := filepath.Join(dir, "update.conf")
	text := strings.Join([]string{"channel = security", "url = " + srv.URL, "window = 02:00-05:00",
		"tuf_root_dir = " + filepath.Join(dir, "tuf"), "state_dir = " + filepath.Join(dir, "state"),
		"download_dir = " + filepath.Join(dir, "rauc"), "gate_dir = " + filepath.Join(dir, "gate"),
		"os_release = " + filepath.Join(dir, "os-release"), "rauc_conf = " + filepath.Join(dir, "system.conf"), ""}, "\n")
	if err := os.WriteFile(conf, []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}

	inst, rb := &fakeInstall{}, &fakeReboot{}
	newEngine = func(c *update.Config, log *slog.Logger) *update.Engine {
		e := update.New(c, log)
		e.Installer, e.Rebooter, e.HTTP = inst, rb, srv.Client()
		return e
	}

	var out, errb bytes.Buffer
	if code := run([]string{"update", "check", "--config", conf}, &out, &errb); code != 0 {
		t.Fatalf("check exit %d: %s %s", code, out.String(), errb.String())
	}
	if !strings.Contains(out.String(), "available    0.1.1") || len(inst.got) != 0 {
		t.Fatalf("check output:\n%s", out.String())
	}

	out.Reset()
	if code := run([]string{"update", "apply", "--config", conf, "--no-reboot"}, &out, &errb); code != 0 {
		t.Fatalf("apply exit %d: %s %s", code, out.String(), errb.String())
	}
	if len(inst.got) != 1 || rb.n != 0 || !strings.Contains(out.String(), "pending_reboot") {
		t.Fatalf("apply: installs %v reboots %d\n%s", inst.got, rb.n, out.String())
	}
	if !strings.Contains(errb.String(), "no pre-update snapshot: restic is not configured") {
		t.Fatalf("missing restic warning in log:\n%s", errb.String())
	}

	out.Reset()
	if code := run([]string{"update", "status", "--config", conf, "--json"}, &out, &errb); code != 0 {
		t.Fatalf("status exit %d", code)
	}
	var st map[string]any
	if err := json.Unmarshal(out.Bytes(), &st); err != nil || st["state"] != "pending_reboot" || st["snapshot"] != "none" {
		t.Fatalf("status json %v: %s", err, out.String())
	}
}
