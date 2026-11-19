// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/spf13/cobra"
)

func pluginCommands(a *App) []*cobra.Command {
	plugin := &cobra.Command{Use: "plugin", Short: "Develop plugins (local, offline checks)"}
	var apiLevel string
	validateCommand := &cobra.Command{
		Use: "validate [dir]", Short: "Validate a tool plugin bundle (does not verify signatures)", Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			dir := "."
			if len(args) > 0 {
				dir = args[0]
			}
			var err error
			if cmd.Flags().Changed("api-level") {
				err = validate.DirectoryForAPI(dir, apiLevel)
			} else {
				err = validate.Directory(dir)
			}
			if err != nil {
				return exitWith(ExitVerifyFailed, "validation_failed", err.Error())
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"valid": true})
			}
			fmt.Fprintln(a.Stdout, "Plugin tool manifest valid (artifact verification still required).")
			return nil
		},
	}
	validateCommand.Flags().StringVar(&apiLevel, "api-level", "", "check against this box plugin API level (offline)")
	plugin.AddCommand(validateCommand)
	return []*cobra.Command{plugin}
}
