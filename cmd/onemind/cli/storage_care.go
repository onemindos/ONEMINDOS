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

// storageCareCommands are `onemind storage trim-status` and `onemind storage eject` (P-10). Both go through the
// hub: the box's host service reads TRIM and the drives, and a drive is removed only after an owner approves the
// action in the dashboard or the phone app. The CLI never approves it, so an agent's token can ask but not run it.
func storageCareCommands(a *App) []*cobra.Command {
	trim := &cobra.Command{
		Use:   "trim-status",
		Short: "When the SSD was last trimmed, when it runs next, smartd warnings and removable drives (owner)",
		Args:  cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var v map[string]any
			if err := c.Do(bg(), http.MethodGet, "/v1/storage/housekeeping", nil, &v); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			if v["available"] != true {
				fmt.Fprintln(a.Stdout, "Not available:", sanitize(careStr(v["message"])))
				return nil
			}
			t, _ := v["trim"].(map[string]any)
			fmt.Fprintf(a.Stdout, "TRIM:       %s\n", trimLine(t))
			fmt.Fprintf(a.Stdout, "Next TRIM:  %s\n", when(t["next_run_at"], "not scheduled"))
			sm, _ := v["smart"].(map[string]any)
			alerts, _ := sm["alerts"].([]any)
			fmt.Fprintf(a.Stdout, "smartd:     %s, %d warning(s)\n", sanitize(careStr(sm["daemon_state"])), len(alerts))
			for _, x := range alerts {
				if m, ok := x.(map[string]any); ok {
					fmt.Fprintf(a.Stdout, "  %s  %s  %s: %s\n", when(m["at"], "?"), sanitize(careStr(m["device"])), sanitize(careStr(m["kind"])), sanitize(careStr(m["message"])))
				}
			}
			drives, _ := v["removable"].([]any)
			if len(drives) == 0 {
				fmt.Fprintln(a.Stdout, "Drives:     none plugged in")
				return nil
			}
			rows := [][]string{}
			for _, x := range drives {
				m, _ := x.(map[string]any)
				state := "can be removed"
				if m["ejectable"] != true {
					state = "in use: " + careStr(m["why_not"])
				}
				size, _ := m["size_bytes"].(float64)
				rows = append(rows, []string{careStr(m["name"]), careStr(m["model"]), careStr(m["label"]), strconv.FormatFloat(size/1e9, 'f', 1, 64) + " GB", state})
			}
			return table(a.Stdout, "DRIVE\tMODEL\tLABEL\tSIZE\tSTATE", rows)
		},
	}

	var reason string
	eject := &cobra.Command{
		Use:   "eject DRIVE",
		Short: "Ask to safely remove a USB drive (sdb or /dev/sdb); prints the approval id an owner approves",
		Args: func(_ *cobra.Command, args []string) error {
			if len(args) != 1 {
				return exitWith(ExitUsage, "usage", "name the drive to remove, for example: onemind storage eject sdb")
			}
			return nil
		},
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			name := strings.TrimPrefix(args[0], "/dev/")
			body := map[string]any{"idempotency_key": "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
			if reason != "" {
				body["reason"] = reason
			}
			var act map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/storage/removable/"+url.PathEscape(name)+"/eject", body, &act); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, act)
			}
			id := careStr(act["id"])
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, sanitize(id))
				return nil
			}
			fmt.Fprintf(a.Stdout, "Removing %s requested. Approval id: %s\nAn owner approves it in the dashboard or the phone app; follow it with: onemind actions info %s\n",
				sanitize(name), sanitize(id), sanitize(id))
			return nil
		},
	}
	eject.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	return []*cobra.Command{trim, eject}
}

func careStr(v any) string { s, _ := v.(string); return s }

func when(v any, none string) string {
	s := careStr(v)
	if s == "" {
		return none
	}
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t.UTC().Format("2006-01-02 15:04 UTC")
	}
	return sanitize(s)
}

func trimLine(t map[string]any) string {
	if t["enabled"] != true {
		return "off (the weekly timer is not enabled)"
	}
	if careStr(t["last_run_at"]) == "" {
		return "has not run on this box yet"
	}
	line := "last ran " + when(t["last_run_at"], "?")
	if r := careStr(t["last_result"]); r != "" && r != "success" {
		line += " (" + sanitize(r) + ")"
	}
	if b, ok := t["last_trimmed_bytes"].(float64); ok {
		line += ", freed " + strconv.FormatFloat(b/(1<<30), 'f', 1, 64) + " GiB"
	}
	return line
}
