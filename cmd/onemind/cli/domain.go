// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// domainCommands is `onemind domain` (NET-DOM-01, #238): your own domain on this box, through the gateway
// (GET and POST /v1/domains). Owner only. `add` registers the domain and prints the TXT record to put at the
// DNS provider; the dashboard's Network screen does the rest (check, remove). Approving a name records a
// decision only: nothing is served from the domain yet.
func domainCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "domain", Short: "Your own domain on this box (owner): list the domains, add one"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The domains, whether each is verified, and the names asked for under it (GET /v1/domains)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := cl.Domains.List(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			if !v.Enabled {
				fmt.Fprintln(a.Stderr, "onemind: your own domain is off on this box (ONEMIND_DOMAINS_ENABLED=1 turns it on)")
			}
			return table(a.Stdout, "DOMAIN\tSTATUS\tNAMES", DomainRows(v))
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "add DOMAIN",
		Short: "Register a domain you own and print the TXT record that proves it (POST /v1/domains)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			d, err := cl.Domains.Add(bg(), strings.TrimSpace(args[0]))
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, d)
			}
			fmt.Fprintf(a.Stdout, "domain: %s added, not verified yet.\n", sanitize(d.Domain))
			fmt.Fprintf(a.Stdout, "Add this %s record at your DNS provider, then check it on the Network screen:\n", sanitize(d.Proof.Type))
			fmt.Fprintf(a.Stdout, "  name:  %s\n  value: %s\n", sanitize(d.Proof.Name), sanitize(d.Proof.Value))
			return nil
		},
	})
	return []*cobra.Command{g}
}

// DomainRows is the table of `domain list`: one row per domain, with its names and their state.
func DomainRows(v *onemind.DomainsSummary) [][]string {
	rows := [][]string{}
	for _, d := range v.Domains {
		status := "not verified"
		if d.Verified {
			status = "verified"
		}
		names := make([]string, 0, len(d.Hosts))
		for _, h := range d.Hosts {
			names = append(names, h.Hostname+" ("+h.State+")")
		}
		rows = append(rows, []string{d.Domain, status, dash(strings.Join(names, ", "))})
	}
	return rows
}
