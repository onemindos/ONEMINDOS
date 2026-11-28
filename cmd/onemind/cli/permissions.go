// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// permissionsCommands is `onemind permissions` (gateway permissions design §3.12): how the gateway
// decides who may do what without asking. The CLI reads and requests; every change it sends is the
// signed-in person's own, checked by the gateway (owner only where it loosens anything).
func permissionsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "permissions", Short: "Deny rules, standing approvals and modes: what may happen without asking"}
	root.AddCommand(permissionsDenyCommands(a), permissionsRulesCommands(a), permissionsModeCommands(a), permissionsLogCommand(a))
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

func (a *App) printPendingPermission(out map[string]any) bool {
	if out["state"] != "awaiting_approval" || out["requested_by"] == nil {
		return false
	}
	fmt.Fprintf(a.Stdout, "Request %s is waiting in Approvals.\n", sanitize(fmt.Sprint(out["id"])))
	return true
}

// permissionsDenyCommands is `onemind permissions deny` (PR 8): a per-principal "never" the gateway
// checks before any rule could say yes. Adding one only tightens (owner, or the person who owns
// that agent). Removing one goes to the owner's approval queue.
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
			if err := c.Do(bg(), http.MethodPost, "/v1/approval-denies", body, &out); err != nil {
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
	remove := &cobra.Command{Use: "remove <deny-id>", Short: "Request approval to remove a deny rule (owner only)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			if err := c.Do(bg(), http.MethodDelete, "/v1/approval-denies/"+url.PathEscape(args[0]), nil, &out); err != nil {
				return stepUpHint(err, "removing a deny rule")
			}
			if out != nil {
				if a.G.JSON {
					return printJSON(a.Stdout, out)
				}
				if a.printPendingPermission(out) {
					return nil
				}
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
// Revoking and narrowing apply at once. Widening requests the owner's approval.
func permissionsRulesCommands(a *App) *cobra.Command {
	root := &cobra.Command{Use: "rules", Short: "Standing approvals: list, revoke, narrow, confirm, re-confirm, keep"}
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
		err = c.Do(bg(), method, p, body, &out)
		return out, err
	}
	print1 := func(out map[string]any, err error, what string) error {
		if err != nil {
			return stepUpHint(err, what)
		}
		if a.G.JSON {
			return printJSON(a.Stdout, out)
		}
		if a.printPendingPermission(out) {
			return nil
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
	one := func(use, short, what string, send func(string) (map[string]any, error)) *cobra.Command {
		return &cobra.Command{Use: use + " <rule-id>", Short: short, Args: cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				out, err := send(url.PathEscape(args[0]))
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
			out, err := call(http.MethodPatch, "/v1/approval-policies/"+url.PathEscape(args[0]), body)
			return print1(out, err, "this change widens the rule, so it")
		}}
	narrow.Flags().IntVar(&perDay, "per-day", 0, "a lower number of uses per 24 hours")
	narrow.Flags().IntVar(&maxUses, "max-uses", 0, "end the rule after this many uses in total")
	narrow.Flags().StringVar(&expires, "expires", "", "an earlier end, RFC 3339 (e.g. 2026-12-31T00:00:00Z)")
	show := &cobra.Command{Use: "show <rule-id>", Short: "One rule: its limits, uses, notices and history (revisions, suspensions, revoke)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var all []map[string]any
			if err := c.Do(bg(), http.MethodGet, path, nil, &all); err != nil {
				return err
			}
			var rule map[string]any
			for _, p := range all {
				if p["id"] == args[0] {
					rule = p
				}
			}
			if rule == nil {
				return exitWith(ExitNotFound, "not_found", "no standing approval "+args[0])
			}
			hist, err := ruleHistory(c, rule)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"rule": rule, "history": hist})
			}
			line(rule)
			limits, _ := rule["limits"].(map[string]any)
			fmt.Fprintf(a.Stdout, "  per day %v, max uses %v, uses %v (%v in 24 h), notices %v, lapse if unused %v days\n",
				limits["per_day"], orDash(limits["max_uses"]), rule["uses"], rule["uses_24h"], rule["notify_after"], orDash(rule["lapse_unused_days"]))
			for _, h := range hist {
				d, _ := h["data"].(map[string]any)
				fmt.Fprintf(a.Stdout, "  %s  %s", sanitize(fmt.Sprint(h["ts"])), sanitize(fmt.Sprint(h["event"])))
				if rev, ok := d["revision"]; ok {
					fmt.Fprintf(a.Stdout, " rev %v", rev)
				}
				if why, ok := d["reason"].(string); ok {
					fmt.Fprintf(a.Stdout, " (%s)", sanitize(why))
				}
				fmt.Fprintln(a.Stdout)
			}
			return nil
		}}
	var only string
	revokeAll := &cobra.Command{Use: "revoke-all", Short: "End every rule, or every rule naming one principal (--principal); no passkey needed", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			body := map[string]any{"principal": nil}
			if only != "" {
				body["principal"] = only
			}
			out, err := call(http.MethodPost, "/v1/approval-policies/revoke-all", body)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			ids, _ := out["revoked"].([]any)
			fmt.Fprintf(a.Stdout, "Revoked %d rule(s). %s\n", len(ids), sanitize(joinAny(out["revoked"])))
			return nil
		}}
	revokeAll.Flags().StringVar(&only, "principal", "", "only rules naming this principal, e.g. agent:notes-helper")
	root.AddCommand(list, show, revokeAll,
		one("revoke", "End a rule now (one step; no passkey needed)", "revoking", func(id string) (map[string]any, error) {
			return call(http.MethodPost, "/v1/approval-policies/"+id+"/revoke", nil)
		}),
		one("confirm", "Confirm a paused rule (owner only)", "confirming a rule", func(id string) (map[string]any, error) {
			return call(http.MethodPost, "/v1/approval-policies/"+id+"/confirm", nil)
		}),
		one("reconfirm", "Re-confirm a suspended rule after its agent changed (owner only)", "re-confirming a rule", func(id string) (map[string]any, error) {
			return call(http.MethodPost, "/v1/approval-policies/"+id+"/reconfirm", nil)
		}),
		one("keep", "Keep a forever rule at its 90-day review", "keeping a rule", func(id string) (map[string]any, error) {
			return call(http.MethodPost, "/v1/approval-policies/"+id+"/keep", nil)
		}),
		narrow)
	return root
}

// permissionsModeCommands is `onemind permissions mode` (PR 10): how a principal's requests are handled.
// Tightening (toward locked) is anyone with a say over that agent; loosening is the owner, with a passkey,
// and never before the owner has one (F-8). "default" names the household default (Always ask).
func permissionsModeCommands(a *App) *cobra.Command {
	root := &cobra.Command{Use: "mode", Short: "Permission modes: locked, ask, remember, auto, headless"}
	const path = "/v1/permission-modes"
	names := map[string]string{"locked": "Locked", "ask": "Always ask", "remember": "Ask once, then remember",
		"auto": "Auto within rules", "headless": "Headless", "bypass": "Bypass in a sandbox"}
	show := func(m map[string]any) {
		who := fmt.Sprint(m["principal"])
		if who == "*" {
			who = "household default"
		}
		label := names[fmt.Sprint(m["mode"])]
		if label == "" {
			label = fmt.Sprint(m["mode"])
		}
		fmt.Fprintf(a.Stdout, "%s: %s", sanitize(who), sanitize(label))
		if own, _ := m["own"].(bool); !own && m["principal"] != "*" &&
			(m["household_default"] == nil || m["mode"] == m["household_default"]) {
			fmt.Fprint(a.Stdout, " (household default)")
		}
		fmt.Fprintln(a.Stdout)
		if pk, ok := m["owner_passkey"].(bool); ok && !pk {
			fmt.Fprintln(a.Stdout, "No owner passkey yet: every mode behaves as Always ask, and nothing can be loosened (F-8).")
		}
	}
	get := &cobra.Command{Use: "get <principal|default>", Short: "Show a principal's mode (an agent may read its own)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			if err := c.Do(bg(), http.MethodGet, path+"/"+url.PathEscape(args[0]), nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			show(out)
			return nil
		}}
	list := &cobra.Command{Use: "list", Short: "The household default and every principal with its own mode", Args: cobra.NoArgs,
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
			for _, m := range out {
				show(m)
			}
			return nil
		}}
	var reason string
	set := &cobra.Command{Use: "set <principal|default> <locked|ask|remember|auto|headless>", Short: "Set a mode (loosening requires the owner's approval)", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			if _, ok := names[args[1]]; !ok {
				return usageErr(cmd, "mode is one of locked, ask, remember, auto, headless")
			}
			body := map[string]any{"mode": args[1]}
			if reason != "" {
				body["reason"] = reason
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			if args[0] == "default" {
				err = c.Do(bg(), http.MethodPut, "/v1/permission-modes", body, &out)
			} else {
				err = c.Do(bg(), http.MethodPut, "/v1/permission-modes/"+url.PathEscape(args[0]), body, &out)
			}
			if err != nil {
				var ge *onemind.Error
				if errors.As(err, &ge) && ge.Reason == "no_owner_passkey" {
					return exitWith(ExitUsage, "usage", "add a passkey first: nothing is loosened before the owner has one (Settings, Security, Sign-in keys)")
				}
				return stepUpHint(err, "loosening a mode")
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			if a.printPendingPermission(out) {
				return nil
			}
			show(out)
			return nil
		}}
	set.Flags().StringVar(&reason, "reason", "", "why, for the audit record")
	root.AddCommand(get, list, set)
	return root
}

func orDash(v any) any {
	if v == nil {
		return "-"
	}
	return v
}

// ruleHistory reads a rule's audit lines (created, revisions, suspensions, re-confirm, revoke) since it was
// made, at most five pages of 500.
func ruleHistory(c *onemind.Client, rule map[string]any) ([]map[string]any, error) {
	since := fmt.Sprint(rule["created_at"])
	if t, err := time.Parse(time.RFC3339, since); err == nil {
		since = t.Add(-time.Second).UTC().Format(time.RFC3339)
	}
	out := []map[string]any{}
	err := auditPages(c, url.Values{"event": {"automation.policy.created,approval.policy.*"}, "since": {since}}, 5, func(r map[string]any) {
		if d, _ := r["data"].(map[string]any); d != nil && d["policy_id"] == rule["id"] {
			out = append(out, r)
		}
	})
	return out, err
}

// auditPages reads GET /v1/audit/events with query q, oldest first, in pages of 500 (at most `pages` of
// them), and hands every line to each. Both `permissions rules show` and `permissions log` page with it.
func auditPages(c *onemind.Client, q url.Values, pages int, each func(map[string]any)) error {
	q.Set("limit", "500")
	for page := 0; page < pages; page++ {
		var recs []map[string]any
		if err := c.Do(bg(), http.MethodGet, "/v1/audit/events?"+q.Encode(), nil, &recs); err != nil {
			return err
		}
		for _, r := range recs {
			each(r)
		}
		if len(recs) < 500 {
			return nil
		}
		after := seqCursor(recs[len(recs)-1]["seq"])
		if after == "" {
			return nil // a line with no usable seq: stop rather than ask for the same page again
		}
		q.Set("after_seq", after)
	}
	return nil
}

// seqCursor is an audit line's seq as the integer the gateway's after_seq expects. JSON numbers decode
// as float64, and fmt.Sprint prints a float64 of a million or more as 1e+06, which the gateway refuses
// (422); this always gives plain digits. It is "" for a missing or non-integer seq.
func seqCursor(v any) string {
	switch n := v.(type) {
	case float64:
		if n < 0 || n != math.Trunc(n) || n > math.MaxInt64 {
			return ""
		}
		return strconv.FormatInt(int64(n), 10)
	case json.Number:
		if _, err := strconv.ParseInt(string(n), 10, 64); err == nil {
			return string(n)
		}
	case int:
		return strconv.Itoa(n)
	case int64:
		return strconv.FormatInt(n, 10)
	}
	return ""
}

// permissionsLogCommand is `onemind permissions log` (design §3.12 "Auto-approved log"): every request a
// standing approval approved in the last --days days, newest first, read from the audit log
// (action.approved lines with approved_via=policy). End a rule with `onemind permissions rules revoke`.
func permissionsLogCommand(a *App) *cobra.Command {
	var days int
	cmd := &cobra.Command{Use: "log", Short: "What your rules approved without asking (newest first)", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if days < 1 || days > 365 {
				return usageErr(cmd, "--days is 1 to 365")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			since := time.Now().UTC().Add(-time.Duration(days) * 24 * time.Hour).Format(time.RFC3339)
			out := []map[string]any{}
			err = auditPages(c, url.Values{"event": {"action.approved"}, "since": {since}}, 10, func(r map[string]any) {
				if d, _ := r["data"].(map[string]any); d != nil && d["approved_via"] == "policy" {
					out = append(out, map[string]any{"ts": r["ts"], "action_id": r["action_id"], "type": d["type"],
						"requested_by": d["requested_by"], "policy_id": d["policy_id"], "policy_revision": d["policy_revision"], "uses": d["uses"]})
				}
			})
			if err != nil {
				return err
			}
			for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
				out[i], out[j] = out[j], out[i]
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			if len(out) == 0 {
				fmt.Fprintf(a.Stdout, "Nothing was approved by a rule in the last %d days.\n", days)
			}
			for _, u := range out {
				fmt.Fprintf(a.Stdout, "%s  %s  by %s  rule %s rev %v  (use %v)\n", sanitize(fmt.Sprint(u["ts"])), sanitize(fmt.Sprint(u["type"])),
					sanitize(fmt.Sprint(u["requested_by"])), sanitize(fmt.Sprint(u["policy_id"])), u["policy_revision"], sanitize(fmt.Sprint(u["uses"])))
			}
			return nil
		}}
	cmd.Flags().IntVar(&days, "days", 30, "how many days back")
	return cmd
}
