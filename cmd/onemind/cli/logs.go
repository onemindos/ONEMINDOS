// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/url"
	"strconv"

	"github.com/spf13/cobra"
)

// logsCommands is `onemind logs` (P-07): the whole-system journal through GET /v1/system/journal. The
// gateway checks the owner, redacts every line (tokens, passwords, keys, e-mail, IP and MAC addresses),
// limits the size and rate, and audits each read; this side strips terminal control characters. It only
// reads, so it files no approval. For one registry service, `onemind services logs UNIT` is the same
// stream with that unit's card checks.
func logsCommands(a *App) []*cobra.Command {
	var unit, priority string
	var boot, tail int
	var follow bool
	c := &cobra.Command{
		Use:   "logs",
		Short: "The whole box's system journal, redacted by the hub; -f follows new lines (owner)",
		Long: "Reads the systemd journal of the whole box through the gateway. Filter by --unit (such as sshd.service),\n" +
			"--priority (0-7 or emerg, alert, crit, err, warning, notice, info, debug: that level and worse) and\n" +
			"--boot (0 is this boot, -1 the one before). Output is redacted by the hub and bounded in size and rate.",
		Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			if tail < 1 || tail > 2000 {
				return exitWith(ExitUsage, "usage", "--tail must be 1-2000")
			}
			if boot > 0 || boot < -50 {
				return exitWith(ExitUsage, "usage", "--boot must be 0 (this boot) down to -50")
			}
			if follow && boot != 0 {
				return exitWith(ExitUsage, "usage", "--follow reads this boot only; leave --boot at 0")
			}
			q := url.Values{"tail": {strconv.Itoa(tail)}, "boot": {strconv.Itoa(boot)}}
			if unit != "" {
				q.Set("unit", unit)
			}
			if priority != "" {
				q.Set("priority", priority)
			}
			return a.streamLogs("/v1/system/journal", q, "logs", follow)
		},
	}
	f := c.Flags()
	f.StringVarP(&unit, "unit", "u", "", "only this systemd unit, such as sshd.service")
	f.StringVarP(&priority, "priority", "p", "", "this level and worse: 0-7 or emerg, alert, crit, err, warning, notice, info, debug")
	f.IntVarP(&boot, "boot", "b", 0, "0 is this boot, -1 the previous one")
	f.IntVarP(&tail, "tail", "n", 200, "how many recent lines (1-2000)")
	f.BoolVarP(&follow, "follow", "f", false, "keep printing new lines (at most 15 minutes; Ctrl-C stops)")
	return []*cobra.Command{c}
}
