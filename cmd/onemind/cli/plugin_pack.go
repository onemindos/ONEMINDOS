// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"path/filepath"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/spf13/cobra"
)

func pluginPackCommand(a *App) *cobra.Command {
	var output string
	command := &cobra.Command{Use: "pack [directory]", Short: "Pack a local OCI layout (unsigned)", Args: cobra.MaximumNArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
		directory := "."
		if len(args) > 0 {
			directory = args[0]
		}
		if output == "" {
			absolute, err := filepath.Abs(directory)
			if err != nil {
				return err
			}
			absolute, err = filepath.EvalSymlinks(absolute)
			if err != nil {
				return err
			}
			output = absolute + ".oci"
		}
		digest, err := artifact.Pack(directory, output)
		if err != nil {
			return exitWith(ExitVerifyFailed, "pack_failed", err.Error())
		}
		if output == "" {
			absolute, _ := filepath.Abs(directory)
			output = absolute + ".oci"
		}
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"digest": digest, "layout": output, "verified": false})
		}
		fmt.Fprintf(a.Stdout, "Packed %s\n%s\nUnsigned: publisher verification, scans and approval are still required.\n", output, digest)
		return nil
	}}
	command.Flags().StringVar(&output, "output", "", "new OCI layout directory (default: source path + .oci)")
	return command
}
