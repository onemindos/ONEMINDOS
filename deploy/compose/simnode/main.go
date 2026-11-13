// SPDX-License-Identifier: Apache-2.0

// Command simnode is a simulated OneMind machine for the compose dev hub
// (deploy/compose): onemindd's own agent (internal/agent, heartbeat every 10 s
// on onemind.node.<id>.status and the local API on :7480) with the hardware
// read from a fixture tree instead of the real machine, for example the
// Raspberry Pi 5 and Jetson trees in internal/detect/testdata. Ported from
// PR #27's sim-node, which sent hand-written heartbeats; this one sends exactly
// what onemindd would send on that board, so it cannot drift from contract §2.
//
//	simnode -root /fixture/rpi5 -arch arm64 [-hostname sim-pi5]
//
// Environment as onemindd: ONEMIND_NATS_URL, ONEMIND_NODE_ROLE, ONEMIND_NODE_ID,
// ONEMIND_AGENT_ADDR. Development only: it reports a machine that is not there.
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/onemindos/onemindos/internal/agent"
	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	root := flag.String("root", "", "fixture tree to read the hardware from (required)")
	arch := flag.String("arch", "arm64", "architecture the simulated machine reports (amd64 or arm64)")
	hostname := flag.String("hostname", "", "hostname to report (default: the fixture's etc/hostname)")
	natsURL := flag.String("nats", os.Getenv("ONEMIND_NATS_URL"), "hub NATS URL (empty = local API only)")
	role := flag.String("role", env("ONEMIND_NODE_ROLE", "node"), "hub or node")
	listen := flag.String("listen", env("ONEMIND_AGENT_ADDR", agent.DefaultListen), "local API listen address")
	interval := flag.Duration("interval", agent.DefaultInterval, "heartbeat interval")
	flag.Parse()

	if err := check(*root, *arch, *role, os.Getenv("ONEMIND_NODE_ID")); err != nil {
		fmt.Fprintln(os.Stderr, "simnode:", err)
		os.Exit(2)
	}
	col := detect.NewFixture(*root, *arch)
	col.Role = *role
	col.NodeID = os.Getenv("ONEMIND_NODE_ID")
	col.Hostname = *hostname

	log := slog.New(slog.NewTextHandler(os.Stderr, nil))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	log.Info("simnode starting", "root", *root, "node_id", col.ID(), "board", col.Board(), "arch", *arch)
	a := agent.New(agent.Config{Listen: *listen, NATSURL: *natsURL, Interval: *interval, Collector: col, Logger: log})
	if err := a.Run(ctx); err != nil {
		log.Error("simnode stopped", "err", err)
		os.Exit(1)
	}
}

// check validates the flags the same way onemindd validates its own.
func check(root, arch, role, nodeID string) error {
	if root == "" {
		return fmt.Errorf("-root is required (a fixture tree such as internal/detect/testdata/rpi5)")
	}
	if st, err := os.Stat(root); err != nil || !st.IsDir() {
		return fmt.Errorf("-root %q is not a directory", root)
	}
	if arch != "amd64" && arch != "arm64" {
		return fmt.Errorf("-arch must be amd64 or arm64, got %q", arch)
	}
	if err := heartbeat.ValidateRole(role); err != nil {
		return err
	}
	if nodeID != "" {
		if err := heartbeat.ValidateNodeID(nodeID); err != nil {
			return fmt.Errorf("ONEMIND_NODE_ID: %w", err)
		}
	}
	return nil
}
