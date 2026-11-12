// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/version"
)

// runBackup is `onemindd backup`: the backup agent (internal/backup) as its
// own process and systemd unit (deploy/systemd/onemind-backup.service).
//
// Why not inside the heartbeat agent: onemindd's heartbeat runs as root with
// every capability removed and a read-only filesystem. A backup must read
// every app's files and a restore must write them back with their owners,
// which needs CAP_DAC_READ_SEARCH, CAP_DAC_OVERRIDE, CAP_CHOWN and CAP_FOWNER.
// Keeping those out of the always-on heartbeat process is the same split as
// `onemindd update` (docs/leap/core/PLUMBING.md §7, "separate mode").
//
//	onemindd backup [-config FILE]        run the agent: schedule + loopback API
//	onemindd backup init [-config FILE]   create the device key if it is missing
func runBackup(args []string) int {
	sub := ""
	if len(args) > 0 && args[0] == "init" {
		sub, args = "init", args[1:]
	}
	fs := flag.NewFlagSet("onemindd backup", flag.ContinueOnError)
	conf := fs.String("config", env("ONEMIND_BACKUP_CONF", backup.DefaultConfigPath), "agent.json path")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	log := newLogger()
	cfg, err := backup.LoadConfig(*conf)
	if err != nil {
		log.Error("onemindd backup: cannot start", "config", *conf, "err", err)
		return 2
	}
	if sub == "init" {
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
	if err := loopbackOnly(cfg.Listen); err != nil {
		log.Error("onemindd backup: cannot start", "err", err)
		return 2
	}
	a, err := backup.New(cfg)
	if err != nil {
		log.Error("onemindd backup: cannot start", "err", err)
		return 2
	}
	a.Log = log.With("service", "backup")
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ln, err := net.Listen("tcp", cfg.Listen)
	if err != nil {
		log.Error("onemindd backup: listen", "err", err)
		return 1
	}
	srv := &http.Server{Handler: a.Handler(ctx), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		if err := srv.Serve(ln); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("backup API stopped", "err", err)
			stop()
		}
	}()
	log.Info("backup agent starting", "version", version.Version, "listen", cfg.Listen, "box", cfg.BoxID,
		"targets", len(cfg.Targets), "apps", len(cfg.Units.Apps), "gateway_hourly", cfg.Schedule.GatewayHourly,
		"signed_jobs", cfg.JobPubKeyFile != "")
	a.Loop(ctx)
	shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdown)
	log.Info("backup agent stopped")
	return 0
}

// loopbackOnly refuses a listen address that is not on the loopback
// interface (H-24): the API is for the gateway and the updater on this box.
func loopbackOnly(addr string) error {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		return fmt.Errorf("listen %q: %w", addr, err)
	}
	if ip := net.ParseIP(host); host != "localhost" && (ip == nil || !ip.IsLoopback()) {
		return fmt.Errorf("listen %q: the backup API binds the loopback interface only", addr)
	}
	return nil
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
