// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"

	"github.com/spf13/cobra"
)

// agentsCommands is `onemind agents` (CORE-SEC-6, #159): the owner's kill switch for every AI
// agent. `stop` makes the gateway refuse every agent principal (403, reason agents_stopped) until
// `resume`; both are owner only and audited, and the state survives a gateway restart.
func agentsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "agents", Short: "The agent kill switch: stop or resume every AI agent (owner only)"}
	const path = "/v1/agents/kill-switch"
	show := func(raw map[string]any) error {
		if a.G.JSON {
			return printJSON(a.Stdout, raw)
		}
		on, _ := raw["on"].(bool)
		if a.G.Quiet {
			fmt.Fprintln(a.Stdout, map[bool]string{true: "stopped", false: "running"}[on])
			return nil
		}
		if on {
			fmt.Fprintln(a.Stdout, "Agents: STOPPED. The gateway refuses every AI agent until an owner runs `onemind agents resume`.")
		} else {
			fmt.Fprintln(a.Stdout, "Agents: running. An owner can stop them all with `onemind agents stop`.")
		}
		if by, ok := raw["changed_by"].(map[string]any); ok {
			fmt.Fprintf(a.Stdout, "Last changed by %s at %s", sanitize(fmt.Sprint(by["id"])), sanitize(fmt.Sprint(raw["changed_at"])))
			if r, ok := raw["reason"].(string); ok && r != "" {
				fmt.Fprintf(a.Stdout, ": %s", sanitize(r))
			}
			fmt.Fprintln(a.Stdout)
		}
		return nil
	}
	call := func(method string, body any) error {
		c, _, err := a.client()
		if err != nil {
			return err
		}
		var raw map[string]any
		if err := c.Do(bg(), method, path, body, &raw); err != nil {
			return err
		}
		return show(raw)
	}
	status := &cobra.Command{Use: "status", Short: "Whether agents are stopped (GET " + path + ")", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error { return call(http.MethodGet, nil) }}
	var reason string
	set := func(use, short string, on bool) *cobra.Command {
		cmd := &cobra.Command{Use: use, Short: short, Args: cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error {
				body := map[string]any{"on": on}
				if reason != "" {
					body["reason"] = reason
				}
				return call(http.MethodPut, body)
			}}
		cmd.Flags().StringVar(&reason, "reason", "", "why, for the audit record")
		return cmd
	}
	root.AddCommand(status,
		set("stop", "Stop every AI agent now (owner only; audited)", true),
		set("resume", "Let AI agents work again (owner only; audited)", false))
	return []*cobra.Command{root}
}
