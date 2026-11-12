// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/mesh"
	"github.com/onemindos/onemindos/internal/service"
)

// subcommands are separate onemindd modes (`onemindd <name> ...`), each its own
// process with its own systemd unit and privileges. One line per feature.
var subcommands = map[string]func(args []string) int{
	"update": runUpdate,
	"mesh":   func(a []string) int { return mesh.RunCLI(a, os.Stdout, os.Stderr) },
}

// optionalServices run inside the heartbeat agent's process, next to it.
// One line per internal/<feature> package, e.g. `backup.Service(),`.
var optionalServices = []service.Service{
	backup.Service(),
}
