// SPDX-License-Identifier: Apache-2.0

package cli

// onemind backup: backups over the gateway (/v1/backups/*, /v1/restores). The reads show state. The
// writes (run, verify, restore) only FILE a request that waits for an owner, and a restore also
// needs the owner's passkey when the box has one. The CLI never sends the owner shortcut
// ("approve": true) and never approves; `onemind actions approve ID` is the owner's step.

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
)

func backupCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "backup", Short: "Backups: status, run, verify, restore request (writes wait for an owner)"}

	root.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Is the box backed up? (GET /v1/backups/status)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/backups/status", func(w io.Writer, v any) error {
				m := obj(v)
				pairs := [][2]string{
					{"health", str(m["health"])},
					{"last backup", dash(str(m["last_success_at"]))},
					{"last verified restore", dash(str(m["last_verified_restore_at"]))},
					{"next run", dash(str(m["next_run_at"]))},
					{"copies", str(m["copies"])},
					{"agent", str(m["agent"])},
				}
				if r := str(m["reason"]); r != "" {
					pairs = append(pairs, [2]string{"reason", r})
				}
				if k := str(obj(m["kit"])["state"]); k != "" {
					pairs = append(pairs, [2]string{"emergency kit", k})
				}
				return kv(w, pairs)
			})
		},
	})

	var app, dest, reason string
	run := &cobra.Command{
		Use:   "run",
		Short: "Request a backup now: the whole box, or one app with --app (POST /v1/backups/runs)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			body := map[string]any{"scope": "box"}
			if app != "" {
				body["scope"] = map[string]any{"app_id": app}
			}
			if dest != "" {
				body["destination_id"] = dest
			}
			return a.backupRequest("backup run", "/v1/backups/runs", body, reason, false)
		},
	}
	run.Flags().StringVar(&app, "app", "", "back up only this app")
	run.Flags().StringVar(&dest, "destination", "", "destination id (default: all)")
	run.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")

	var mode string
	verify := &cobra.Command{
		Use:   "verify",
		Short: "Request a restore drill of the latest backup into a scratch area (POST /v1/backups/verify)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if mode != "scratch_restore" && mode != "check" {
				return usageErr(cmd, "--mode must be scratch_restore or check")
			}
			return a.backupRequest("backup verify", "/v1/backups/verify", map[string]any{"mode": mode, "latest": true}, reason, false)
		},
	}
	verify.Flags().StringVar(&mode, "mode", "scratch_restore", "scratch_restore (a real trial restore) or check (repository check only)")
	verify.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")

	snaps := &cobra.Command{
		Use:   "snapshots",
		Short: "The backups that can be restored (GET /v1/backups/snapshots)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			path := "/v1/backups/snapshots"
			if app != "" {
				path += "?app_id=" + url.QueryEscape(app)
			}
			return a.read(path, func(w io.Writer, v any) error {
				var rows [][]string
				for _, s := range list(v) {
					m := obj(s)
					rows = append(rows, []string{str(m["id"]), dash(str(m["taken_at"])), dash(str(m["unit"]))})
				}
				if len(rows) == 0 {
					_, err := fmt.Fprintln(w, "No snapshots yet. They appear after the first backup run (onemind backup run); add a backup destination first if you have none.")
					return err
				}
				return table(w, "SNAPSHOT\tTAKEN\tUNIT", rows)
			})
		},
	}
	snaps.Flags().StringVar(&app, "app", "", "only this app's snapshots")

	var rApp, rPath string
	restore := &cobra.Command{
		Use:   "restore SNAPSHOT_ID --app APP [--path /file/or/folder]",
		Short: "Request a restore in place of one app or one path (POST /v1/restores); a passkey approves it",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if rApp == "" {
				return usageErr(cmd, "--app is required: a whole-box restore runs at set-up on a fresh box, not here")
			}
			scope := map[string]any{"app_id": rApp}
			if rPath != "" {
				if !strings.HasPrefix(rPath, "/") {
					return usageErr(cmd, "--path must be absolute, for example /data/photos")
				}
				scope["path"] = rPath
			}
			return a.backupRequest("restore of "+args[0], "/v1/restores", map[string]any{"snapshot_id": args[0], "scope": scope, "mode": "portable", "target": "in_place"}, reason, true)
		},
	}
	restore.Flags().StringVar(&rApp, "app", "", "the app to restore")
	restore.Flags().StringVar(&rPath, "path", "", "restore only this absolute path inside the app")
	restore.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")

	root.AddCommand(run, verify, snaps, restore, backupVerificationsCommand(a), backupContentCommand(a))
	return []*cobra.Command{root}
}

// backupRequest files one backup request. The gateway answers 202 with the waiting action.
//
// stable chooses the key policy. A restore keeps a key built from what is asked for and the UTC day,
// so repeating it replays the waiting request. A backup run or verify gets a fresh random key per
// invocation: a second backup is a real request, not a replay of this morning's.
func (a *App) backupRequest(what, path string, body map[string]any, reason string, stable bool) error {
	if reason != "" {
		body["reason"] = reason
	}
	// The key names the operation and its target (the path and the body without the free-text reason),
	// so asking twice for the same thing replays the waiting request instead of filing a second one.
	target := map[string]any{}
	for k, v := range body {
		if k != "reason" {
			target[k] = v
		}
	}
	raw, _ := json.Marshal(target) // map keys marshal sorted, so equal requests give equal bytes
	key := freshKey()
	if stable {
		key = idemKey("cli-backup-", path, string(raw))
	}
	v, err := a.gwDoKeyed(http.MethodPost, path, key, body)
	if err != nil {
		return err
	}
	return a.printRequested(what, v)
}
