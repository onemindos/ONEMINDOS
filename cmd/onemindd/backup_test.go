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

func TestBackupRegisteredAndLoopbackOnly(t *testing.T) {
	if subcommands["backup"] == nil {
		t.Fatal("onemindd backup must be registered")
	}
	for addr, ok := range map[string]bool{
		"127.0.0.1:7481": true, "[::1]:7481": true, "localhost:7481": true,
		":7481": false, "0.0.0.0:7481": false, "192.0.2.10:7481": false, "nonsense": false,
	} {
		if err := loopbackOnly(addr); (err == nil) != ok {
			t.Errorf("loopbackOnly(%q) = %v", addr, err)
		}
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
