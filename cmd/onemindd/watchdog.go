// SPDX-License-Identifier: Apache-2.0

package main

import (
	"github.com/onemindos/onemindos/internal/service"
	"github.com/onemindos/onemindos/internal/watchdog"
)

// watchdogService is the node-side hub watcher (#687): it alerts locally and over the LAN when
// the leaf link to the hub stays down. Off unless /etc/onemind/watchdog.json exists, the node
// is joined, and never on a hub.
func watchdogService(role string) service.Service {
	return watchdog.Service(leafSupervisor.Link, joinedNode, role)
}
