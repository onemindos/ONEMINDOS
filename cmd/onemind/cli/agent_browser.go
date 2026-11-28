// SPDX-License-Identifier: Apache-2.0

package cli

// onemind agent-browser: the agent browser over the gateway (/v1/agent-browser/*, #694). The reads show the
// sites an AI agent may visit and its browsing sessions. `sites request` only FILES a request that waits for an
// owner (agentbrowser.site.allow); it never approves one, so an agent or a script cannot widen an agent's reach on
// its own (AI never actuates without human approval). `sites remove` and `sessions end` take access away at once;
// the gateway allows them to the owner only.

import (
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
)

func agentBrowserCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "agent-browser", Short: "The agent browser: sites an AI agent may visit, and its sessions (owner)"}

	sites := &cobra.Command{Use: "sites", Short: "Sites an agent may visit"}
	sites.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The approved sites (GET /v1/agent-browser/sites)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/agent-browser/sites", func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, s := range list(v) {
					m := obj(s)
					rows = append(rows, []string{str(m["id"]), str(m["agent"]), str(m["entry"]), dash(str(m["approved_by"])), str(m["created_at"])})
				}
				return table(w, "ID\tAGENT\tSITE\tAPPROVED BY\tSINCE", rows)
			})
		},
	})
	var agent, note string
	request := &cobra.Command{
		Use:   "request SITE",
		Short: "Ask to allow a site for an agent: example.org or *.example.org; an owner approves it (POST /v1/agent-browser/sites)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			entry := strings.TrimSpace(args[0])
			if strings.TrimSpace(agent) == "" {
				return usageErr(cmd, "--agent is required: name the agent this site is for")
			}
			body := map[string]any{"entry": entry, "agent": strings.TrimSpace(agent)}
			if note != "" {
				body["note"] = note
			}
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/agent-browser/sites", idemKey("cli-agent-browser-site-", agent, entry), body)
			if err != nil {
				return err
			}
			return a.printRequested("agent browser site "+sanitize(entry), v)
		},
	}
	request.Flags().StringVar(&agent, "agent", "", "the agent this site is for (required)")
	request.Flags().StringVar(&note, "note", "", "why, shown to the owner")
	sites.AddCommand(request)
	sites.AddCommand(&cobra.Command{
		Use:   "remove ID",
		Short: "Take a site away from an agent, at once (DELETE /v1/agent-browser/sites/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodDelete, "/v1/agent-browser/sites/"+url.PathEscape(args[0]), nil)
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, _ any) error {
				_, err := io.WriteString(w, "Removed site "+sanitize(args[0])+". The agent can no longer open it.\n")
				return err
			})
		},
	})
	root.AddCommand(sites)

	sessions := &cobra.Command{Use: "sessions", Short: "Agent browsing sessions"}
	sessions.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The browser sessions (GET /v1/agent-browser/sessions)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/agent-browser/sessions", func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, s := range list(v) {
					m := obj(s)
					rows = append(rows, []string{str(m["id"]), str(m["agent"]), str(m["state"]), str(m["pages"]) + "/" + str(m["max_pages"]), str(m["expires_at"])})
				}
				return table(w, "ID\tAGENT\tSTATE\tPAGES\tEXPIRES", rows)
			})
		},
	})
	sessions.AddCommand(&cobra.Command{
		Use:   "end ID",
		Short: "End a browsing session now (DELETE /v1/agent-browser/sessions/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodDelete, "/v1/agent-browser/sessions/"+url.PathEscape(args[0]), nil)
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, _ any) error {
				_, err := io.WriteString(w, "Ended session "+sanitize(args[0])+".\n")
				return err
			})
		},
	})
	root.AddCommand(sessions)
	return []*cobra.Command{root}
}
