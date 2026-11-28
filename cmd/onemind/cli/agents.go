// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
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
		set("resume", "Let AI agents work again (owner only; audited)", false),
		agentInputsCommands(a))
	return []*cobra.Command{root}
}

// agentInputsCommands is `onemind agents inputs` (gateway permissions PR 6): what an agent can read
// that the gateway cannot see. An agent that reads outside text (web, email, files, a chat host) is
// tainted all the time, so no standing approval accepts its requests. Owner only; audited.
func agentInputsCommands(a *App) *cobra.Command {
	root := &cobra.Command{Use: "inputs", Short: "What an agent reads outside OneMind: web, email, files (owner only)"}
	path := func(id string) string { return "/v1/agents/" + url.PathEscape(id) + "/inputs" }
	show := func(raw map[string]any) error {
		if a.G.JSON {
			return printJSON(a.Stdout, raw)
		}
		in := joinAny(raw["external_inputs"])
		if declared, _ := raw["declared"].(bool); !declared && in != "" {
			fmt.Fprintf(a.Stdout, "(default: you have not declared this agent's inputs, so it counts as reading outside text)\n")
		}
		if in == "" {
			fmt.Fprintf(a.Stdout, "%s reads nothing outside OneMind that the gateway cannot see.\n", sanitize(fmt.Sprint(raw["id"])))
		} else {
			fmt.Fprintf(a.Stdout, "%s reads outside text (%s): it is tainted all the time, so a person approves each request.\n",
				sanitize(fmt.Sprint(raw["id"])), sanitize(in))
		}
		if acc := joinAny(raw["accept_injection_risk"]); acc != "" {
			fmt.Fprintf(a.Stdout, "Accepted injection risk for: %s (recorded; not in effect yet).\n", sanitize(acc))
		}
		return nil
	}
	get := &cobra.Command{Use: "get <agent-id>", Short: "Show what an agent is declared to read", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw map[string]any
			if err := c.Do(bg(), http.MethodGet, path(args[0]), nil, &raw); err != nil {
				return err
			}
			return show(raw)
		}}
	var web, email, files, chat, none bool
	var accept []string
	set := &cobra.Command{Use: "set <agent-id>", Short: "Declare what an agent reads (owner only; replaces the list)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			inputs := []string{}
			for _, kv := range []struct {
				on   bool
				name string
			}{{web, "web"}, {email, "email"}, {files, "files"}, {chat, "chat"}} {
				if kv.on {
					inputs = append(inputs, kv.name)
				}
			}
			if len(inputs) == 0 && !none {
				return usageErr(cmd, "say what the agent reads (--web, --email, --files, --chat) or --none")
			}
			if len(inputs) > 0 && none {
				return usageErr(cmd, "--none cannot be combined with --web, --email, --files or --chat")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw map[string]any
			body := map[string]any{"external_inputs": inputs, "accept_injection_risk": append([]string{}, accept...)}
			if err := c.Do(bg(), http.MethodPut, path(args[0]), body, &raw); err != nil {
				var ge *onemind.Error
				if errors.As(err, &ge) && ge.Reason == "step_up_required" {
					return exitWith(ExitUsage, "usage", "loosening an agent needs you to confirm with your passkey in the dashboard (Agents); the CLI cannot make that confirmation")
				}
				return err
			}
			return show(raw)
		}}
	set.Flags().BoolVar(&web, "web", false, "reads web pages")
	set.Flags().BoolVar(&email, "email", false, "reads email")
	set.Flags().BoolVar(&files, "files", false, "reads files it opens itself")
	set.Flags().BoolVar(&chat, "chat", false, "runs many chats on one token")
	set.Flags().BoolVar(&none, "none", false, "reads nothing outside the gateway (loosens the agent)")
	set.Flags().StringSliceVar(&accept, "accept-risk", nil, "write action type to accept the injection risk for (repeatable; recorded, not in effect yet)")
	root.AddCommand(get, set)
	return root
}

func joinAny(v any) string {
	list, _ := v.([]any)
	out := make([]string, 0, len(list))
	for _, x := range list {
		out = append(out, fmt.Sprint(x))
	}
	return strings.Join(out, ", ")
}
