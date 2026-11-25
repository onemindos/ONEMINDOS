// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// firewallCommands is `onemind firewall`: the box's live firewall in plain words (GET
// /v1/network/firewall, P-09 part 1). Owner only and read only. Allow rules with automatic revert are
// part 2: they will be `onemind firewall allow`, which only files a request the owner approves.
func firewallCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "firewall", Short: "This box's firewall: what is open, and to whom (owner, read only)"}
	g.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "What the firewall lets in, each rule in plain words (GET /v1/network/firewall)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := cl.Network.Firewall(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, v); err != nil {
					return err
				}
			}
			if !v.Available {
				return exitWith(ExitUnreachable, "host_unavailable", "firewall: "+sanitize(deref(v.Message)))
			}
			if a.G.JSON {
				return nil
			}
			fmt.Fprintln(a.Stdout, sanitize(deref(v.Headline)))
			fmt.Fprintln(a.Stdout)
			if err := table(a.Stdout, "CHAIN\t#\tACTION\tFROM\tWHAT IT DOES", FirewallRows(v)); err != nil {
				return err
			}
			if n := derefInt(v.Dropped); n > 0 {
				fmt.Fprintf(a.Stderr, "onemind: warning: %d entr%s left out because the box reported something that did not check out\n", n, map[bool]string{true: "y was", false: "ies were"}[n == 1])
			}
			if n := derefInt(v.Truncated); n > 0 {
				fmt.Fprintf(a.Stderr, "onemind: warning: %d part%s of the rules left out for size; this view is not complete\n", n, map[bool]string{true: "", false: "s"}[n == 1])
			}
			return nil
		},
	})
	return []*cobra.Command{g}
}

// audienceName is the short column text; the long form is in each rule's summary.
var audienceName = map[string]string{
	"this_machine": "this box", "mesh": "mesh", "pod_network": "apps on this box", "lan": "LAN",
	"specific_address": "one address", "one_interface": "one connection", "any_network": "ANY ADDRESS",
}

// FirewallRows is the table: one row per rule, in the order the firewall tries them. Words come from
// the gateway's summary (already checked there); control characters are stripped again here.
func FirewallRows(v *onemind.FirewallView) [][]string {
	rows := [][]string{}
	if v.Rules == nil {
		return rows
	}
	for _, r := range *v.Rules {
		from := audienceName[string(r.Audience)]
		if from == "" {
			from = "unknown"
		}
		rows = append(rows, []string{sanitize(r.Chain), fmt.Sprint(r.Position), strings.ToUpper(sanitize(string(r.Action))), from, sanitize(r.Summary)})
	}
	return rows
}
