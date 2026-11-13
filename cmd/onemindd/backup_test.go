// SPDX-License-Identifier: Apache-2.0

package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/backup"
)

func TestBackupHasNoDaemonSubcommand(t *testing.T) {
	if subcommands["backup-init"] == nil {
		t.Fatal("onemindd backup-init must be registered")
	}
	// One backup service, inside onemindd (backup.Service()): no `onemindd backup` daemon mode.
	if subcommands["backup"] != nil {
		t.Fatal("there must be no second backup daemon")
	}
	found := false
	for _, s := range optionalServices {
		if s.Name == "backup" {
			found = true
		}
	}
	if !found {
		t.Fatal("backup.Service() must be an optional service of onemindd")
	}
}

func TestBackupInitCreatesKeyOnceAndNeverOverwrites(t *testing.T) {
	dir := t.TempDir()
	c := backup.DefaultConfig()
	c.BoxID, c.NodeID = "box1", "node1"
	c.StateDir, c.ScratchDir = filepath.Join(dir, "state"), filepath.Join(dir, "scratch")
	c.DeviceKeyFile = filepath.Join(dir, "secrets", "device.key")
	b, _ := json.Marshal(c)
	conf := filepath.Join(dir, "agent.json")
	if err := os.WriteFile(conf, b, 0o600); err != nil {
		t.Fatal(err)
	}
	if rc := runBackupInit([]string{"-config", conf}); rc != 0 {
		t.Fatalf("first init: %d", rc)
	}
	first, err := os.ReadFile(c.DeviceKeyFile)
	if err != nil || len(first) == 0 {
		t.Fatalf("key not written: %v", err)
	}
	if rc := runBackupInit([]string{"-config", conf}); rc != 0 {
		t.Fatalf("second init: %d", rc)
	}
	second, _ := os.ReadFile(c.DeviceKeyFile)
	if string(first) != string(second) {
		t.Fatal("init must never overwrite an existing device key (it would orphan every snapshot)")
	}
}

func TestBackupHeartbeatReport(t *testing.T) {
	dir := t.TempDir()
	if backupReport(filepath.Join(dir, "missing.json")) != nil {
		t.Fatal("no agent.json: the heartbeat must omit the backup object")
	}
	c := backup.DefaultConfig()
	c.BoxID, c.NodeID = "box1", "node1"
	c.StateDir, c.ScratchDir = filepath.Join(dir, "state"), filepath.Join(dir, "scratch")
	c.DeviceKeyFile = filepath.Join(dir, "device.key")
	b, _ := json.Marshal(c)
	conf := filepath.Join(dir, "agent.json")
	if err := os.WriteFile(conf, b, 0o600); err != nil {
		t.Fatal(err)
	}
	report := backupReport(conf)
	if h := report(); h == nil || h.LastResult != "none" || h.LastRunAt != nil {
		t.Fatalf("empty state: %+v", h)
	}
	st, err := backup.OpenStore(filepath.Join(c.StateDir, "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	end := time.Date(2026, 11, 12, 9, 0, 30, 0, time.UTC)
	_ = st.Update(func(s *backup.State) {
		s.Runs = append(s.Runs, backup.Run{ID: "run_1", State: backup.StateRefused,
			StartedAt: time.Date(2026, 11, 12, 9, 0, 0, 0, time.UTC), FinishedAt: &end})
	})
	if h := report(); h.LastResult != "failed" || *h.LastRunAt != "2026-11-12T09:00:00Z" {
		t.Fatalf("refused run: %+v", h)
	}
}
