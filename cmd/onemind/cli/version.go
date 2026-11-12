// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/version"
	onemind "github.com/onemindos/onemindos/sdk/go"
)

func versionCommands(a *App) []*cobra.Command {
	return []*cobra.Command{{
		Use:   "version",
		Short: "Print the CLI version",
		Args:  cobra.ArbitraryArgs,
		RunE: func(*cobra.Command, []string) error {
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]string{"schema": "onemind.cli.version/v1", "cli": version.Version, "sdk": onemind.Version})
			}
			fmt.Fprintln(a.Stdout, "onemind", version.Version)
			return nil
		},
	}}
}
