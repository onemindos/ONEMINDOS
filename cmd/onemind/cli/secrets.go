// SPDX-License-Identifier: Apache-2.0

package cli

// onemind secrets: an app's secret settings (GET/POST /v1/apps/{id}/secrets, GET /v1/secrets/public-key).
// The CLI never sees or sends a secret value: `show` lists which keys are set, `generate` asks the
// box to make a new random value, `clear` asks it to remove one. A value you type is sealed in the
// dashboard form (in your browser, to the box's public key), so it never crosses this terminal.
// Both changes only FILE a request (app.configure) that an owner approves.

import (
	"fmt"
	"io"
	"net/http"

	"github.com/spf13/cobra"
)

func secretsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "secrets", Short: "An app's secret settings: which are set, make a new one, remove one (never shows a value)"}

	root.AddCommand(&cobra.Command{
		Use:   "show APP_ID",
		Short: "Which secrets the app needs and which are set (GET /v1/apps/ID/secrets)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/apps/"+pathID(args[0])+"/secrets", func(w io.Writer, v any) error {
				var rows [][]string
				for _, s := range list(obj(v)["secrets"]) {
					sm := obj(s)
					for _, k := range list(sm["keys"]) {
						km := obj(k)
						state := "not set"
						if km["set"] == true {
							state = "set (v" + jnum(km["version"]) + ")"
						}
						req := "optional"
						if km["required"] == true {
							req = "required"
						}
						rows = append(rows, []string{str(sm["name"]) + "/" + str(km["key"]), str(km["kind"]), req, state, dash(str(km["updated_at"]))})
					}
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "This app has no secret settings.")
					return nil
				}
				if err := table(w, "SECRET/KEY\tKIND\tNEEDED\tSTATE\tUPDATED", rows); err != nil {
					return err
				}
				if miss := list(obj(v)["missing_required"]); len(miss) > 0 {
					fmt.Fprintf(w, "\nStill missing: %s\n", joinStrs(miss, 0))
				}
				return nil
			})
		},
	})

	root.AddCommand(&cobra.Command{
		Use:   "public-key",
		Short: "The box's key that sealed secret forms are encrypted to (GET /v1/secrets/public-key)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/secrets/public-key", func(w io.Writer, v any) error {
				pairs := [][2]string{}
				for _, k := range []string{"key_id", "alg", "key", "sealed_alg"} {
					if s := str(obj(v)[k]); s != "" {
						pairs = append(pairs, [2]string{k, s})
					}
				}
				return kv(w, pairs)
			})
		},
	})

	var reason string
	change := func(use, short, field string) *cobra.Command {
		return &cobra.Command{
			Use:   use + " APP_ID SECRET/KEY...",
			Short: short,
			Args:  cobra.MinimumNArgs(2),
			RunE: func(_ *cobra.Command, args []string) error {
				body := map[string]any{field: args[1:]}
				if reason != "" {
					body["reason"] = reason
				}
				return a.requestWrite(use+" of "+joinStrs(toAny(args[1:]), 0)+" for "+args[0], http.MethodPost, "/v1/apps/"+pathID(args[0])+"/secrets", body)
			},
		}
	}
	gen := change("generate", "Request a new random value for these keys (POST /v1/apps/ID/secrets); an owner approves", "generate")
	clr := change("clear", "Request removing these keys' values (POST /v1/apps/ID/secrets); an owner approves", "clear")
	for _, c := range []*cobra.Command{gen, clr} {
		c.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")
	}
	root.AddCommand(gen, clr)
	return []*cobra.Command{root}
}

func toAny(ss []string) []any {
	out := make([]any, len(ss))
	for i, s := range ss {
		out[i] = s
	}
	return out
}

func init() { groups = append(groups, secretsCommands) }
