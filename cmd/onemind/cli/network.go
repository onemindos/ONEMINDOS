// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/spf13/cobra"
)

// networkCommands are `onemind network set|dhcp|confirm` (P-08): a wired interface's fixed IPv4 address and
// DNS, or back to DHCP, with an automatic way back.
//
// set and dhcp only ASK (PUT /v1/network/{iface} files a network.configure action): an owner approves it with
// a passkey in the dashboard or the phone app, the box applies it, and the owner then has a few minutes to reach
// the box at the NEW address and confirm. confirm keeps it (POST /v1/network/{iface}/confirm); without it the box
// goes back to its old settings by itself, so a wrong address never strands anyone. The CLI never approves.
func networkCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "network", Short: "Change a wired interface: fixed address and DNS, or back to DHCP, with automatic rollback (owner)"}

	var address, gateway, reason string
	var dns []string
	var rollback int
	set := &cobra.Command{
		Use:   "set IFACE --address CIDR --gateway IP [--dns IP]...",
		Short: "Ask for a fixed IPv4 address, gateway and DNS on a cable interface; prints the approval id",
		Example: "  onemind network set eth0 --address 192.0.2.20/24 --gateway 192.0.2.1 --dns 192.0.2.1\n" +
			"  # an owner approves with a passkey; then, from the new address:  onemind network confirm eth0",
		Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if address == "" || gateway == "" {
				return exitWith(ExitUsage, "usage", "network set needs --address (like 192.0.2.20/24) and --gateway; to use the router's address instead, run: onemind network dhcp "+sanitize(args[0]))
			}
			body := map[string]any{"mode": "static", "address": address, "gateway": gateway, "dns": dns}
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

	confirm := &cobra.Command{
		Use:   "confirm IFACE",
		Short: "Keep the pending change on this interface: run it from the box's NEW address",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/network/"+url.PathEscape(args[0])+"/confirm", nil, &out); err != nil {
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
	g.AddCommand(set, dhcp, confirm)
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
		where = address
	}
	fmt.Fprintf(a.Stdout, "Change of %s requested. Approval id: %s\n"+
		"An owner approves it with a passkey (dashboard or phone app); follow it with: onemind actions info %s\n"+
		"Then reach the box at %s and run: onemind network confirm %s\n"+
		"You have %d seconds after approval. If you do not confirm, the box goes back to its old settings by itself.\n",
		sanitize(iface), sanitize(id), sanitize(id), sanitize(where), sanitize(iface), rollback)
	return nil
}
