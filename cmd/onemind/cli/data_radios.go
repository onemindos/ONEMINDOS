// SPDX-License-Identifier: Apache-2.0

package cli

// onemind data grants and onemind radios.
//
// `data grants`: who may read or write which kind of your data (the data commons), GET
// /v1/data/grants; taking a grant back is DELETE /v1/data/grants/{id} (removing power is direct, and
// the gateway restricts it to an owner). Giving one is a request in `onemind actions`.
//
// `radios`: radios the box found on its machines (GET /v1/radios). Confirming what a radio is
// (POST /v1/radios/{id}/confirm) is an owner's statement and human-only: the gateway refuses an
// agent token, and nothing is opened or sent by confirming.

import (
	"fmt"
	"io"
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

func radiosCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "radios", Short: "Radios found on your machines: list, confirm what one is (owner only)"}
	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Radios the box found (GET /v1/radios)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/radios", func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(v) {
					m := obj(x)
					conf := "-" // only a radio that asks for confirming has a confirm card
					if c := obj(m["confirm"]); len(c) > 0 {
						conf = "needs confirming"
						if c["confirmed"] == true {
							conf = "confirmed as " + str(c["profile"])
						}
					}
					rows = append(rows, []string{str(m["id"]), dash(str(m["hostname"])), dash(str(m["kind"])), dash(str(m["model"])), str(m["node_status"]), conf})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "No radios found.")
					return nil
				}
				return table(w, "ID\tMACHINE\tKIND\tMODEL\tMACHINE STATE\tCONFIRMED", rows)
			})
		},
	})
	var profile string
	confirm := &cobra.Command{
		Use:   "confirm RADIO_ID --profile PROFILE",
		Short: "Say what a found radio is, e.g. --profile meshcore-companion-usb (POST /v1/radios/ID/confirm); owner only",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if profile == "" {
				return usageErr(cmd, "--profile is required (the card in `onemind radios list --json` names it)")
			}
			v, err := a.gwDo(http.MethodPost, "/v1/radios/"+pathID(args[0])+"/confirm", map[string]any{"profile": profile})
			if err != nil {
				return err
			}
			return a.printDone(v, "Confirmed %s as %s. Nothing was opened or sent.", args[0], profile)
		},
	}
	confirm.Flags().StringVar(&profile, "profile", "", "what the radio is")
	root.AddCommand(confirm)
	return []*cobra.Command{root}
}

func init() { groups = append(groups, dataCommands, radiosCommands) }
