// SPDX-License-Identifier: Apache-2.0

package main

import (
	"github.com/onemindos/onemindos/internal/service"
	"github.com/onemindos/onemindos/internal/watchdog"
)

// watchdogService is the node-side hub watcher (#687): it alerts locally and over the LAN when
// the hub heartbeat stops. Off unless /etc/onemind/watchdog.json exists, and never on a hub.
func watchdogService(natsURL, natsSeed, role string) service.Service {
	return watchdog.Service(natsURL, natsSeed, role)
}
