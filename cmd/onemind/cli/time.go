// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/spf13/cobra"
)

// timeCommands are `onemind time status` and `onemind time set-zone ZONE` (P-04).
//
// status reads GET /v1/system/time: the hub's time zone and whether its clock is set from a time server
// (owner only). set-zone files a system.set_timezone action (POST /v1/system/time/zone) and prints its
// id: an owner approves it in the dashboard or the phone app, and the host then applies it. The CLI never
// approves, so an agent's token can ask but not change the box.
func timeCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "time", Short: "The hub's time zone and clock synchronisation"}
	g.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Time zone, whether the clock is synchronised, and the time server (owner)",
		Args:  cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var v map[string]any
			if err := c.Do(bg(), http.MethodGet, "/v1/system/time", nil, &v); err != nil {
				return err
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, v); err != nil {
					return err
				}
			}
			if v["available"] != true {
				msg, _ := v["message"].(string)
				return exitWith(ExitUnreachable, "host_unavailable", "time: "+sanitize(msg))
			}
			if a.G.JSON {
				return nil
			}
			str := func(k string) string { s, _ := v[k].(string); return sanitize(s) }
			zone := str("zone")
			if zone == "" {
				zone = "unknown"
			}
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, zone)
				return nil
			}
			fmt.Fprintf(a.Stdout, "Time zone:   %s\n", zone)
			fmt.Fprintf(a.Stdout, "Hub clock:   %s\n", str("at"))
			fmt.Fprintf(a.Stdout, "Synchronised: %s\n", syncWords(v))
			if s := str("server"); s != "" {
				line := s
				if n, ok := v["stratum"].(float64); ok {
					line += " (stratum " + strconv.Itoa(int(n)) + ")"
				}
				fmt.Fprintf(a.Stdout, "Time server: %s\n", line)
			}
			if t, err := time.Parse(time.RFC3339, str("last_sync_at")); err == nil {
				fmt.Fprintf(a.Stdout, "Last sync:   %s\n", t.UTC().Format(time.RFC3339))
			}
			return nil
		},
	})

	var reason string
	setZone := &cobra.Command{
		Use:   "set-zone ZONE",
		Short: "Ask for a new time zone (e.g. Europe/Berlin); prints the approval id an owner approves",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]any{"zone": args[0], "idempotency_key": "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
			if reason != "" {
				body["reason"] = reason
			}
			var act map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/system/time/zone", body, &act); err != nil {
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
			fmt.Fprintf(a.Stdout, "Time zone %s requested. Approval id: %s\nAn owner approves it in the dashboard or the phone app; follow it with: onemind actions info %s\n",
				sanitize(args[0]), sanitize(id), sanitize(id))
			return nil
		},
	}
	setZone.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	g.AddCommand(setZone)
	return []*cobra.Command{g}
}

// syncWords says what the hub reported, in words; a field the clock did not report is "not reported".
func syncWords(v map[string]any) string {
	switch v["ntp_synchronized"] {
	case true:
		return "yes"
	case false:
		if v["ntp_enabled"] == false {
			return "no (network time is switched off)"
		}
		return "no (no time server reached yet)"
	}
	return "not reported"
}
