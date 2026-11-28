// SPDX-License-Identifier: Apache-2.0

package jobs

import (
	"context"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/version"
)

// Builtin is the job kinds every joined machine runs itself. Only read-only
// kinds live here: a kind that changes the machine (update.apply, os.rollback,
// system.restart_unit) is handed to the process that holds that right, never
// run inside the read-only heartbeat agent.
func Builtin(nodeID string) map[string]Handler {
	return map[string]Handler{
		// host.check: the machine is reachable on the durable job path and runs this agent version.
		"host.check": func(context.Context, backup.Job) Result {
			return Result{State: StateSucceeded, Summary: "node-" + nodeID + " onemindd " + version.Version}
		},
	}
}
