// SPDX-License-Identifier: Apache-2.0

package cli

// onemind radios: the radios found on the machines (GET /v1/radios) and confirming what one is
// (POST /v1/radios/{id}/confirm). Confirming is a person's statement, never an agent's: the gateway
// answers 403 to every token that is not an owner's. It opens, probes and sends nothing, and it does
// not give any app the radio (that is a separate approval).

import (
	"io"
	"net/http"
	"net/url"

	"github.com/spf13/cobra"
)

func radiosCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "radios", Short: "Radios found on your machines, and confirming what one is (owner only)"}
	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every USB radio on every machine (GET /v1/radios); changes nothing",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/radios", func(w io.Writer, v any) error {
				var rows [][]string
				for _, r := range list(v) {
					m := obj(r)
					c := obj(m["confirm"])
					state := "-"
					if len(c) > 0 {
						state = "not confirmed"
						if c["confirmed"] == true {
							state = "confirmed as " + str(c["label"])
						}
					}
					rows = append(rows, []string{str(m["id"]), dash(str(m["hostname"])), str(m["node_status"]), str(m["kind"]), dash(str(m["model"])), state})
				}
				return table(w, "RADIO\tMACHINE\tSTATE\tKIND\tMODEL\tCONFIRMATION", rows)
			})
		},
	})
	var profile string
	confirm := &cobra.Command{
		Use:   "confirm RADIO_ID [--profile P]",
		Short: "Say what a found radio is, as an owner (POST /v1/radios/{id}/confirm); an agent token is refused",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			id := args[0]
			if profile == "" {
				// Use the profile the radio's own card asks about, so a person does not need to know its name.
				cards, err := a.gwDo(http.MethodGet, "/v1/radios", nil)
				if err != nil {
					return err
				}
				for _, r := range list(cards) {
					if str(obj(r)["id"]) == id {
						profile = str(obj(obj(r)["confirm"])["profile"])
					}
				}
				if profile == "" {
					return exitWith(ExitNotFound, "not_found", "no radio "+id+" asks to be confirmed; see `onemind radios list`")
				}
			}
			v, err := a.gwDo(http.MethodPost, "/v1/radios/"+url.PathEscape(id)+"/confirm", map[string]any{"profile": profile})
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				c := obj(obj(v)["confirm"])
				if err := kv(w, [][2]string{{"radio", id}, {"confirmed as", str(c["label"])}, {"at", dash(str(c["confirmed_at"]))}}); err != nil {
					return err
				}
				_, err := io.WriteString(w, "Nothing was opened or sent.\n")
				return err
			})
		},
	}
	confirm.Flags().StringVar(&profile, "profile", "", "what the radio is (default: what its card asks, for example meshcore-companion-usb)")
	root.AddCommand(confirm)
	return []*cobra.Command{root}
}
