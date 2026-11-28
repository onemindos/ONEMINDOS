// SPDX-License-Identifier: Apache-2.0

package cli

// onemind tokens: your API tokens (GET/POST /v1/tokens, POST .../rotate, DELETE /v1/tokens/{id}).
// The gateway decides who may mint: only a signed-in person, and never more power than that person
// holds. A new secret is printed once and never stored by the CLI.

import (
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/spf13/cobra"
)

func tokensCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "tokens", Short: "API tokens for scripts and AI agents: list, create, rotate, revoke"}

	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your tokens (an owner sees everyone's); never the secret (GET /v1/tokens)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/tokens", func(w io.Writer, v any) error {
				var rows [][]string
				for _, t := range list(v) {
					m := obj(t)
					rows = append(rows, []string{str(m["id"]), str(m["name"]), str(m["kind"]), str(m["principal_id"]),
						joinStrs(m["scopes"], 40), dash(str(m["expires_at"])), dash(str(m["last_used_at"]))})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "No tokens yet. Create one with: onemind tokens create NAME")
					return nil
				}
				return table(w, "ID\tNAME\tKIND\tFOR\tSCOPES\tEXPIRES\tLAST USED", rows)
			})
		},
	})

	var agent, scopes string
	var days int
	create := &cobra.Command{
		Use:   "create NAME [--agent NAME] [--scopes a,b] [--days N]",
		Short: "Make a token, shown once (POST /v1/tokens); for yourself, or for one AI agent with --agent",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			body := map[string]any{"name": args[0], "principal": "self"}
			if agent != "" {
				id := agent
				if !strings.HasPrefix(id, "agent:") {
					id = "agent:" + id
				}
				body["principal"] = map[string]any{"kind": "agent", "id": id}
			}
			if scopes != "" {
				body["scopes"] = strings.Split(scopes, ",")
			}
			if cmd.Flags().Changed("days") {
				body["expires_in_days"] = days
			}
			v, err := a.gwDo(http.MethodPost, "/v1/tokens", body)
			if err != nil {
				return err
			}
			return a.printToken(v, "Created")
		},
	}
	create.Flags().StringVar(&agent, "agent", "", "make the token for this AI agent (agent:NAME); it can only ask, never approve")
	create.Flags().StringVar(&scopes, "scopes", "", "comma-separated scopes or bundles (default: the safe reader set for an agent)")
	create.Flags().IntVar(&days, "days", 0, "valid for this many days (the box sets the default and the maximum)")

	var grace int
	rotate := &cobra.Command{
		Use:   "rotate TOKEN_ID [--grace SECONDS]",
		Short: "Replace a token's secret, shown once; the old one stops (after --grace seconds, if given)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodPost, "/v1/tokens/"+pathID(args[0])+"/rotate", map[string]any{"grace_s": grace})
			if err != nil {
				return err
			}
			return a.printToken(v, "Rotated")
		},
	}
	rotate.Flags().IntVar(&grace, "grace", 0, "seconds the old secret keeps working, so a script can switch over")

	var yes bool
	revoke := &cobra.Command{
		Use:   "revoke TOKEN_ID --yes",
		Short: "Stop a token working now (DELETE /v1/tokens/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, yes, "revoking "+args[0]+" stops everything that uses it"); err != nil {
				return err
			}
			if _, err := a.gwDo(http.MethodDelete, "/v1/tokens/"+pathID(args[0]), nil); err != nil {
				return err
			}
			return a.printDone(map[string]any{"id": args[0], "revoked": true}, "Revoked %s.", args[0])
		},
	}
	revoke.Flags().BoolVar(&yes, "yes", false, "confirm")

	root.AddCommand(create, rotate, revoke)
	return []*cobra.Command{root}
}

// printToken shows a minted token: the secret appears here and nowhere else.
func (a *App) printToken(v any, verb string) error {
	if a.G.JSON {
		return printJSON(a.Stdout, v)
	}
	m := obj(v)
	secret := str(obj(m["one_time"])["token"])
	if a.G.Quiet {
		fmt.Fprintln(a.Stdout, secret)
		return nil
	}
	fmt.Fprintf(a.Stdout, "%s token %s (%s), expires %s.\n", verb, str(m["id"]), sanitize(str(m["name"])), dash(str(m["expires_at"])))
	fmt.Fprintf(a.Stdout, "Copy it now, it is shown once and cannot be read again:\n  %s\n", secret)
	return nil
}

func init() { groups = append(groups, tokensCommands) }
