// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"os/user"
	"strconv"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
	"github.com/onemindos/onemindos/internal/storage/ops"
)

const storageUsage = `usage:
  onemindd storage serve [--socket PATH] [--mount DIR] [--group NAME] [--journal DIR]
  onemindd storage init --device PART [--tpm2 auto|yes|no] [--force] [--print-recovery-key]
`

// runStorage is `onemindd storage`: the storage operation service (its own
// privileged unit, docs/leap/core/STORAGE-ACT-os.patch.md) and the first-boot
// formatter of onemind-data. Separate from the heartbeat agent, which has no
// capabilities and a read-only view of the box.
func runStorage(args []string) int {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, storageUsage)
		return 2
	}
	switch args[0] {
	case "serve":
		return storageServe(args[1:])
	case "init":
		return storageInit(args[1:])
	}
	fmt.Fprint(os.Stderr, storageUsage)
	return 2
}

func storageServe(args []string) int {
	fs := flag.NewFlagSet("onemindd storage serve", flag.ContinueOnError)
	sock := fs.String("socket", env("ONEMIND_STORAGE_SOCKET", "/run/onemind/storage.sock"), "Unix socket for the gateway")
	mount := fs.String("mount", env("ONEMIND_STORAGE_MOUNT", "/data"), "where the data set is mounted")
	group := fs.String("group", env("ONEMIND_STORAGE_GROUP", "onemind"), "group allowed on the socket (the gateway's)")
	journal := fs.String("journal", "", "operation journal (default <mount>/onemind/storage/ops)")
	keyFile := fs.String("key-file", os.Getenv("ONEMIND_STORAGE_KEY_FILE"), "set key (default <mount>/"+storage.SetKeyPath+")")
	poll := fs.Duration("poll", 5*time.Second, "status polling while the kernel balances or replaces")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *journal == "" {
		*journal = *mount + "/onemind/storage/ops"
	}
	log := newLogger()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	col := storage.New()
	e := &ops.Engine{Facts: ops.CollectorFacts{C: col}, Run: ops.ExecRunner{}, Mount: *mount,
		Options: storage.PlanOptions{KeyFile: *keyFile}, Log: log, Context: ctx, Poll: *poll, HoldDir: storage.RunDir}
	if m, err := col.MirrorStatus(ctx, *mount); err == nil && m.State != storage.StateUnavailable {
		st, err := ops.OpenStore(*journal)
		if err != nil {
			log.Error("storage journal unavailable", "err", err)
			return 1
		}
		defer st.Close()
		e.Store = st
	} else {
		log.Warn("data set not mounted: status only, no operations (storage recovery mode)", "mount", *mount, "err", err)
	}
	if err := e.Resume(ctx); err != nil {
		log.Error("resume failed", "err", err)
	}
	gid := -1
	if g, err := user.LookupGroup(*group); err == nil {
		gid, _ = strconv.Atoi(g.Gid)
	} else {
		log.Warn("socket group not found; root only", "group", *group)
	}
	l, err := ops.Listen(*sock, gid)
	if err != nil {
		log.Error("cannot listen", "socket", *sock, "err", err)
		return 1
	}
	log.Info("storage service listening", "socket", *sock, "mount", *mount, "journal", e.Store != nil)
	srv := &ops.Server{E: e, AllowUID: -1, AllowGID: gid}
	err = srv.Serve(ctx, l)
	stop()
	e.Wait()
	if err != nil {
		log.Error("storage service stopped", "err", err)
		return 1
	}
	return 0
}

func storageInit(args []string) int {
	fs := flag.NewFlagSet("onemindd storage init", flag.ContinueOnError)
	dev := fs.String("device", "", "the onemind-data partition (e.g. /dev/disk/by-partlabel/onemind-data)")
	tpm := fs.String("tpm2", "auto", "enrol a TPM2 keyslot: auto, yes or no")
	force := fs.Bool("force", false, "format even if the partition holds something")
	printKey := fs.Bool("print-recovery-key", false, "also print the recovery key (console installers); otherwise it waits in "+storage.RecoveryKeyFile+" for the dashboard to show it once")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	o := storage.InitOptions{Part: *dev}
	switch *tpm {
	case "auto":
		o.TPM2 = storage.TPM2Present()
	case "yes":
		o.TPM2 = true
	case "no":
	default:
		fmt.Fprintln(os.Stderr, "onemindd storage init: --tpm2 must be auto, yes or no")
		return 2
	}
	if o.TPM2 {
		if _, err := os.Stat(storage.PCRPublicKey); err == nil {
			o.PCRKey = storage.PCRPublicKey
		}
	}
	set, err := ops.InitData(context.Background(), ops.ExecRunner{}, o, *force)
	if err != nil {
		fmt.Fprintln(os.Stderr, "onemindd storage init:", err)
		return 1
	}
	res := map[string]any{"set_uuid": set, "tpm2": o.TPM2, "recovery_key_file": storage.RecoveryKeyFile}
	if *printKey {
		if b, err := os.ReadFile(storage.RecoveryKeyFile); err == nil {
			res["recovery_key"] = string(b)
		}
	}
	_ = json.NewEncoder(os.Stdout).Encode(res)
	return 0
}
