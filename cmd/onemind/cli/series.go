// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/url"
	"strconv"

	"github.com/spf13/cobra"
)

func seriesCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "series", Short: "Node metric history on the hub"}
	var window, points int
	query := &cobra.Command{
		Use:     "query NODE_ID METRIC",
		Short:   "Print timestamped values for a node metric",
		Long:    "Query cpu_pct, mem_used_mb, mem_total_mb, disk_free_gb, disk_total_gb, temp_c, or load1.",
		Example: "  onemind series query node-1 cpu_pct --window-s 86400 --points 48",
		Args:    cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			q := url.Values{
				"node_id": {args[0]}, "metric": {args[1]},
				"window_s": {strconv.Itoa(window)}, "points": {strconv.Itoa(points)},
			}
			var result any
			if err := c.Do(bg(), http.MethodGet, "/v1/series?"+q.Encode(), nil, &result); err != nil {
				return err
			}
			return printJSON(a.Stdout, result)
		},
	}
	query.Flags().IntVar(&window, "window-s", 86400, "seconds of history, up to 2592000 (30 days)")
	query.Flags().IntVar(&points, "points", 60, "maximum number of averaged points, from 1 to 500")
	root.AddCommand(query)
	return []*cobra.Command{root}
}
