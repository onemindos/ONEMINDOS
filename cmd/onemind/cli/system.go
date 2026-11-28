// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/spf13/cobra"
)

// resetPhrase is what the owner types to ask for a factory reset (core/onemind_core/system.py RESET_PHRASE).
const resetPhrase = "factory reset"

// systemCommands are `onemind system restart|shutdown|reset|diagnostics` (W1, audit b1).
//
// restart, shutdown and reset only REQUEST: they file a system.* action through POST /v1/system/actions
// and print its id. An owner approves it in the dashboard or the phone app (a reset only with a passkey);
// the CLI never approves, so a token that can ask cannot also run it. The hub answers 409 host_unavailable
// when this box cannot perform the control, and nothing is filed. diagnostics is a read: the hub's
// redacted support bundle (GET /v1/system/diagnostics, owner only).
func systemCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "system", Short: "Restart, shut down or reset this box (asks an owner to approve); export diagnostics"}
	var reason, confirm, out string
	ask := func(use, short, typ string) *cobra.Command {
		return &cobra.Command{
			Use:   use,
			Short: short,
			Args:  cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error {
				body := map[string]any{"type": typ, "idempotency_key": "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
				if reason != "" {
					body["reason"] = reason
				}
				if typ == "system.factory_reset" {
					if confirm != resetPhrase {
						return exitWith(ExitUsage, "usage", fmt.Sprintf("a factory reset erases this box: type --confirm %q to ask for it", resetPhrase))
					}
					body["confirm"] = confirm
				}
				c, _, err := a.client()
				if err != nil {
					return err
				}
				var act map[string]any
				if err := c.Do(bg(), http.MethodPost, "/v1/system/actions", body, &act); err != nil {
					return err
				}
				if a.G.JSON {
					return printJSON(a.Stdout, act)
				}
				id, _ := act["id"].(string)
				if a.G.Quiet {
					fmt.Fprintln(a.Stdout, sanitize(id))
					return nil
				}
				how := "An owner approves it in the dashboard or the phone app"
				if typ == "system.factory_reset" {
					how = "An owner approves it with a passkey in the dashboard or the phone app"
				}
				fmt.Fprintf(a.Stdout, "%s requested. Approval id: %s\n%s; nothing happens before that. Follow it with: onemind actions info %s\n",
					short1(typ), sanitize(id), how, sanitize(id))
				return nil
			},
		}
	}
	restart := ask("restart", "Ask to restart this box; prints the approval id an owner approves", "system.restart")
	shutdown := ask("shutdown", "Ask to shut this box down; prints the approval id an owner approves", "system.shutdown")
	reset := ask("reset", "Ask to factory-reset this box (erases everything; owner and passkey needed to approve)", "system.factory_reset")
	for _, c := range []*cobra.Command{restart, shutdown, reset} {
		c.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	}
	reset.Flags().StringVar(&confirm, "confirm", "", fmt.Sprintf("must be %q", resetPhrase))

	diag := &cobra.Command{
		Use:   "diagnostics",
		Short: "Export the redacted support bundle as JSON (owner)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var bundle map[string]any
			if err := c.Do(bg(), http.MethodGet, "/v1/system/diagnostics", nil, &bundle); err != nil {
				return err
			}
			if out == "" {
				return printJSON(a.Stdout, bundle)
			}
			f, err := os.OpenFile(out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
			if err != nil {
				return exitWith(ExitUsage, "usage", err.Error())
			}
			if err := printJSON(f, bundle); err != nil {
				f.Close()
				return err
			}
			if err := f.Close(); err != nil {
				return err
			}
			if !a.G.Quiet && !a.G.JSON {
				fmt.Fprintln(a.Stdout, "Wrote the diagnostic bundle to", sanitize(out))
			}
			return nil
		},
	}
	diag.Flags().StringVarP(&out, "output", "o", "", "write to this new file (mode 0600) instead of stdout")
	g.AddCommand(restart, shutdown, reset, diag)
	return []*cobra.Command{g}
}

func short1(typ string) string {
	switch typ {
	case "system.restart":
		return "Restart"
	case "system.shutdown":
		return "Shutdown"
	}
	return "Factory reset"
}
