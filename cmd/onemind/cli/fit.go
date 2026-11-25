// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
)

func fitCommands(a *App) []*cobra.Command {
	fit := &cobra.Command{Use: "fit", Short: "Read machine fit from the gateway"}
	var nodeID string
	app := &cobra.Command{
		Use:   "app APP_ID",
		Short: "Show which machines can run an app",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var placement onemind.AppPlacement
			if err := c.Do(cmd.Context(), http.MethodGet, "/v1/apps/"+url.PathEscape(args[0])+"/placement", nil, &placement); err != nil {
				return err
			}
			if placement.Fit == nil {
				return exitWith(ExitVerifyFailed, "not_checked", "the gateway did not report machine fit")
			}
			nodes := placement.Fit.Nodes
			if nodeID != "" {
				for _, node := range nodes {
					if node.NodeId == nodeID {
						if a.G.JSON {
							return printJSON(a.Stdout, node)
						}
						return table(a.Stdout, "MACHINE\tVERDICT\tREASONS", [][]string{{node.NodeId, string(node.Verdict), strings.Join(node.Reasons, " ")}})
					}
				}
				return exitWith(ExitNotFound, "node_not_found", fmt.Sprintf("machine %q did not report fit", nodeID))
			}
			if a.G.JSON {
				return printJSON(a.Stdout, placement.Fit)
			}
			rows := make([][]string, 0, len(nodes))
			for _, node := range nodes {
				rows = append(rows, []string{node.NodeId, string(node.Verdict), strings.Join(node.Reasons, " ")})
			}
			return table(a.Stdout, "MACHINE\tVERDICT\tREASONS", rows)
		},
	}
	app.Flags().StringVar(&nodeID, "node", "", "only show this machine")
	fit.AddCommand(app)
	return []*cobra.Command{fit}
}
