// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"time"

	"github.com/spf13/cobra"
)

// nameRe is the box name: one lower-case DNS label (core/onemind_core/routers/instance_name.py).
var nameRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`)

// nameCommands are `onemind name show` and `onemind name set NAME` (P-05). set files an instance.rename action
// (PUT /v1/instance/name) and prints its id: an owner approves it in the dashboard (Settings > About) or the
// phone app. The CLI never approves it, so an agent's token can ask but not rename the box. Once the host has
// done it, the box answers as NAME.local.
func nameCommands(a *App) []*cobra.Command {
	n := &cobra.Command{Use: "name", Short: "The box's name: what the sign-in page says and what <name>.local answers to"}
	n.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "Print the box's name",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out struct {
				Name string `json:"name"`
			}
			if err := c.Do(bg(), http.MethodGet, "/v1/instance/name", nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.name/v1", "name": out.Name})
			}
			fmt.Fprintln(a.Stdout, sanitize(out.Name))
			return nil
		},
	})
	var reason string
	set := &cobra.Command{
		Use:   "set NAME",
		Short: "Ask to rename the box; prints the approval id an owner approves (the box then answers as NAME.local)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if !nameRe.MatchString(args[0]) {
				return exitWith(ExitUsage, "usage", "NAME must be lower-case letters, digits and -, up to 63 characters, not starting or ending with -")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]any{"name": args[0], "idempotency_key": "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
			if reason != "" {
				body["reason"] = reason
			}
			var act map[string]any
			if err := c.Do(bg(), http.MethodPut, "/v1/instance/name", body, &act); err != nil {
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
			fmt.Fprintf(a.Stdout, "Rename to %s requested. Approval id: %s\nAn owner approves it (dashboard or phone app); follow it with: onemind actions info %s\nThen the box answers as %s.local\n",
				sanitize(args[0]), sanitize(id), sanitize(id), sanitize(args[0]))
			return nil
		},
	}
	set.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	n.AddCommand(set)
	return []*cobra.Command{n}
}
