// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/etcdir"
	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/jobs"
	"github.com/onemindos/onemindos/internal/service"
	"github.com/onemindos/onemindos/internal/version"
)

// jobsStateDir is where the machine keeps its done-list and policy-epoch mark:
// ONEMIND_JOBS_DIR, else <ONEMIND_ETC_DIR>/jobs (/data/onemind/etc/jobs on the
// image, so a job that ran is still known after an update or a reboot).
func jobsStateDir() string {
	if d := os.Getenv("ONEMIND_JOBS_DIR"); d != "" && filepath.IsAbs(d) {
		return filepath.Clean(d)
	}
	return filepath.Join(etcdir.Dir(), "jobs")
}

// jobsService is onemindd's job intake (internal/jobs, D-029 N2). It runs on a
// joined machine that pinned its gateway's job key at join; anywhere else it stays off.
func jobsService() service.Service {
	return service.Service{Name: "jobs", Enabled: jobKeyPinned, Run: runJobs}
}

func jobKeyPinned() bool {
	st, err := fabric.LoadState("/")
	if err != nil || st.JobKid == "" || os.Getenv("ONEMIND_NATS_URL") == "" {
		return false
	}
	_, err = os.Stat(fabric.JobPubFile)
	return err == nil
}

func runJobs(ctx context.Context, log *slog.Logger) error {
	st, err := fabric.LoadState("/")
	if err != nil {
		return err
	}
	if st.JobKid == "" {
		return errors.New("jobs: this machine pinned no job key at join")
	}
	dir := jobsStateDir()
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	opts := []nats.Option{nats.Name("onemindd-jobs/" + version.Version), nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1), nats.ReconnectWait(2 * time.Second), nats.ReconnectBufSize(-1)}
	if seed := os.Getenv("ONEMIND_NATS_NKEY_SEED"); seed != "" {
		nk, err := nats.NkeyOptionFromSeed(seed)
		if err != nil {
			return err
		}
		opts = append(opts, nk)
	}
	nc, err := nats.Connect(os.Getenv("ONEMIND_NATS_URL"), opts...)
	if err != nil {
		return err
	}
	defer nc.Close()
	in := &jobs.Intake{NC: nc, NodeID: st.NodeID, Verifier: backup.NewNodeJobVerifier(st.NodeID, fabric.JobPubFile, dir),
		Handlers: jobs.Builtin(st.NodeID), Log: log}
	return in.Run(ctx)
}
