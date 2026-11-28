// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// networkCommands are `onemind network show|set|dhcp|confirm`. show reads the box's network (gateway_admin.go);
// set, dhcp and confirm (P-08) change a wired interface's fixed IPv4 address and DNS, or go back to DHCP, with an
// automatic way back. One group: two top-level "network" commands would hide one of them.
//
// set and dhcp only ASK (PUT /v1/network/{iface} files a network.configure action): an owner approves it with
// a passkey in the dashboard or the phone app, the box applies it, and the owner then has a few minutes to reach
// the box at the NEW address and confirm. confirm keeps it (POST /v1/network/{iface}/confirm); without it the box
// goes back to its old settings by itself, so a wrong address never strands anyone. The CLI never approves.
func networkCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "network", Short: "This box's network: show it; change a wired interface (fixed address and DNS, or DHCP) with automatic rollback (owner)"}

	var address, gateway, reason string
	var dns []string
	var rollback int
	set := &cobra.Command{
		Use:   "set IFACE --address CIDR --gateway IP [--dns IP]...",
		Short: "Ask for a fixed IPv4 address, gateway and DNS on a cable interface; prints the approval id",
		Example: "  onemind network set eth0 --address 192.0.2.20/24 --gateway 192.0.2.1 --dns 192.0.2.1\n" +
			"  # after passkey approval and verifying the dashboard at the new address:\n" +
			"  onemind network confirm eth0 APPROVAL_ID --verified-reachable",
		Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if address == "" || gateway == "" {
				return exitWith(ExitUsage, "usage", "network set needs --address (like 192.0.2.20/24) and --gateway; to use the router's address instead, run: onemind network dhcp "+sanitize(args[0]))
			}
			body := map[string]any{"mode": "static", "address": address, "gateway": gateway}
			if len(dns) > 0 { // a nil slice would go out as "dns": null, which the gateway refuses (422)
				body["dns"] = dns
			}
			return a.networkRequest(args[0], body, rollback, reason, address)
		},
	}
	set.Flags().StringVar(&address, "address", "", "IPv4 address with its prefix, like 192.0.2.20/24")
	set.Flags().StringVar(&gateway, "gateway", "", "the router's IPv4 address, inside the same subnet")
	set.Flags().StringSliceVar(&dns, "dns", nil, "a DNS server (repeat or comma-separate, at most three)")

	dhcp := &cobra.Command{
		Use:   "dhcp IFACE",
		Short: "Ask to go back to an automatic (DHCP) address; clears the fixed address, gateway and DNS",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.networkRequest(args[0], map[string]any{"mode": "dhcp"}, rollback, reason, "")
		},
	}
	for _, c := range []*cobra.Command{set, dhcp} {
		c.Flags().IntVar(&rollback, "rollback-seconds", 120, "how long you have to confirm from the new address before the old settings return (10-600)")
		c.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	}

	var verified bool
	confirm := &cobra.Command{
		Use:   "confirm IFACE APPROVAL_ID --verified-reachable",
		Short: "Keep an approved change after verifying the new address",
		Long: "From another device on the wired network, open the dashboard directly at the changed interface's IPv4 address. " +
			"For DHCP, find that address in the router. Sign in and verify that this box's Network page loads before confirming.",
		Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			if !verified {
				return exitWith(ExitUsage, "usage", "verify that the dashboard's Network page loads at the new IPv4 address, then use --verified-reachable")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			body := map[string]any{"action_id": args[1], "verified_reachable": verified}
			if err := c.Do(bg(), http.MethodPost, "/v1/network/"+url.PathEscape(args[0])+"/confirm", body, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			if !a.G.Quiet {
				fmt.Fprintf(a.Stdout, "Confirmed: the change to %s stays.\n", sanitize(args[0]))
			}
			return nil
		},
	}
	confirm.Flags().BoolVar(&verified, "verified-reachable", false, "attest that this box's dashboard loaded at the new address")
	g.AddCommand(networkShowCmd(a), set, dhcp, confirm)
	return []*cobra.Command{g}
}

// networkRequest files the change and says what happens next. It validates nothing itself: the gateway and the
// box refuse an unusable address, and that answer reaches the person word for word.
func (a *App) networkRequest(iface string, body map[string]any, rollback int, reason, address string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	body["rollback_seconds"] = rollback
	body["idempotency_key"] = "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)
	if reason != "" {
		body["reason"] = reason
	}
	var act map[string]any
	if err := c.Do(bg(), http.MethodPut, "/v1/network/"+url.PathEscape(iface), body, &act); err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, act)
	}
	id, _ := act["id"].(string)
	if a.G.Quiet {
		fmt.Fprintln(a.Stdout, sanitize(id))
		return nil
	}
	where := "the address the router gives it"
	if address != "" {
		where = fmt.Sprintf("IPv4 address %s (configured as %s)", strings.SplitN(address, "/", 2)[0], address)
	}
	fmt.Fprintf(a.Stdout, "Change of %s requested. Approval id: %s\n"+
		"An owner approves it with a passkey (dashboard or phone app); follow it with: onemind actions info %s\n"+
		"From another device on the wired network, open the dashboard at %s, sign in, and verify this box's Network page loads.\n"+
		"Then run onemind network confirm %s %s --verified-reachable\n"+
		"You have %d seconds after approval. If you do not confirm, the box goes back to its old settings by itself.\n",
		sanitize(iface), sanitize(id), sanitize(id), sanitize(where), sanitize(iface), sanitize(id), rollback)
	return nil
}
