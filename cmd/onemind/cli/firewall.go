// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// firewallCommands is `onemind firewall`: the box's live firewall in plain words (GET
// /v1/network/firewall, P-09 part 1) and the owner's allow rules with automatic revert (part 2).
//
// show reads. allow only files a request (POST /v1/network/firewall/allow) and prints its approval id: an owner
// approves it with a passkey in the dashboard or the phone app, and the rule is then pending; the box takes it away
// again unless `confirm` keeps it. The CLI never approves anything, so an agent's token can ask but not open a port.
// confirm and remove are the owner's own calls (owner token); removing exposure needs no approval. There is no way to
// name the internet: the scope is lan or mesh.
func firewallCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "firewall", Short: "This box's firewall: what is open, and to whom; ask to open a port to the LAN or mesh"}
	var scope, reason string
	allow := &cobra.Command{
		Use:   "allow PROTO/PORT",
		Short: "Ask to open a port (for example tcp/8123) to your home network or mesh; an owner approves it with a passkey",
		Long: "Files a request to open one port. It does not open anything until an owner approves it with a passkey (dashboard or phone app).\n" +
			"After approval the rule is pending: the box removes it again after a few minutes unless you run `onemind firewall confirm ID`.\n" +
			"The scope is --scope lan (devices on your home network; mesh peers and apps on this box can reach it too) or --scope mesh (your other OneMind machines). The internet is not an option.",
		Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			proto, port, err := parseProtoPort(args[0])
			if err != nil {
				return exitWith(ExitUsage, "usage", err.Error())
			}
			if scope != "lan" && scope != "mesh" {
				return exitWith(ExitUsage, "usage", "--scope must be lan or mesh; the internet is never an option")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			act, err := c.Network.Allow(bg(), proto, port, scope, reason)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, act)
			}
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, sanitize(act.Id))
				return nil
			}
			fmt.Fprintf(a.Stdout, "Request to open %s/%d to the %s filed. Approval id: %s\nAn owner approves it with a passkey (dashboard or phone app). Then keep it with: onemind firewall confirm %s\nUnconfirmed, it closes again by itself.\n",
				proto, port, map[string]string{"lan": "home network", "mesh": "mesh"}[scope], sanitize(act.Id), sanitize(act.Id))
			return nil
		},
	}
	allow.Flags().StringVar(&scope, "scope", "lan", "who may connect: lan (home network) or mesh (your OneMind machines)")
	allow.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	g.AddCommand(allow, &cobra.Command{
		Use:   "confirm ID",
		Short: "Keep a pending allow rule (owner); without it the rule closes again by itself",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Network.ConfirmAllow(bg(), args[0]); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"id": args[0], "state": "confirmed"})
			}
			fmt.Fprintf(a.Stdout, "Rule %s confirmed: it stays open until you remove it.\n", sanitize(args[0]))
			return nil
		},
	}, &cobra.Command{
		Use:   "remove ID",
		Short: "Take an allow rule away, pending or confirmed (owner)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Network.RemoveAllow(bg(), args[0]); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"id": args[0], "removed": true})
			}
			fmt.Fprintf(a.Stdout, "Rule %s removed.\n", sanitize(args[0]))
			return nil
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "What the firewall lets in, each rule in plain words (GET /v1/network/firewall)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := cl.Network.Firewall(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, v); err != nil {
					return err
				}
			}
			if !v.Available {
				return exitWith(ExitUnreachable, "host_unavailable", "firewall: "+sanitize(deref(v.Message)))
			}
			if a.G.JSON {
				return nil
			}
			fmt.Fprintln(a.Stdout, sanitize(deref(v.Headline)))
			fmt.Fprintln(a.Stdout)
			if err := table(a.Stdout, "CHAIN\t#\tACTION\tFROM\tWHAT IT DOES", FirewallRows(v)); err != nil {
				return err
			}
			if rows := AllowRows(v); len(rows) > 0 {
				fmt.Fprintln(a.Stdout)
				if err := table(a.Stdout, "ALLOW RULE ID\tPORT\tFROM\tSTATE", rows); err != nil {
					return err
				}
			}
			if n := derefInt(v.Dropped); n > 0 {
				fmt.Fprintf(a.Stderr, "onemind: warning: %d entr%s left out because the box reported something that did not check out\n", n, map[bool]string{true: "y was", false: "ies were"}[n == 1])
			}
			if n := derefInt(v.Truncated); n > 0 {
				fmt.Fprintf(a.Stderr, "onemind: warning: %d part%s of the rules left out for size; this view is not complete\n", n, map[bool]string{true: "", false: "s"}[n == 1])
			}
			return nil
		},
	})
	return []*cobra.Command{g}
}

// audienceName is the short column text; the long form is in each rule's summary.
var audienceName = map[string]string{
	"this_machine": "this box", "mesh": "mesh", "pod_network": "apps on this box", "lan": "LAN",
	"specific_address": "one address", "one_interface": "one connection", "any_network": "ANY ADDRESS",
}

// FirewallRows is the table: one row per rule, in the order the firewall tries them. Words come from
// the gateway's summary (already checked there); control characters are stripped again here.
func FirewallRows(v *onemind.FirewallView) [][]string {
	rows := [][]string{}
	if v.Rules == nil {
		return rows
	}
	for _, r := range *v.Rules {
		from := audienceName[string(r.Audience)]
		if from == "" {
			from = "unknown"
		}
		rows = append(rows, []string{sanitize(r.Chain), fmt.Sprint(r.Position), strings.ToUpper(sanitize(string(r.Action))), from, sanitize(r.Summary)})
	}
	return rows
}

// parseProtoPort reads "tcp/8123" (the form `open_to_anywhere` uses).
func parseProtoPort(s string) (string, int, error) {
	proto, num, ok := strings.Cut(strings.ToLower(s), "/")
	port, err := strconv.Atoi(num)
	if !ok || (proto != "tcp" && proto != "udp") || err != nil || port < 1 || port > 65535 {
		return "", 0, fmt.Errorf("write the port as tcp/8123 or udp/5353 (1-65535)")
	}
	return proto, port, nil
}

// AllowRows is the owner's allow rules: id, port, who, and whether it is kept or reverts (and when).
func AllowRows(v *onemind.FirewallView) [][]string {
	rows := [][]string{}
	if v.Allow == nil || v.Allow.Rules == nil {
		return rows
	}
	for _, r := range *v.Allow.Rules {
		state := string(r.State)
		if r.State == "pending" && r.ExpiresAt != nil {
			state = "pending, closes " + r.ExpiresAt.Local().Format("15:04:05") + " unless confirmed"
		}
		if r.State == "revert_failed" {
			state = "could not close yet, retrying (remove it with: onemind firewall remove ID)"
		}
		rows = append(rows, []string{sanitize(r.Id), fmt.Sprintf("%s/%d", sanitize(string(r.Proto)), r.Port), map[string]string{"lan": "LAN", "mesh": "mesh"}[string(r.Scope)], state})
	}
	return rows
}
