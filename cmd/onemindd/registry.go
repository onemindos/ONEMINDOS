// SPDX-License-Identifier: Apache-2.0

package main

import (
	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/service"
)

// subcommands are separate onemindd modes (`onemindd <name> ...`), each its own
// process with its own systemd unit and privileges. One line per feature.
var subcommands = map[string]func(args []string) int{
	"update":      runUpdate,
	"backup-init": runBackupInit, // backup.go: one-shot, creates the device key; the agent itself is backup.Service() below
	"mesh":        runMesh,       // net.go
}

// optionalServices run inside the heartbeat agent's process, next to it.
// One line per internal/<feature> package, e.g. `backup.Service(),`.
var optionalServices = []service.Service{
	leafSupervisor.Service(joinedNode), // net.go: supervises the NATS leaf, feeds fabric.leaf_link
	backup.Service(),
}
