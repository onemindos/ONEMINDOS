// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
)

func configCommands(a *App) []*cobra.Command {
	group := &cobra.Command{Use: "config", Short: "Export box settings for private Git"}
	var dir string
	export := &cobra.Command{
		Use:   "export --dir <path>",
		Short: "Write the selected box's secret-free settings as YAML",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if strings.TrimSpace(dir) == "" {
				return usageErr(cmd, "--dir is required")
			}
			return a.exportSettings(cmd.Context(), dir)
		},
	}
	export.Flags().StringVar(&dir, "dir", "", "directory in which to write settings.yaml")
	group.AddCommand(export)
	return []*cobra.Command{group}
}

func (a *App) exportSettings(ctx context.Context, dir string) error {
	client, _, err := a.client()
	if err != nil {
		return err
	}
	var export onemind.ConfigExportView
	if err := client.Do(ctx, http.MethodGet, "/v1/config/export", nil, &export); err != nil {
		return err
	}
	if export.Yaml == "" {
		return fmt.Errorf("gateway returned an empty settings export")
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	path := filepath.Join(dir, "settings.yaml")
	if err := writeFile0600(path, []byte(export.Yaml)); err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, map[string]string{"path": path})
	}
	_, err = fmt.Fprintln(a.Stdout, sanitize(path))
	return err
}
