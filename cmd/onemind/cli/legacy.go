// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"

	"github.com/spf13/cobra"
)

// legacyCommands is `onemind legacy` (gateway permissions design 25f, D-028): the people who may get a
// read-only copy of an owner's files after the owner's death, and the claims they make. Adding a contact
// needs an owner session and a separate passkey approval. An owner session can remove a contact or
// cancel a claim immediately. Any sign-in by the owner cancels a claim at once.
func legacyCommands(a *App) []*cobra.Command {
	const enrollmentHold = "Legacy contact enrollment is on hold until OneMind supports verification with a hardware key or first-key setup at the box."
	root := &cobra.Command{Use: "legacy", Short: "Legacy contacts and claims: who may get a copy of your files after your death"}
	call := func(method, path string, body, out any) error {
		c, _, err := a.client()
		if err != nil {
			return err
		}
		return c.Do(bg(), method, path, body, out)
	}
	contacts := &cobra.Command{Use: "contacts", Short: "Your legacy contacts (owner only)"}
	list := &cobra.Command{Use: "list", Short: "List your legacy contacts", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var rows []map[string]any
			if err := call(http.MethodGet, "/v1/auth/legacy/contacts", nil, &rows); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, rows)
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No legacy contacts yet. "+enrollmentHold)
				return nil
			}
			out := make([][]string, 0, len(rows))
			for _, r := range rows {
				out = append(out, []string{str(r["id"]), str(r["display_name"]), str(r["state"]), fmt.Sprint(r["wait_days"]), dash(str(r["usable_at"]))})
			}
			return table(a.Stdout, "ID\tNAME\tSTATE\tWAIT DAYS\tCOUNTS FROM", out)
		}}
	var name, household string
	var cooling, wait int
	add := &cobra.Command{Use: "add", Short: "Request a legacy invite for owner passkey approval", Long: enrollmentHold, Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			body := map[string]any{"kind": "outside", "display_name": name}
			if household != "" {
				body = map[string]any{"kind": "household", "household_user_id": household}
			} else if name == "" {
				return usageErr(cmd, "say who: --name <name>, or --household <user-id> for an adult here")
			}
			if cooling != 0 {
				body["cooling_off_days"] = cooling
			}
			if wait != 0 {
				body["wait_days"] = wait
			}
			var r map[string]any
			if err := call(http.MethodPost, "/v1/auth/legacy/contacts", body, &r); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "Legacy invite requested. A claim would wait %v days.\n", r["wait_days"])
			fmt.Fprintf(a.Stdout, "Approve %s with your passkey in the dashboard Approvals page. Then run: onemind legacy contacts invite %s\n",
				sanitize(str(r["action_id"])), sanitize(str(r["contact_id"])))
			return nil
		}}
	add.Flags().StringVar(&name, "name", "", "the contact's name (someone outside the household)")
	add.Flags().StringVar(&household, "household", "", "the user id of an adult in this household")
	add.Flags().IntVar(&cooling, "cooling-off-days", 0, "days before the contact counts: 3, 7 or 14")
	add.Flags().IntVar(&wait, "wait-days", 0, "how long a claim waits: 14, 30, 60 or 90 (default 30)")
	invite := &cobra.Command{Use: "invite <contact-id>", Short: "Print an approved legacy invite from your owner session", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var r map[string]any
			if err := call(http.MethodGet, "/v1/auth/legacy/contacts/"+url.PathEscape(args[0])+"/invite", nil, &r); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "Box key: %s\nInvite (works once, expires %s):\n%s\n", sanitize(str(r["box_key_fingerprint"])),
				sanitize(str(r["invite_expires_at"])), sanitize(str(r["invite"])))
			return nil
		}}
	remove := &cobra.Command{Use: "remove <contact-id>", Short: "Remove a legacy contact (no step-up)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var r map[string]any
			if err := call(http.MethodDelete, "/v1/auth/legacy/contacts/"+url.PathEscape(args[0]), nil, &r); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "%s is %s.\n", sanitize(str(r["display_name"])), sanitize(str(r["state"])))
			return nil
		}}
	contacts.AddCommand(list, add, invite, remove)

	claims := &cobra.Command{Use: "claims", Short: "Legacy claims on this box (owners and adults)"}
	claimList := &cobra.Command{Use: "list", Short: "List legacy claims", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var rows []map[string]any
			if err := call(http.MethodGet, "/v1/auth/legacy/claims", nil, &rows); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, rows)
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No legacy claims.")
				return nil
			}
			out := make([][]string, 0, len(rows))
			for _, r := range rows {
				out = append(out, []string{str(r["id"]), str(r["contact_display_name"]), str(r["state"]), str(r["ends_at"])})
			}
			return table(a.Stdout, "ID\tFROM\tSTATE\tCAN BE GRANTED AFTER", out)
		}}
	var block bool
	cancel := &cobra.Command{Use: "cancel <claim-id>", Short: "Stop a claim (owner, no step-up); --block also removes that contact", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var r map[string]any
			if err := call(http.MethodPost, "/v1/auth/legacy/claims/"+url.PathEscape(args[0])+"/cancel", map[string]any{"block": block}, &r); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "Claim %s is %s.\n", sanitize(str(r["id"])), sanitize(str(r["state"])))
			return nil
		}}
	cancel.Flags().BoolVar(&block, "block", false, "also remove the legacy contact who made the claim")
	confirm := &cobra.Command{Use: "confirm <claim-id>", Short: "Confirm a claim as the second person (a household adult)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var r map[string]any
			if err := call(http.MethodPost, "/v1/auth/legacy/claims/"+url.PathEscape(args[0])+"/confirm", nil, &r); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "Claim %s is %s.\n", sanitize(str(r["id"])), sanitize(str(r["state"])))
			return nil
		}}
	claims.AddCommand(claimList, cancel, confirm)
	root.AddCommand(contacts, claims)
	return []*cobra.Command{root}
}
