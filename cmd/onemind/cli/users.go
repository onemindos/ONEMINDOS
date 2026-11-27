// SPDX-License-Identifier: Apache-2.0

package cli

// onemind users: the people on this box, over the gateway (GET/POST /v1/users,
// POST /v1/users/{id}/disable). Only an owner may use these routes; the gateway answers 403 to
// anyone else (an agent token included) and audits it. The CLI holds no extra power.

import (
	"fmt"
	"io"
	"net/http"
	"net/url"

	"github.com/spf13/cobra"
)

func usersCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "users", Short: "The people on this box: list, invite, disable (owner only)"}

	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Everyone with an account (GET /v1/users)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/users", func(w io.Writer, v any) error {
				var rows [][]string
				for _, u := range list(v) {
					m := obj(u)
					state := "active"
					switch {
					case m["disabled"] == true:
						state = "disabled"
					case m["enrolled"] != true:
						state = "invited"
					}
					rows = append(rows, []string{str(m["id"]), str(m["display_name"]), dash(str(m["username"])), str(m["role"]), state, dash(str(m["last_seen_at"]))})
				}
				return table(w, "ID\tNAME\tUSERNAME\tROLE\tSTATE\tLAST SEEN", rows)
			})
		},
	})

	var role, username string
	var secretsStdin bool
	invite := &cobra.Command{
		Use:   "invite NAME",
		Short: "Add a person and print their one-time 24-hour invitation link",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			body := map[string]any{"display_name": args[0], "role": role, "username": nil}
			if username != "" {
				body["username"] = username
			}
			var v any
			var err error
			if role == "owner" {
				v, err = a.gwDo(http.MethodPost, "/v1/users", body)
			} else {
				v, err = a.familyInvite("/v1/users/invites", "users.invite", "", body, secretsStdin, false)
			}
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			u, one := obj(v), obj(obj(v)["one_time"])
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, str(one["enrolment_url"]))
				return nil
			}
			fmt.Fprintf(a.Stdout, "Invited %s (%s, %s).\n", sanitize(str(u["display_name"])), str(u["id"]), str(u["role"]))
			fmt.Fprintf(a.Stdout, "Sign-up link, shown once, valid until %s:\n  %s\n", str(one["expires_at"]), str(one["enrolment_url"]))
			return nil
		},
	}
	invite.Flags().StringVar(&role, "role", "adult", "owner, adult, teen, child or guest")
	invite.Flags().StringVar(&username, "username", "", "sign-in name (optional)")
	invite.Flags().BoolVar(&secretsStdin, "secrets-stdin", false, "read password and authenticator code from stdin if step-up is required")

	var reinviteStdin, reinviteYes bool
	reinvite := &cobra.Command{Use: "reinvite USER_ID", Short: "Reset a family member's sign-in with a new invitation",
		Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
			if !reinviteYes {
				return usageErr(cmd, "issuing a replacement invitation clears this person's sign-in credentials and sessions. Repeat with --yes to confirm")
			}
			v, err := a.familyInvite("/v1/users/"+url.PathEscape(args[0])+"/invite", "users.reinvite", args[0], nil, reinviteStdin, true)
			if err != nil {
				return err
			}
			return a.accountResult(str(obj(obj(v)["one_time"])["enrolment_url"]), v)
		}}
	reinvite.Flags().BoolVar(&reinviteYes, "yes", false, "confirm clearing current sign-in credentials and sessions")
	reinvite.Flags().BoolVar(&reinviteStdin, "secrets-stdin", false, "read password, authenticator code and screen code from separate stdin lines")

	var yes bool
	disable := &cobra.Command{
		Use:   "disable USER_ID",
		Short: "Stop a person signing in (POST /v1/users/ID/disable; the last owner cannot be disabled)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !yes {
				return usageErr(cmd, "disabling "+args[0]+" ends their sessions: repeat with --yes to confirm")
			}
			v, err := a.gwDo(http.MethodPost, "/v1/users/"+url.PathEscape(args[0])+"/disable", nil)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			fmt.Fprintf(a.Stdout, "Disabled %s.\n", args[0])
			return nil
		},
	}
	disable.Flags().BoolVar(&yes, "yes", false, "confirm")
	root.AddCommand(invite, reinvite, disable)
	return []*cobra.Command{root}
}
