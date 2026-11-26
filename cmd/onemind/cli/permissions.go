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
	root.AddCommand(permissionsDenyCommands(a), permissionsRulesCommands(a))
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

// permissionsRulesCommands is `onemind permissions rules` (PR 9): the owner's standing approvals.
// Revoking is one step and needs no passkey (it only narrows); narrowing applies at once; anything
// that widens a rule is done in the dashboard, where the passkey binds the change.
func permissionsRulesCommands(a *App) *cobra.Command {
	root := &cobra.Command{Use: "rules", Short: "Standing approvals: list, revoke, narrow, re-confirm, keep"}
	const path = "/v1/approval-policies"
	line := func(p map[string]any) {
		life := "until " + fmt.Sprint(p["expires_at"])
		if f, _ := p["forever"].(bool); f {
			life = "FOREVER"
		}
		allow, _ := p["allow"].(map[string]any)
		fmt.Fprintf(a.Stdout, "%s  rev %v  %s  %s may %s  %s", sanitize(fmt.Sprint(p["id"])), p["revision"], sanitize(fmt.Sprint(p["state"])),
			sanitize(joinAny(allow["requested_by"])), sanitize(joinAny(allow["types"])), sanitize(life))
		if r, ok := p["suspended_reason"].(string); ok && r != "" {
			fmt.Fprintf(a.Stdout, "  (suspended: %s)", sanitize(r))
		}
		if d, _ := p["review_due"].(bool); d {
			fmt.Fprint(a.Stdout, "  (review due)")
		}
		fmt.Fprintln(a.Stdout)
	}
	call := func(method, p string, body any) (map[string]any, error) {
		c, _, err := a.client()
		if err != nil {
			return nil, err
		}
		var out map[string]any
		return out, c.Do(bg(), method, p, body, &out)
	}
	print1 := func(out map[string]any, err error, what string) error {
		if err != nil {
			return stepUpHint(err, what)
		}
		if a.G.JSON {
			return printJSON(a.Stdout, out)
		}
		line(out)
		return nil
	}
	list := &cobra.Command{Use: "list", Short: "List standing approvals (forever rules first)", Args: cobra.NoArgs,
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
				fmt.Fprintln(a.Stdout, "No standing approvals.")
			}
			for _, forever := range []bool{true, false} {
				for _, p := range out {
					if f, _ := p["forever"].(bool); f == forever {
						line(p)
					}
				}
			}
			return nil
		}}
	one := func(use, short, suffix, what string) *cobra.Command {
		return &cobra.Command{Use: use + " <rule-id>", Short: short, Args: cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				out, err := call(http.MethodPost, path+"/"+url.PathEscape(args[0])+"/"+suffix, nil)
				return print1(out, err, what)
			}}
	}
	var perDay, maxUses int
	var expires string
	narrow := &cobra.Command{Use: "narrow <rule-id>", Short: "Narrow a rule now (lower --per-day or --max-uses, earlier --expires)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			body := map[string]any{}
			limits := map[string]any{}
			if perDay > 0 {
				limits["per_day"] = perDay
			}
			if maxUses > 0 {
				limits["max_uses"] = maxUses
			}
			if expires != "" {
				body["expires_at"] = expires
			}
			if len(limits) == 0 && len(body) == 0 {
				return usageErr(cmd, "say what to narrow: --per-day, --max-uses or --expires")
			}
			if len(limits) > 0 {
				body["limits"] = limits // the gateway keeps the limits left out
			}
			out, err := call(http.MethodPatch, path+"/"+url.PathEscape(args[0]), body)
			return print1(out, err, "this change widens the rule, so it")
		}}
	narrow.Flags().IntVar(&perDay, "per-day", 0, "a lower number of uses per 24 hours")
	narrow.Flags().IntVar(&maxUses, "max-uses", 0, "end the rule after this many uses in total")
	narrow.Flags().StringVar(&expires, "expires", "", "an earlier end, RFC 3339 (e.g. 2026-12-31T00:00:00Z)")
	root.AddCommand(list,
		one("revoke", "End a rule now (one step; no passkey needed)", "revoke", "revoking"),
		one("reconfirm", "Re-confirm a suspended rule after its agent changed (owner; passkey)", "reconfirm", "re-confirming a rule"),
		one("keep", "Keep a forever rule at its 90-day review", "keep", "keeping a rule"),
		narrow)
	return root
}
