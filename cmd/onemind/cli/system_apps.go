// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// systemAppsCommands are `onemind apps built-in`, `apps disable ID` and `apps enable ID`: the Built in
// area. Built-in apps cannot be removed (the hub answers 409 system_app_protected), only switched off:
// the workload stops, volumes, secrets and settings stay. An agent token may file the request but only an
// owner approves it. A switched-off app is hidden from `apps list`, so these commands do not look it up
// there; the hub checks the id against the signed list.
func systemAppsCommands(a *App) []*cobra.Command {
	list := &cobra.Command{
		Use:   "built-in",
		Short: "The Built in apps: on or off, version, licence, update channel (GET /v1/system-apps)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			rows, err := c.Apps.System(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, rows)
			}
			out := [][]string{}
			for _, x := range rows {
				state := "on"
				if !x.Enabled {
					state = "off"
				}
				if !x.CanDisable {
					state += " (always)"
				}
				out = append(out, []string{x.Id, sanitize(x.Name), state, dash(deref(x.Version)), dash(deref(x.License)), dash(deref(x.UpdateChannel))})
			}
			return table(a.Stdout, "ID\tNAME\tSTATE\tVERSION\tLICENCE\tUPDATES", out)
		},
	}
	return []*cobra.Command{list,
		switchCommand(a, onemind.ActionAppDisable, "disable APP_ID", "Request switching a built-in app off; its data is kept (owners approve)"),
		switchCommand(a, onemind.ActionAppEnable, "enable APP_ID", "Request switching a built-in app back on (owners approve)")}
}

func switchCommand(a *App, typ, use, short string) *cobra.Command {
	var noApprove, yes bool
	var wait time.Duration
	cmd := &cobra.Command{
		Use:   use,
		Short: short,
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			waitSet := cmd.Flags().Changed("wait")
			if !noApprove && !yes && !a.Interactive() {
				return exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --no-approve to only file the request (or --yes to approve it as the owner)")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			act, err := c.Actions.Request(bg(), onemind.ActionRequest{Type: typ, AppID: args[0]})
			if err != nil {
				return err
			}
			if !a.G.JSON {
				fmt.Fprintf(a.Stdout, "Requested action %s  %s %s\n", act.Id, typ, args[0])
			}
			if noApprove {
				if waitSet {
					return a.waitAction(c, act.Id, wait)
				}
				if a.G.JSON {
					return printJSON(a.Stdout, act)
				}
				if a.G.Quiet {
					fmt.Fprintln(a.Stdout, act.Id)
				} else {
					fmt.Fprintf(a.Stdout, "Waiting for an owner: onemind actions approve %s\n", act.Id)
				}
				return nil
			}
			ok := yes
			if !ok {
				if ok, err = a.confirm("Approve now?", "--yes"); err != nil {
					return err
				}
			}
			if !ok {
				return exitWith(ExitPending, "pending", fmt.Sprintf("left waiting for approval: onemind actions approve %s", act.Id))
			}
			if _, err := c.Actions.Approve(bg(), act.Id); err != nil {
				if errors.Is(err, onemind.ErrPermissionDenied) {
					return exitWith(ExitPermissionDenied, "permission_denied",
						fmt.Sprintf("requested %s, but this principal may not approve; an owner runs: onemind actions approve %s", act.Id, act.Id))
				}
				return err
			}
			if !waitSet {
				wait = 10 * time.Minute
			}
			return a.waitAction(c, act.Id, wait)
		},
	}
	cmd.Flags().BoolVar(&noApprove, "no-approve", false, "only file the request (scripts, agents, non-owners)")
	cmd.Flags().BoolVar(&yes, "yes", false, "approve without asking (owner token)")
	cmd.Flags().DurationVar(&wait, "wait", 10*time.Minute, "wait for the outcome (default 10m)")
	cmd.Flags().Lookup("wait").NoOptDefVal = "10m"
	return cmd
}
