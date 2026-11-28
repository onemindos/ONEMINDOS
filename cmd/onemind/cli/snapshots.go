// SPDX-License-Identifier: Apache-2.0
package cli

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type localSnapshot struct {
	ID      string    `json:"id"`
	Cadence string    `json:"cadence"`
	TakenAt time.Time `json:"taken_at"`
}

func snapshotCommands(a *App) []*cobra.Command {
	cmd := &cobra.Command{Use: "snapshots", Short: "List this box's Snapper timeline (administrator only)", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			ctx, cancel := context.WithTimeout(cmd.Context(), a.G.Timeout)
			defer cancel()
			out, err := exec.CommandContext(ctx, "snapper", "--no-dbus", "--utc", "--iso", "--jsonout", "-c", "storage",
				"list", "--columns", "number,type,date,cleanup,read-only").Output()
			if err != nil {
				if e, ok := err.(*exec.ExitError); ok && len(e.Stderr) > 0 {
					return fmt.Errorf("Snapper storage history: %s", strings.TrimSpace(string(e.Stderr)))
				}
				return fmt.Errorf("Snapper storage history: %w", err)
			}
			var configs map[string][]struct {
				Number   uint32 `json:"number"`
				Type     string `json:"type"`
				Date     string `json:"date"`
				Cleanup  string `json:"cleanup"`
				ReadOnly bool   `json:"read-only"`
			}
			if err := json.Unmarshal(out, &configs); err != nil {
				return fmt.Errorf("decode Snapper storage history: %w", err)
			}
			rows, ok := configs["storage"]
			if !ok {
				return fmt.Errorf("Snapper did not return the storage timeline")
			}
			versions := []localSnapshot{}
			for _, row := range rows {
				if row.Number == 0 || row.Type != "single" || row.Cleanup != "timeline" || !row.ReadOnly {
					continue
				}
				taken, err := time.Parse(time.DateTime, row.Date)
				if err != nil {
					return fmt.Errorf("invalid date for Snapper snapshot %d: %w", row.Number, err)
				}
				versions = append(versions, localSnapshot{
					ID:      fmt.Sprintf("snapper-%d-%s", row.Number, taken.Format("20060102T150405Z")),
					Cadence: "timeline", TakenAt: taken,
				})
			}
			sort.SliceStable(versions, func(i, j int) bool { return versions[i].TakenAt.After(versions[j].TakenAt) })
			if a.G.JSON {
				return printJSON(a.Stdout, versions)
			}
			fmt.Fprintln(a.Stdout, "Local snapshots share this disk. Use Backups for off-box copies.")
			for _, item := range versions {
				fmt.Fprintf(a.Stdout, "%s\t%s\n", item.ID, item.TakenAt.Format(time.RFC3339))
			}
			return nil
		}}
	return []*cobra.Command{cmd}
}
