// SPDX-License-Identifier: Apache-2.0

package main

import "github.com/onemindos/onemindos/internal/service"

// subcommands are separate onemindd modes (`onemindd <name> ...`), each its own
// process with its own systemd unit and privileges. One line per feature.
var subcommands = map[string]func(args []string) int{
	"update": runUpdate,
	"backup": runBackup, // backup.go: own process, own unit (onemind-backup.service)
}

// optionalServices run inside the heartbeat agent's process, next to it.
// One line per internal/<feature> package, e.g. `backup.Service(),`.
var optionalServices = []service.Service{}
