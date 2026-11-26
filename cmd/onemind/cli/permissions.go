// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// permissionsCommands is `onemind permissions` (gateway permissions design §3.12): how the gateway
// decides who may do what without asking. The CLI reads and requests; every change it sends is the
// signed-in person's own, checked by the gateway (owner only where it loosens anything).
func permissionsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "permissions", Short: "Deny rules, standing approvals and modes: what may happen without asking"}
	root.AddCommand(permissionsDenyCommands(a))
	return []*cobra.Command{root}
}

// stepUpHint turns the gateway's step_up_required into a plain instruction: the CLI cannot do a
// passkey ceremony, so the person signs in with their passkey in the dashboard first.
func stepUpHint(err error, what string) error {
	var ge *onemind.Error
	if errors.As(err, &ge) && ge.Reason == "step_up_required" {
		return exitWith(ExitUsage, "usage", what+" needs a fresh passkey sign-in: sign in with your passkey in the dashboard, then run this again")
	}
	return err
}

// permissionsDenyCommands is `onemind permissions deny` (PR 8): a per-principal "never" the gateway
// checks before any rule could say yes. Adding one only tightens (owner, or the person who owns
// that agent); removing one loosens (owner only, with a passkey).
func permissionsDenyCommands(a *App) *cobra.Command {
	root := &cobra.Command{Use: "deny", Short: "Deny rules: a principal may never have a type (or tier) approved without you"}
	const path = "/v1/approval-denies"
	show := func(d map[string]any) {
		what := fmt.Sprint(d["action_type"])
		if d["action_type"] == nil {
			what = "every " + fmt.Sprint(d["tier"]) + " request"
		}
		fmt.Fprintf(a.Stdout, "%s  %s may never: %s", sanitize(fmt.Sprint(d["id"])), sanitize(fmt.Sprint(d["principal"])), sanitize(what))
		if r, ok := d["reason"].(string); ok && r != "" {
			fmt.Fprintf(a.Stdout, " (%s)", sanitize(r))
		}
		fmt.Fprintln(a.Stdout)
	}
	list := &cobra.Command{Use: "list", Short: "List deny rules (GET " + path + ")", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out []map[string]any
			if err := c.Do(bg(), http.MethodGet, path, nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			if len(out) == 0 {
				fmt.Fprintln(a.Stdout, "No deny rules.")
			}
			for _, d := range out {
				show(d)
			}
			return nil
		}}
	var actionType, tier, reason string
	add := &cobra.Command{Use: "add <principal>", Short: "Refuse a principal one action type (--type) or a whole tier (--tier)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if (actionType == "") == (tier == "") {
				return usageErr(cmd, "name exactly one of --type or --tier")
			}
			body := map[string]any{"principal": args[0]}
			if actionType != "" {
				body["action_type"] = actionType
			} else {
				body["tier"] = tier
			}
			if reason != "" {
				body["reason"] = reason
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			if err := c.Do(bg(), http.MethodPost, path, body, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			show(out)
			return nil
		}}
	add.Flags().StringVar(&actionType, "type", "", "the action type it may never have approved, e.g. app.install")
	add.Flags().StringVar(&tier, "tier", "", "T0 read, T1 write, T2 sensitive, T3 destructive, T4 actuate or P physical")
	add.Flags().StringVar(&reason, "reason", "", "why, for the owner and the audit record")
	remove := &cobra.Command{Use: "remove <deny-id>", Short: "Remove a deny rule (owner only; loosens, so it needs your passkey)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodDelete, path+"/"+url.PathEscape(args[0]), nil, nil); err != nil {
				return stepUpHint(err, "removing a deny rule")
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"removed": args[0]})
			}
			fmt.Fprintf(a.Stdout, "Removed deny rule %s.\n", sanitize(args[0]))
			return nil
		}}
	root.AddCommand(list, add, remove)
	return root
}
