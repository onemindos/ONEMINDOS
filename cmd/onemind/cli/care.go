// SPDX-License-Identifier: Apache-2.0

package cli

// onemind care: the owner's box check-up (GET /v1/care/checkup). It reads and changes nothing. A
// finding that has a fix names the request to file (for example `onemind backup run`).

import (
	"io"

	"github.com/spf13/cobra"
)

func careCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "care", Short: "Check the box for drift: backups, probes, scans, disks, drills (owner only)"}
	root.AddCommand(&cobra.Command{
		Use:   "checkup",
		Short: "Run the check-up (GET /v1/care/checkup); changes nothing",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/care/checkup", func(w io.Writer, v any) error {
				var rows [][]string
				for _, c := range list(v) {
					m := obj(c)
					fix := ""
					if f := str(m["fix"]); f == "backup.run" {
						fix = "onemind backup run"
					} else if f != "" {
						fix = f
					}
					rows = append(rows, []string{str(m["id"]), str(m["state"]), str(m["detail"]), dash(fix)})
				}
				return table(w, "CHECK\tSTATE\tDETAIL\tFIX", rows)
			})
		},
	})
	return []*cobra.Command{root}
}
