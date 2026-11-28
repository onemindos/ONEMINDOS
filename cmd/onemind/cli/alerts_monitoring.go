// SPDX-License-Identifier: Apache-2.0

package cli

// onemind alerts and onemind monitoring.
//
// `alerts`: what the box is telling you needs attention (GET /v1/alerts, POST .../ack, .../resolve,
// .../fix). Acknowledging says "I saw it"; resolving closes one that does not clear by itself. Asking
// for a fix only FILES the fix's request: the CLI never sends the approve shortcut, so a person still
// approves it (in the dashboard or with `onemind actions approve ID`).
//
// `monitoring`: one summary of nodes, apps and open alerts (GET /v1/monitoring/summary). Node history
// is `onemind series`; live use per machine and app is `onemind status --usage`.

import (
	"fmt"
	"io"
	"net/http"

	"github.com/spf13/cobra"
)

func alertsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "alerts", Short: "What needs your attention: list, acknowledge, resolve, request the suggested fix"}
	var state string
	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Alerts (GET /v1/alerts): open ones by default",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/alerts"+query("state", state), func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(v) {
					m := obj(x)
					fix := "-"
					if m["fix"] != nil {
						fix = "yes"
					}
					rows = append(rows, []string{str(m["id"]), str(m["severity"]), str(m["state"]), str(m["title"]), str(m["opened_at"]), fix})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "Nothing needs your attention.")
					return nil
				}
				return table(w, "ID\tSEVERITY\tSTATE\tTITLE\tOPENED\tFIX", rows)
			})
		},
	})
	root.Commands()[0].Flags().StringVar(&state, "state", "open", "open (includes acknowledged), acknowledged or resolved; comma for more")
	root.AddCommand(&cobra.Command{
		Use:   "show ALERT_ID",
		Short: "One alert in full (GET /v1/alerts/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/alerts/"+pathID(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				pairs := [][2]string{{"id", str(m["id"])}, {"severity", str(m["severity"])}, {"state", str(m["state"])}, {"title", str(m["title"])},
					{"what happened", dash(str(m["body"]))}, {"opened", str(m["opened_at"])}, {"times", jnum(m["occurrences"])}, {"more help", dash(str(m["learn_more_url"]))}}
				if f := obj(m["fix"]); len(f) > 0 {
					pairs = append(pairs, [2]string{"suggested fix (a request, approved by a person)", str(f["type"])})
				}
				return kv(w, pairs)
			})
		},
	})
	post := func(use, short, suffix, done string) *cobra.Command {
		return &cobra.Command{
			Use:   use + " ALERT_ID",
			Short: short,
			Args:  cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				v, err := a.gwDo(http.MethodPost, "/v1/alerts/"+pathID(args[0])+suffix, nil)
				if err != nil {
					return err
				}
				return a.printDone(v, done, args[0])
			},
		}
	}
	var reason string
	fix := &cobra.Command{
		Use:   "fix ALERT_ID",
		Short: "Request the alert's suggested fix (POST /v1/alerts/ID/fix); a person approves it",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			body := map[string]any{}
			if reason != "" {
				body["reason"] = reason
			}
			return a.requestWrite("the fix for alert "+args[0], http.MethodPost, "/v1/alerts/"+pathID(args[0])+"/fix", body)
		},
	}
	fix.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")
	root.AddCommand(post("ack", "Say you have seen it (POST /v1/alerts/ID/ack); owners and adults", "/ack", "Acknowledged %s."),
		post("resolve", "Close an alert that does not clear by itself (POST /v1/alerts/ID/resolve); owner only", "/resolve", "Resolved %s."), fix)
	return []*cobra.Command{root}
}

func monitoringCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "monitoring", Short: "The box at a glance: machines, apps and open alerts"}
	root.AddCommand(&cobra.Command{
		Use:   "summary",
		Short: "Counts of machines, apps and open alerts (GET /v1/monitoring/summary)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/monitoring/summary", func(w io.Writer, v any) error {
				m := obj(v)
				n, ap, al := obj(m["nodes"]), obj(m["apps"]), obj(m["open_alerts"])
				pairs := [][2]string{
					{"machines", fmt.Sprintf("%s online, %s stale, %s offline", jnum(n["online"]), jnum(n["stale"]), jnum(n["offline"]))},
					{"apps", fmt.Sprintf("%s healthy, %s unhealthy, %s starting, %s stopped, %s unknown", jnum(ap["healthy"]), jnum(ap["unhealthy"]), jnum(ap["starting"]), jnum(ap["stopped"]), jnum(ap["unknown"]))},
					{"open alerts", fmt.Sprintf("%s critical, %s warning, %s info", jnum(al["critical"]), jnum(al["warning"]), jnum(al["info"]))},
				}
				for _, s := range list(m["storage"]) {
					pairs = append(pairs, [2]string{"storage on " + str(obj(s)["node_id"]), dash(str(obj(s)["state"]))})
				}
				pairs = append(pairs, [2]string{"as of", dash(str(m["at"]))})
				return kv(w, pairs)
			})
		},
	})
	return []*cobra.Command{root}
}

func init() { groups = append(groups, alertsCommands, monitoringCommands) }
