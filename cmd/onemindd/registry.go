// SPDX-License-Identifier: Apache-2.0

package main

import (
	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/rescue"
	"github.com/onemindos/onemindos/internal/service"
)

// subcommands are separate onemindd modes (`onemindd <name> ...`), each its own
// process with its own systemd unit and privileges. One line per feature.
var subcommands = map[string]func(args []string) int{
	"update":      runUpdate,
	"backup-init": runBackupInit, // backup.go: one-shot, creates the device key; the agent itself is backup.Service() below
	"storage":     runStorage,
	"host":        runHost,   // host.go: approved restart, shutdown, OS install (#146, #142), its own unit
	"mesh":        runMesh,   // net.go
	"relay":       runRelay,  // net.go: the owner's relay role (NETWORKING.md §4.4)
	"rescue":      runRescue, // rescue.go: the rescue console, its own unit (CORE-UPDATE-8)
	// The terminal's shell starts through this hidden mode, which drops every capability first (#273).
	rescue.ShellHelperCommand: rescue.RunShellHelper,
}

// optionalServices run inside the heartbeat agent's process, next to it.
// One line per internal/<feature> package, e.g. `backup.Service(),`.
var optionalServices = []service.Service{
	leafSupervisor.Service(joinedNode), // net.go: supervises the NATS leaf, feeds fabric.leaf_link
	backup.Service(),
}
