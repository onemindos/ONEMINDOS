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

// leafMonitor watches the local NATS leaf of a joined node; the heartbeat's
// fabric.leaf_link reads it.
var leafMonitor = func() *leaf.Monitor {
	m := leaf.NewMonitor(leaf.DefaultConfPath, leaf.DefaultMonitor)
	m.Enabled = func() bool { _, err := fabric.LoadState("/"); return err == nil } // a joined node
	return m
}()

// netReports are the heartbeat's mesh and fabric objects (contract §12.10).
func netReports(role string, log *slog.Logger) (func() *mesh.Heartbeat, func() *heartbeat.Fabric) {
	return mesh.Reporter(log), fabric.Reporter(role, leafMonitor.Link)
}
