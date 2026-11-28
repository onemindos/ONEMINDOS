// SPDX-License-Identifier: Apache-2.0

package cli

// onemind box-restore: bring one app's data back from another box's backup (new hardware, UMB-P08).
// `candidates` lists what a backup destination holds (read only). `app` only FILES the ordinary backup.restore request,
// never approved by this command: an owner approves it (`onemind actions approve ID`). The recovery key from the kit
// is read from standard input (--recovery-key-stdin), never from a flag, so it does not land in shell history or the
// process list. Both calls are owner only (the gateway answers 403 to anyone else).

import (
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"

	"github.com/spf13/cobra"
)

var destIDRe = regexp.MustCompile(`^dst_[0-9a-f]{16}$`)

func boxRestoreCommands(a *App) []*cobra.Command {
	restore := &cobra.Command{Use: "box-restore", Short: "Restore an app from another box's backup (new hardware); needs its box ID and recovery key (owner)"}

	var dest, box string
	var keyStdin bool
	common := func(c *cobra.Command) {
		c.Flags().StringVar(&dest, "destination", "", "backup destination id (dst_...), from `onemind backup status` or the dashboard")
		c.Flags().StringVar(&box, "box", "", "the old box's ID, from its recovery kit")
		c.Flags().BoolVar(&keyStdin, "recovery-key-stdin", false, "read the recovery key from standard input (required)")
	}
	check := func(cmd *cobra.Command) (string, error) {
		if !destIDRe.MatchString(dest) {
			return "", usageErr(cmd, "--destination must be a backup destination id like dst_0123456789abcdef")
		}
		if strings.TrimSpace(box) == "" {
			return "", usageErr(cmd, "--box is required: the old box's ID from its recovery kit")
		}
		if !keyStdin {
			return "", usageErr(cmd, "--recovery-key-stdin is required: pipe the recovery key in so it never lands in shell history")
		}
		key, err := readSecretLine(a.Stdin)
		if err != nil {
			return "", err
		}
		if len(key) < 32 {
			return "", usageErr(cmd, "that does not look like a recovery key (too short)")
		}
		return key, nil
	}

	cand := &cobra.Command{
		Use:   "candidates --destination ID --box BOX --recovery-key-stdin",
		Short: "List the restore points a destination holds for the old box (POST /v1/onboarding/restore/candidates; read only)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			key, err := check(cmd)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPost, "/v1/onboarding/restore/candidates", map[string]any{"destination_id": dest, "box_id": strings.TrimSpace(box), "recovery_key": key})
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, p := range list(obj(v)["points"]) {
					m := obj(p)
					apps := []string{}
					for _, x := range list(m["apps"]) {
						apps = append(apps, str(x))
					}
					rows = append(rows, []string{str(m["run_id"]), dash(str(m["taken_at"])), dash(strings.Join(apps, ", "))})
				}
				return table(w, "RUN\tTAKEN\tAPPS", rows)
			})
		},
	}
	common(cand)
	restore.AddCommand(cand)

	var run, app, reason string
	appCmd := &cobra.Command{
		Use:   "app --destination ID --box BOX --run RUN --app APP --recovery-key-stdin",
		Short: "Request restoring one installed app's data from a restore point; an owner approves it (POST /v1/onboarding/restore/apps)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if run == "" || app == "" {
				return usageErr(cmd, "--run and --app are required (see `candidates`)")
			}
			key, err := check(cmd)
			if err != nil {
				return err
			}
			body := map[string]any{"destination_id": dest, "box_id": strings.TrimSpace(box), "recovery_key": key, "run_id": run, "app_id": app, "approve": false}
			if reason != "" {
				body["reason"] = reason
			}
			// A stable key per (destination, box, run, app, day): asking twice replays the waiting request.
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/onboarding/restore/apps", idemKey("cli-restore-", dest, box, run, app), body)
			if err != nil {
				return err
			}
			if !a.G.JSON && !a.G.Quiet {
				fmt.Fprintln(a.Stderr, "onemind: the app must already be installed on this box; its data is restored only after an owner approves.")
				// The gateway holds the recovery key in memory for this one action (backups/service.py _pending_keys).
				fmt.Fprintln(a.Stderr, "onemind: approve it soon: the box keeps the recovery key in memory only, so a restart before approval means filing the request again with the key.")
			}
			return a.printRequested("restore of "+sanitize(app), v)
		},
	}
	common(appCmd)
	appCmd.Flags().StringVar(&run, "run", "", "the backup run id (from `candidates`)")
	appCmd.Flags().StringVar(&app, "app", "", "the app whose data to restore")
	appCmd.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")
	restore.AddCommand(appCmd)

	return []*cobra.Command{restore}
}
