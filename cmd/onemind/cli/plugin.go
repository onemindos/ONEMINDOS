// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/spf13/cobra"
)

func pluginCommands(a *App) []*cobra.Command {
	plugin := &cobra.Command{Use: "plugin", Short: "Develop plugins (local, offline checks)"}
	var previous, apiLevel string
	command := &cobra.Command{
		Use: "validate [dir]", Short: "Validate a plugin bundle (does not verify signatures)", Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			hasPrevious := cmd.Flags().Changed("previous")
			if hasPrevious && strings.TrimSpace(previous) == "" {
				return exitWith(ExitVerifyFailed, "validation_failed", "--previous requires a non-empty directory")
			}
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
			var comparison *validate.GrantDiff
			if hasPrevious {
				before, err := previousManifest(previous)
				if err != nil {
					return exitWith(ExitVerifyFailed, "validation_failed", err.Error())
				}
				data, readErr := previousManifest(dir)
				if readErr != nil {
					return exitWith(ExitVerifyFailed, "validation_failed", readErr.Error())
				}
				comparison, err = validate.Compare(before, data)
				if err != nil {
					return exitWith(ExitVerifyFailed, "validation_failed", err.Error())
				}
			}
			if a.G.JSON {
				if comparison != nil {
					return printJSON(a.Stdout, map[string]any{"valid": true, "widens_grants": comparison.WidensGrants, "reasons": comparison.Reasons})
				}
				return printJSON(a.Stdout, map[string]any{"valid": true})
			}
			fmt.Fprintln(a.Stdout, "Plugin bundle valid (artifact verification still required).")
			if comparison != nil {
				fmt.Fprintf(a.Stdout, "widens_grants: %t (informational; owner approval still required)\n", comparison.WidensGrants)
				for _, reason := range comparison.Reasons {
					fmt.Fprintln(a.Stdout, reason)
				}
			}
			return nil
		},
	}
	command.Flags().StringVar(&previous, "previous", "", "compare grants with a previous plugin directory")
	command.Flags().StringVar(&apiLevel, "api-level", "", "check against this box plugin API level (offline)")
	plugin.AddCommand(command, pluginInitCommand(a), pluginPackCommand(a))
	return []*cobra.Command{plugin}
}

func previousManifest(dir string) ([]byte, error) {
	path := filepath.Join(dir, "onemind.app.yaml")
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("previous manifest must be a regular file")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return io.ReadAll(io.LimitReader(f, validate.MaxManifestBytes+1))
}
