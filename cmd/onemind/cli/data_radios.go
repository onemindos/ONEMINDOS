// SPDX-License-Identifier: Apache-2.0

package cli

// onemind data grants and onemind radios.
//
// `data grants`: who may read or write which kind of your data (the data commons), GET
// /v1/data/grants; taking a grant back is DELETE /v1/data/grants/{id} (removing power is direct, and
// the gateway restricts it to an owner). Giving one is a request in `onemind actions`.
//
// The `radios` commands live in radios.go.

import (
	"net/http"

	"github.com/spf13/cobra"
)

func dataCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "data", Short: "The data commons: who may read or write which kind of your data"}
	grants := &cobra.Command{Use: "grants", Short: "Data grants: list, revoke"}
	grants.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every grant and what it allows (GET /v1/data/grants)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/data/grants", "ID\tWHO\tDATA\tALLOWS\tSTATE\tEXPIRES", func(m map[string]any) []string {
				var allows []any
				for _, k := range []string{"read", "write", "aggregate"} {
					if m[k] == true {
						allows = append(allows, k)
					}
				}
				state := "active"
				if m["active"] != true {
					state = "revoked"
				}
				g := obj(m["grantee"])
				return []string{str(m["id"]), str(g["kind"]) + ":" + str(g["id"]), str(m["data_class"]), joinStrs(allows, 0), state, dash(str(m["expires_at"]))}
			})
		},
	})
	var yes bool
	rev := &cobra.Command{
		Use:   "revoke GRANT_ID --yes",
		Short: "Take a grant back now (DELETE /v1/data/grants/ID); owner only",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, yes, "revoking "+args[0]+" stops that access to your data"); err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodDelete, "/v1/data/grants/"+pathID(args[0]), nil)
			if err != nil {
				return err
			}
			if v == nil {
				v = map[string]any{"id": args[0], "revoked": true}
			}
			return a.printDone(v, "Revoked %s.", args[0])
		},
	}
	rev.Flags().BoolVar(&yes, "yes", false, "confirm")
	grants.AddCommand(rev)
	root.AddCommand(grants)
	return []*cobra.Command{root}
}

func init() { groups = append(groups, dataCommands) }
