// SPDX-License-Identifier: Apache-2.0
package cli

import (
	"context"
	"fmt"
	"github.com/onemindos/onemindos/internal/backup/localsnapshot"
	"github.com/spf13/cobra"
	"time"
)

func snapshotCommands(a *App) []*cobra.Command {
	var path string
	cmd := &cobra.Command{Use: "snapshots", Short: "List local btrfs versions on this box (administrator only)", Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			c, err := localsnapshot.Load(path)
			if err != nil {
				return err
			}
			ctx, cancel := context.WithTimeout(context.Background(), a.G.Timeout)
			defer cancel()
			v, err := (localsnapshot.Manager{Config: c}).List(ctx)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			fmt.Fprintln(a.Stdout, "Local snapshots share this disk; manage off-box backups on the Backups page.")
			for _, item := range v {
				fmt.Fprintf(a.Stdout, "%s\t%s\n", item.ID, item.TakenAt.Format(time.RFC3339))
			}
			return nil
		}}
	cmd.Flags().StringVar(&path, "snapshot-config", localsnapshot.DefaultConfig, "local administrator configuration")
	return []*cobra.Command{cmd}
}
