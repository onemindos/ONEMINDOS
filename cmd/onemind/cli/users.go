// SPDX-License-Identifier: Apache-2.0

package cli

// onemind users: the people on this box. The gateway authorizes the owner.

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	onemind "github.com/onemindos/onemindos/sdk/go"
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
		Short: "Create a one-time invitation from your signed-in owner account",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			body := map[string]any{"display_name": args[0], "role": role, "username": nil}
			if username != "" {
				body["username"] = username
			}
			v, err := a.createUserInvite(body, secretsStdin)
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
	invite.Flags().BoolVar(&secretsStdin, "secrets-stdin", false, "read password, fresh authenticator code and any required screen code from stdin")

	var reinviteYes bool
	reinvite := &cobra.Command{Use: "reinvite USER_ID", Short: "Request a replacement invitation for a family member",
		Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
			if !reinviteYes {
				return usageErr(cmd, "approving a replacement invitation clears this person's sign-in credentials and sessions. Repeat with --yes to submit the request")
			}
			return a.requestFamilyInvite("/v1/users/"+url.PathEscape(args[0])+"/invite", nil)
		}}
	reinvite.Flags().BoolVar(&reinviteYes, "yes", false, "confirm submitting a request to clear current sign-in credentials and sessions")

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

func (a *App) requestFamilyInvite(path string, body any) error {
	c, err := a.selectedAccountClient(false)
	if err != nil {
		return err
	}
	var action map[string]any
	if err := c.Do(bg(), http.MethodPost, path, body, &action); err != nil {
		return explainGateway(err)
	}
	id := str(action["id"])
	if id == "" || action["state"] != "awaiting_approval" {
		return fmt.Errorf("the box did not return a pending invitation request")
	}
	if a.G.JSON {
		return printJSON(a.Stdout, action)
	}
	if a.G.Quiet {
		_, err = fmt.Fprintln(a.Stdout, sanitize(id))
		return err
	}
	_, err = fmt.Fprintf(a.Stdout, "Invitation requested (%s). Open Approvals in the dashboard to verify the request and collect the link.\n", sanitize(id))
	return err
}

func (a *App) createUserInvite(body map[string]any, secretsStdin bool) (any, error) {
	c, err := a.selectedAccountClient(false)
	if err != nil {
		return nil, err
	}
	const path = "/v1/users"
	var invite any
	err = c.Do(bg(), http.MethodPost, path, body, &invite)
	if err == nil {
		return invite, nil
	}
	var gatewayErr *onemind.Error
	if !errors.As(err, &gatewayErr) || gatewayErr.Reason != "step_up_required" || !(secretsStdin || a.Interactive()) {
		return nil, explainGateway(err)
	}
	var options struct {
		Challenge   string `json:"challenge"`
		BoxRequired bool   `json:"box_code_required"`
	}
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/step-up/options", map[string]any{
		"op": "users.create", "body": body, "method": "password+totp", "at_box": true,
	}, &options); err != nil {
		return nil, explainGateway(err)
	}
	if options.Challenge == "" {
		return nil, fmt.Errorf("the box did not return an invitation verification challenge")
	}
	proof := map[string]string{"challenge": options.Challenge}
	for _, field := range [][2]string{{"password", "Password"}, {"totp", "Fresh authenticator code"}} {
		value, err := a.accountSecret(field[1], secretsStdin)
		if err != nil {
			return nil, err
		}
		proof[field[0]] = value
	}
	proof["totp"] = strings.TrimSpace(proof["totp"])
	verification := map[string]any{"password_totp": proof}
	if options.BoxRequired {
		code, err := a.accountSecret("Code on the box's screen", secretsStdin)
		if err != nil {
			return nil, err
		}
		verification["box_code"] = strings.TrimSpace(code)
	}
	var grant struct {
		StepUp string `json:"step_up"`
	}
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/step-up", verification, &grant); err != nil {
		return nil, explainGateway(err)
	}
	if grant.StepUp == "" {
		return nil, fmt.Errorf("the box did not return an invitation verification grant")
	}
	if err := c.DoWithStepUp(bg(), http.MethodPost, path, grant.StepUp, body, &invite); err != nil {
		return nil, explainGateway(err)
	}
	return invite, nil
}
