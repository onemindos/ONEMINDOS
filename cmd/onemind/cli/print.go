// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"time"

	"github.com/spf13/cobra"
)

func printCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "print", Short: "Physical print jobs"}
	root.AddCommand(&cobra.Command{
		Use:   "request JOB TITLE",
		Short: "File a held CUPS job for owner approval (use the job and title from onemind-print-hold)",
		Args:  cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var action any
			body := map[string]any{
				"type": "print.job.release", "params": map[string]string{"job": args[0], "title": args[1]},
				"idempotency_key": freshKey(), "expires_at": c.HubNow().Add(10 * time.Minute).UTC().Format(time.RFC3339),
			}
			if err := c.Do(bg(), http.MethodPost, "/v1/actions", body, &action); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, action)
			}
			id := sanitize(str(obj(action)["id"]))
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, id)
			} else {
				fmt.Fprintf(a.Stdout, "Requested %s. Review the job in Approvals and hold to approve with a passkey.\n", id)
			}
			return nil
		},
	})
	return []*cobra.Command{root}
}
