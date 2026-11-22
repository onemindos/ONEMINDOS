// SPDX-License-Identifier: Apache-2.0
package main

import (
	"context"
	"flag"
	"github.com/onemindos/onemindos/internal/backup/localsnapshot"
	"os"
	"time"
)

// Only an administrator-provisioned timer calls this; no gateway or AI route.
func runSnapshots(args []string) int {
	fs := flag.NewFlagSet("onemindd snapshots-tick", flag.ContinueOnError)
	path := fs.String("config", localsnapshot.DefaultConfig, "private snapshot configuration")
	if err := fs.Parse(args); err != nil || fs.NArg() != 0 {
		return 2
	}
	if os.Geteuid() != 0 {
		newLogger().Error("snapshot timer requires root")
		return 1
	}
	c, err := localsnapshot.Load(*path)
	if err == nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()
		err = (localsnapshot.Manager{Config: c}).Tick(ctx, time.Now())
	}
	if err != nil {
		newLogger().Error("local snapshot schedule", "err", err)
		return 1
	}
	return 0
}
