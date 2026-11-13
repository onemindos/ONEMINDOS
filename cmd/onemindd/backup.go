// SPDX-License-Identifier: Apache-2.0

package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/heartbeat"
)

// runBackupInit is `onemindd backup-init`: a one-shot that creates the device key if it is missing.
// It is not a daemon. There is exactly one backup service: backup.Service() (registry.go,
// optionalServices), which runs inside onemindd's own process and mounts the loopback API on
// :7480 under /api/v1/backup/ (contract 12.12). A second agent process would mean two writers
// to the same state file and two places that can start a restore.
//
//	onemindd backup-init [-config FILE]   create the device key if it is missing
func runBackupInit(args []string) int {
	fs := flag.NewFlagSet("onemindd backup-init", flag.ContinueOnError)
	conf := fs.String("config", env("ONEMIND_BACKUP_CONF", backup.DefaultConfigPath), "agent.json path")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	log := newLogger()
	cfg, err := backup.LoadConfig(*conf)
	if err != nil {
		log.Error("onemindd backup-init: cannot start", "config", *conf, "err", err)
		return 2
	}
	if err := os.MkdirAll(filepath.Dir(cfg.DeviceKeyFile), 0o700); err != nil {
		log.Error("device key", "err", err)
		return 1
	}
	switch err := backup.GenerateKey(cfg.DeviceKeyFile); {
	case errors.Is(err, os.ErrExist):
		fmt.Println("device key exists:", cfg.DeviceKeyFile)
	case err != nil:
		log.Error("device key", "err", err)
		return 1
	default:
		fmt.Println("device key created:", cfg.DeviceKeyFile)
	}
	return 0
}

// backupReport returns the heartbeat's "backup" source (contract §12.10),
// read from the backup agent's state file, or nil when the box has no
// backup agent configured.
func backupReport(path string) func() *heartbeat.Backup {
	cfg, err := backup.LoadConfig(path)
	if err != nil {
		return nil
	}
	state := filepath.Join(cfg.StateDir, "state.json")
	return func() *heartbeat.Backup {
		st, err := backup.OpenStore(state)
		if err != nil {
			return nil
		}
		h := backup.HeartbeatFromState(st.View())
		return &heartbeat.Backup{Running: h.Running, LastRunAt: h.LastRunAt, LastResult: h.LastResult}
	}
}
