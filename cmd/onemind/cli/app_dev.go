// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"github.com/onemindos/onemindos/cmd/onemind/cli/appmodule"
	"github.com/spf13/cobra"
)

func appDevCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use: "dev", Short: "Run the local SQLite gateway and dashboard together", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return appmodule.Dev(cmd.Context(), ".", a.Stdout, a.Stderr)
		},
	}
}
