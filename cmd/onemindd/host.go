// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"os/user"
	"strconv"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/host"
	"github.com/onemindos/onemindos/internal/netview"
	"github.com/onemindos/onemindos/internal/storage/ops"
	"github.com/onemindos/onemindos/internal/update"
)

const hostUsage = `usage:
  onemindd host serve [--socket PATH] [--user NAME] [--journal DIR] [--update-conf FILE] [--delay 3s]
`

// runHost is `onemindd host`: the host action service (#146, #142), its own
// privileged unit (os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-host.service).
// It restarts, shuts down and installs OS updates for actions the owner
// approved in the gateway (docs/leap/core/HOST-ACTIONS.md).
func runHost(args []string) int {
	if len(args) == 0 || args[0] != "serve" {
		fmt.Fprint(os.Stderr, hostUsage)
		return 2
	}
	fs := flag.NewFlagSet("onemindd host serve", flag.ContinueOnError)
	sock := fs.String("socket", env("ONEMIND_HOST_SOCKET", "/run/onemind/host.sock"), "Unix socket for the gateway")
	gwUser := fs.String("user", env("ONEMIND_HOST_USER", "onemind"), "the one user besides root allowed on the socket (the gateway's)")
	journal := fs.String("journal", env("ONEMIND_HOST_JOURNAL", "/data/onemind/host/actions"), "action journal directory")
	conf := fs.String("update-conf", env("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), "update.conf for OS installs")
	delay := fs.Duration("delay", 3*time.Second, "wait before the box goes down, so the gateway records the answer first")
	if err := fs.Parse(args[1:]); err != nil {
		return 2
	}
	log := newLogger()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	svc := &host.Service{Power: host.Systemd{}, OS: &host.UpdateEngine{ConfigPath: *conf, Log: log},
		BootID: host.BootID(), Delay: *delay, Log: log}
	if st, err := host.OpenStore(*journal); err != nil {
		log.Error("host journal unavailable: status only, every action refused", "dir", *journal, "err", err)
	} else {
		svc.Store = st
	}
	if err := svc.Resume(); err != nil {
		// Fail closed: an unreadable journal may hide an open action.
		log.Error("host journal unreadable: status only, every action refused", "err", err)
		svc.Store = nil
	}
	uid := -1
	if u, err := user.Lookup(*gwUser); err == nil {
		uid, _ = strconv.Atoi(u.Uid)
	} else {
		log.Warn("gateway user not found; root only", "user", *gwUser)
	}
	// The image passes the socket from onemind-host.socket (0660 root:onemind), so
	// nothing here chowns. Without systemd (development) it opens one, root only.
	l, err := host.ActivationListener(os.Getenv, os.Getpid(), 3)
	if err == nil && l == nil {
		l, err = ops.Listen(*sock, -1)
	}
	if err != nil {
		log.Error("cannot listen", "socket", *sock, "err", err)
		return 1
	}
	log.Info("host service listening", "socket", *sock, "journal", svc.Store != nil, "boot_id", svc.BootID, "gateway_uid", uid)
	err = (&host.Server{S: svc, AllowUID: uid, AllowGID: -1, Ctx: ctx, Network: networkView}).Serve(ctx, l)
	stop()
	svc.Wait()
	if err != nil {
		log.Error("host service stopped", "err", err)
		return 1
	}
	return 0
}

// networkView is GET /v1/network: the box's interfaces, gateways, DNS and listening ports, read from
// /sys and /proc (internal/netview). Files are capped so an odd host cannot make one answer huge.
func networkView() (any, error) {
	read := func(p string) ([]byte, error) {
		f, err := os.Open(p)
		if err != nil {
			return nil, err
		}
		defer f.Close()
		return io.ReadAll(io.LimitReader(f, 1<<20))
	}
	exists := func(p string) bool { _, err := os.Stat(p); return err == nil }
	return netview.System(read, exists).Collect()
}
