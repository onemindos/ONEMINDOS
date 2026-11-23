// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// servicesCommands is `onemind services`: the service cards (GET /v1/system/services, #623). Every
// systemd unit the OS ships, with the plain name from the image's services registry, its risk and what
// systemd says now. Owner only. `logs` and `restart` (#636) are in services_actions.go.
func servicesCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "services", Short: "The services this box runs, with a plain name and their state (owner)"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every systemd unit the OS ships: name, state, memory, risk (GET /v1/system/services)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := cl.Services.List(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, v); err != nil {
					return err
				}
			}
			if !v.Available {
				return exitWith(ExitUnreachable, "host_unavailable", "services: "+sanitize(deref(v.Message)))
			}
			if a.G.JSON {
				return nil
			}
			if err := table(a.Stdout, "UNIT\tNAME\tSTATE\tMEMORY\tRISK\tRESTART", ServiceRows(v)); err != nil {
				return err
			}
			if v.Message != nil {
				fmt.Fprintln(a.Stderr, "onemind: warning:", sanitize(*v.Message))
			}
			if n := derefInt(v.Unknown); n > 0 {
				fmt.Fprintf(a.Stderr, "onemind: warning: %d unit(s) run without a service card (shown as unknown)\n", n)
			}
			return nil
		},
	})
	g.AddCommand(serviceActionCommands(a)...)
	return []*cobra.Command{g}
}

// ServiceRows is the table: a unit not installed on this board shows "not installed"; an unknown unit
// shows its unit name and risk "unknown", never words the registry did not vouch for.
func ServiceRows(v *onemind.ServicesView) [][]string {
	rows := [][]string{}
	if v.Services == nil {
		return rows
	}
	for _, c := range *v.Services {
		state := "not installed"
		if c.Installed {
			state = dash(deref(c.ActiveState))
			if sub := deref(c.SubState); sub != "" && sub != state {
				state += " (" + sub + ")"
			}
		}
		memory := "-"
		if c.MemoryBytes != nil {
			memory = fmt.Sprintf("%.1f MB", float64(*c.MemoryBytes)/(1<<20))
		}
		name, restart := c.Name, "no"
		if !c.Known {
			name = "(unknown: no service card)"
		}
		if c.Restartable {
			restart = "yes"
		}
		rows = append(rows, []string{c.Unit, name, state, memory, string(c.Risk), restart})
	}
	return rows
}

func derefInt(p *int) int {
	if p == nil {
		return 0
	}
	return *p
}
