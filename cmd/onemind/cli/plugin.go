// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/spf13/cobra"
)

func pluginCommands(a *App) []*cobra.Command {
	plugin := &cobra.Command{Use: "plugin", Short: "Develop plugins (local, offline checks)"}
	plugin.AddCommand(&cobra.Command{
		Use: "validate [dir]", Short: "Validate a tool plugin bundle (does not verify signatures)", Args: cobra.MaximumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			dir := "."
			if len(args) > 0 {
				dir = args[0]
			}
			if err := validate.Directory(dir); err != nil {
				return exitWith(ExitVerifyFailed, "validation_failed", err.Error())
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"valid": true})
			}
			fmt.Fprintln(a.Stdout, "Plugin tool manifest valid (artifact verification still required).")
			return nil
		},
	})
	return []*cobra.Command{plugin}
}
