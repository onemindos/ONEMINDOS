// SPDX-License-Identifier: Apache-2.0

package main

import (
	"log/slog"
	"os"

	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

// runMesh is `onemindd mesh enroll|wait-ip|status` (NETWORKING.md §5.2: the
// k3s and NATS units wait for the mesh address with `onemindd mesh wait-ip`).
func runMesh(args []string) int { return mesh.RunCLI(args, os.Stdout, os.Stderr) }

// leafSupervisor supervises the local NATS leaf of a joined node (CORE-NET-12, slop CS2-06): it
// loads the persisted leaf.Config, watches the loopback monitor (the heartbeat's
// fabric.leaf_link reads it), reloads the unit when `onemind fabric join` rewrites the Config
// and restarts it after repeated failed checks. It does not write leaf.conf: onemindd's sandbox
// keeps /etc read-only, so the join command renders it.
var leafSupervisor = leaf.NewSupervisor(leaf.DefaultConfPath, leaf.DefaultConfigPath, "", slog.Default())

// joinedNode reports whether `onemind fabric join` ran on this machine (the leaf exists only then).
func joinedNode() bool { _, err := fabric.LoadState("/"); return err == nil }

// netReports are the heartbeat's mesh and fabric objects (contract §12.10).
func netReports(role string, log *slog.Logger) (func() *mesh.Heartbeat, func() *heartbeat.Fabric) {
	return mesh.Reporter(log), fabric.Reporter(role, leafSupervisor.Link)
}
