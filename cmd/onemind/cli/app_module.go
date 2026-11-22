// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/onemindos/onemindos/cmd/onemind/cli/appmodule"
	"github.com/spf13/cobra"
)

func init() { groups = append(groups, moduleCommands) }

func moduleCommands(a *App) []*cobra.Command {
	app := &cobra.Command{Use: "app", Short: "Develop a gateway module in a OneMind source checkout"}
	var kind string
	newCmd := &cobra.Command{
		Use: "new <id>", Short: "Create a gateway module and its dashboard screen", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if kind != "module" {
				return usageErr(cmd, "supported kind: module")
			}
			if err := appmodule.Create(".", args[0]); err != nil {
				return err
			}
			fmt.Fprintf(a.Stdout, "Created %s. Run onemind app dev, sign in and open /%s.\n", args[0], args[0])
			return nil
		},
	}
	newCmd.Flags().StringVar(&kind, "kind", "module", "kind of app to create")
	app.AddCommand(newCmd, &cobra.Command{
		Use: "dev", Short: "Run the local SQLite gateway and dashboard together", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return appmodule.Dev(cmd.Context(), ".", a.Stdout, a.Stderr)
		},
	})
	return []*cobra.Command{app}
}
