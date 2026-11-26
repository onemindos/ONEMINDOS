// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// recoveryCommands is `onemind recovery` (gateway permissions design 25d, D-028). Merge note: PR #1194 (25c)
// also defines recoveryCommands (with the at-the-box `kit` subcommand) in recovery.go; whichever lands second
// keeps one root and adds the other's subcommands to it, so `onemind recovery` stays one command group.
// It covers the people who can
// help a locked-out owner get back in. Adding a contact is a security setting (owner, signed-in
// session, passkey step-up); removing one takes power away and needs no step-up. A contact never
// sees or approves anything: they only confirm, later, that a recovery really is the owner.
func recoveryCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "recovery", Short: "Recovery contacts and waits: who can help you get back into your account"}
	contacts := &cobra.Command{Use: "contacts", Short: "Your recovery contacts (owner only)"}
	stepUp := func(err error, what string) error {
		var ge *onemind.Error
		if errors.As(err, &ge) && ge.Reason == "step_up_required" {
			return exitWith(ExitUsage, "usage", what+" needs a fresh passkey sign-in: sign in with your passkey in the dashboard, then run this again")
		}
		return err
	}
	call := func(method, path string, body any, out any) error {
		c, _, err := a.client()
		if err != nil {
			return err
		}
		return c.Do(bg(), method, path, body, out)
	}
	list := &cobra.Command{Use: "list", Short: "List your recovery contacts and their state", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var rows []map[string]any
			if err := call(http.MethodGet, "/v1/auth/recovery/contacts", nil, &rows); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, rows)
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No recovery contacts yet. Add one with `onemind recovery contacts add --name <name>`.")
				return nil
			}
			out := make([][]string, 0, len(rows))
			for _, r := range rows {
				out = append(out, []string{str(r["id"]), str(r["display_name"]), str(r["kind"]), str(r["state"]), dash(str(r["usable_at"]))})
			}
			return table(a.Stdout, "ID\tNAME\tKIND\tSTATE\tCOUNTS FROM", out)
		}}
	var name, household string
	var cooling int
	add := &cobra.Command{Use: "add", Short: "Invite a recovery contact; prints the signed invite for their OneMind app", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			body := map[string]any{"kind": "outside", "display_name": name}
			if household != "" {
				body = map[string]any{"kind": "household", "household_user_id": household}
			} else if name == "" {
				return usageErr(cmd, "say who: --name <name> for someone outside the household, or --household <user-id> for an adult here")
			}
			if cooling != 0 {
				body["cooling_off_days"] = cooling
			}
			var r map[string]any
			if err := call(http.MethodPost, "/v1/auth/recovery/contacts", body, &r); err != nil {
				return stepUp(err, "adding a recovery contact")
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "Invited %s (%s). The invite works once and expires %s.\n", sanitize(str(r["display_name"])),
				sanitize(str(r["id"])), sanitize(str(r["invite_expires_at"])))
			fmt.Fprintf(a.Stdout, "They open it in the OneMind phone app. After they accept, they count after %v days.\n", r["cooling_off_days"])
			fmt.Fprintf(a.Stdout, "Box key: %s\nInvite:\n%s\n", sanitize(str(r["box_key_fingerprint"])), sanitize(str(r["invite"])))
			return nil
		}}
	add.Flags().StringVar(&name, "name", "", "the contact's name (someone outside the household)")
	add.Flags().StringVar(&household, "household", "", "the user id of an adult in this household")
	add.Flags().IntVar(&cooling, "cooling-off-days", 0, "days before the contact counts: 3, 7 or 14 (default: your setting)")
	remove := &cobra.Command{Use: "remove <contact-id>", Short: "Remove a contact or withdraw an invite (no step-up)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var r map[string]any
			if err := call(http.MethodDelete, "/v1/auth/recovery/contacts/"+url.PathEscape(args[0]), nil, &r); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			fmt.Fprintf(a.Stdout, "%s is %s.\n", sanitize(str(r["display_name"])), sanitize(str(r["state"])))
			return nil
		}}
	contacts.AddCommand(list, add, remove)

	var setCooling, setContactWait, setRemoteWait int
	settings := &cobra.Command{Use: "settings", Short: "Show or change your recovery waits (shortening needs a fresh passkey)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var r map[string]any
			var err error
			changes := map[string]any{}
			for k, v := range map[string]int{"cooling_off_days": setCooling, "contact_wait_hours": setContactWait, "remote_wait_hours": setRemoteWait} {
				if v != 0 {
					changes[k] = v
				}
			}
			if len(changes) > 0 {
				err = call(http.MethodPut, "/v1/auth/recovery/settings", changes, &r)
			} else {
				err = call(http.MethodGet, "/v1/auth/recovery/settings", nil, &r)
			}
			if err != nil {
				return stepUp(err, "shortening a recovery wait")
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			values, _ := r["values"].(map[string]any)
			options, _ := r["options"].(map[string]any)
			pairs := [][2]string{}
			for _, k := range []string{"cooling_off_days", "contact_wait_hours", "remote_wait_hours"} {
				pairs = append(pairs, [2]string{k, fmt.Sprintf("%v (options %s)", values[k], joinAny(options[k]))})
			}
			return kv(a.Stdout, pairs)
		}}
	settings.Flags().IntVar(&setCooling, "cooling-off-days", 0, "days before a new contact counts: 3, 7 or 14")
	settings.Flags().IntVar(&setContactWait, "contact-wait-hours", 0, "the wait after a contact confirms: 24, 48 or 72 (72 anyway if a strong key was used in the last 7 days)")
	settings.Flags().IntVar(&setRemoteWait, "remote-wait-hours", 0, "the wait of a recovery with no contact: 72 or 168")

	invitations := &cobra.Command{Use: "invitations", Short: "Invites asking you to be someone's recovery contact", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var rows []map[string]any
			if err := call(http.MethodGet, "/v1/auth/recovery/invitations", nil, &rows); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, rows)
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No invitations.")
				return nil
			}
			out := make([][]string, 0, len(rows))
			for _, r := range rows {
				out = append(out, []string{str(r["id"]), str(r["owner_display_name"]), str(r["invite_expires_at"])})
			}
			fmt.Fprintln(a.Stdout, "Accept an invitation in the OneMind phone app; the contact key lives in your phone.")
			return table(a.Stdout, "ID\tFROM\tEXPIRES", out)
		}}
	root.AddCommand(contacts, settings, invitations)
	root.AddCommand(recoveryFlowCommands(a)...)
	return []*cobra.Command{root}
}
