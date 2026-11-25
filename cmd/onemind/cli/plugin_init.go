// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"path/filepath"

	"github.com/onemindos/onemindos/internal/plugin/scaffold"
	"github.com/spf13/cobra"
)

func pluginInitCommand(a *App) *cobra.Command {
	var id, template, source string
	command := &cobra.Command{Use: "init <directory>", Short: "Create a local declarative plugin", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if id == "" {
				id = filepath.Base(filepath.Clean(args[0]))
			}
			if err := scaffold.Create(args[0], id, template, source); err != nil {
				return exitWith(ExitUsage, "scaffold_failed", err.Error())
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"created": true, "id": id, "template": template})
			}
			fmt.Fprintf(a.Stdout, "Created %s (%s). Run onemind plugin validate %s.\n", id, template, args[0])
			return nil
		},
	}
	command.Flags().StringVar(&id, "id", "", "plugin DNS-label id (default: directory name)")
	command.Flags().StringVar(&template, "template", "settings", "local source template: settings")
	command.Flags().StringVar(&source, "source", "", "HTTPS source repository URL (required)")
	_ = command.MarkFlagRequired("source")
	return command
}
