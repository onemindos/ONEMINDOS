// SPDX-License-Identifier: Apache-2.0

package cli

// onemind backup verifications and onemind backup content: the verification history
// (GET /v1/backups/verifications) and the optional tier for apps' large re-downloadable content
// (GET and POST /v1/backups/content). The reads change nothing. Switching content on or off only
// FILES a request that waits for an owner; switching it on carries the size the person was shown, so
// the gateway refuses it (409) when the content grew since.

import (
	"fmt"
	"io"
	"strconv"

	"github.com/spf13/cobra"
)

func backupVerificationsCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "verifications",
		Short: "Every restore test and repository check, and what it found (GET /v1/backups/verifications)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/backups/verifications", func(w io.Writer, v any) error {
				items := list(v)
				if len(items) == 0 {
					_, err := io.WriteString(w, "No checks yet: a backup is not proven until one passes (onemind backup verify).\n")
					return err
				}
				var rows [][]string
				for _, x := range items {
					m := obj(x)
					mode := "check"
					if str(m["mode"]) == "scratch_restore" {
						mode = "restore test"
					}
					rows = append(rows, []string{str(m["result"]), mode, dash(str(m["unit"])), dash(str(m["snapshot_id"])), dash(str(m["finished_at"]))})
				}
				return table(w, "RESULT\tKIND\tUNIT\tBACKUP\tFINISHED", rows)
			})
		},
	}
}

func backupContentCommand(a *App) *cobra.Command {
	root := &cobra.Command{Use: "content", Short: "Apps' large re-downloadable content: list what it weighs, include or leave out (writes wait for an owner)"}
	root.AddCommand(&cobra.Command{
		Use: "list", Short: "Apps with downloadable content, whether it is backed up, and its size now (GET /v1/backups/content)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/backups/content", func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(v) {
					m := obj(x)
					state := "left out"
					if m["enabled"] == true {
						state = "included"
					}
					rows = append(rows, []string{str(m["app_id"]), state, humanBytes(m["size_bytes"]), dash(str(m["files"]))})
				}
				return table(w, "APP\tIN BACKUPS\tSIZE NOW\tFILES", rows)
			})
		},
	})
	var on, off bool
	var reason string
	set := &cobra.Command{
		Use:   "set APP_ID (--include | --leave-out)",
		Short: "Request including or leaving out an app's downloadable content (POST /v1/backups/content); an owner approves it",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if on == off {
				return usageErr(cmd, "choose exactly one of --include or --leave-out")
			}
			body := map[string]any{"app_id": args[0], "enabled": on}
			if on {
				// Show the size, and send exactly that size: the gateway refuses the request if it changed.
				v, err := a.gwDo("GET", "/v1/backups/content", nil)
				if err != nil {
					return err
				}
				var bytes any
				for _, x := range list(v) {
					if str(obj(x)["app_id"]) == args[0] {
						bytes = obj(x)["size_bytes"]
					}
				}
				n, ok := bytes.(float64)
				if !ok {
					return exitWith(ExitNotFound, "not_found", args[0]+" has no measured downloadable content (see `onemind backup content list`)")
				}
				body["seen_size_bytes"] = int64(n)
				if !a.G.JSON && !a.G.Quiet {
					fmt.Fprintf(a.Stdout, "%s's downloadable content is %s; it will be added to every backup once an owner approves.\n", args[0], humanBytes(bytes))
				}
			}
			what := "leaving out " + args[0] + "'s content"
			if on {
				what = "including " + args[0] + "'s content"
			}
			return a.backupRequest(what, "/v1/backups/content", body, reason, true)
		},
	}
	set.Flags().BoolVar(&on, "include", false, "back this app's downloadable content up")
	set.Flags().BoolVar(&off, "leave-out", false, "stop backing this app's downloadable content up (earlier backups keep theirs)")
	set.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")
	root.AddCommand(set)
	return root
}

func humanBytes(v any) string {
	f, ok := v.(float64)
	if !ok || f < 0 {
		return "not measured"
	}
	units := []string{"bytes", "KB", "MB", "GB", "TB"}
	i := 0
	for f >= 1000 && i < len(units)-1 {
		f /= 1000
		i++
	}
	if i == 0 {
		return strconv.Itoa(int(f)) + " bytes"
	}
	return fmt.Sprintf("%.1f %s", f, units[i])
}
