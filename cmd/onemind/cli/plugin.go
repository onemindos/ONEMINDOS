// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/spf13/cobra"
)

func pluginCommands(a *App) []*cobra.Command {
	plugin := &cobra.Command{Use: "plugin", Short: "Develop plugins (local, offline checks)"}
	plugin.AddCommand(&cobra.Command{
		Use: "validate [dir]", Short: "Validate a tool plugin manifest (does not verify artifacts)", Args: cobra.MaximumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			dir := "."
			if len(args) > 0 {
				dir = args[0]
			}
			path := filepath.Join(dir, "onemind.app.yaml")
			info, err := os.Lstat(path)
			if err != nil {
				return err
			}
			if !info.Mode().IsRegular() {
				return fmt.Errorf("manifest must be a regular file")
			}
			f, err := os.Open(path)
			if err != nil {
				return err
			}
			defer f.Close()
			data, err := io.ReadAll(io.LimitReader(f, validate.MaxManifestBytes+1))
			if err != nil {
				return err
			}
			if err = validate.Manifest(data); err != nil {
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
