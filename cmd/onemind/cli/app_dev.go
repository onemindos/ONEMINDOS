// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"github.com/onemindos/onemindos/cmd/onemind/cli/appmodule"
	"github.com/spf13/cobra"
)

func init() { groups = append(groups, moduleCommands) }

func moduleCommands(a *App) []*cobra.Command {
	app := &cobra.Command{Use: "app", Short: "Develop a gateway module in a OneMind source checkout"}
	app.AddCommand(&cobra.Command{
		Use: "dev", Short: "Run the local SQLite gateway and dashboard together", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return appmodule.Dev(cmd.Context(), ".", a.Stdout, a.Stderr)
		},
	})
	app.AddCommand(appTestCommand(a))
	return []*cobra.Command{app}
}
