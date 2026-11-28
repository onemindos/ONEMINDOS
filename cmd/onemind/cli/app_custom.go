// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
)

// Custom apps (PLG-GIT-01, D-026): an app linked from a Git repository goes through the same checks
// as a Market app. `deploy` plans a revision on the gateway (a fetch, the checks, a recorded
// revision; nothing runs), then files the ordinary app.install or app.update request, which waits
// for an owner. `rollback` does the same for the previously deployed revision.

// customPlan is the part of POST /v1/custom-apps/plan the CLI reads. The gateway's full reply is
// printed unchanged with --json.
type customPlan struct {
	AppID      string   `json:"app_id"`
	Name       string   `json:"name"`
	Version    string   `json:"version"`
	Revision   int      `json:"revision"`
	Commit     string   `json:"commit"`
	Verdict    string   `json:"verdict"`
	ActionType string   `json:"action_type"`
	Problems   []string `json:"problems"`
	Notes      []string `json:"notes"`
	Scan       *struct {
		Result string `json:"result"`
	} `json:"scan"`
	Signature *struct {
		Policy string `json:"policy"`
		Status string `json:"status"`
		Detail string `json:"detail"`
	} `json:"signature"`
}

type customRollback struct {
	AppID        string `json:"app_id"`
	FromRevision int    `json:"from_revision"`
	ToRevision   int    `json:"to_revision"`
	Commit       string `json:"commit"`
	Version      string `json:"version"`
	ActionType   string `json:"action_type"`
}

// delegateRequest files and (for an owner) approves the app.install or app.update, with the flags
// the caller was given, by running the same command `onemind apps install` runs.
func delegateRequest(a *App, cmd *cobra.Command, typ, appID string) error {
	req := requestCommand(a, typ, "request APP_ID", "")
	for _, name := range []string{"no-approve", "yes", "wait", "accept-licence"} {
		if f := cmd.Flags().Lookup(name); f != nil && f.Changed {
			if err := req.Flags().Set(name, f.Value.String()); err != nil {
				return err
			}
		}
	}
	return req.RunE(req, []string{appID})
}

func addRequestFlags(cmd *cobra.Command) {
	cmd.Flags().Bool("no-approve", false, "only plan and file the request (scripts, agents, non-owners)")
	cmd.Flags().Bool("yes", false, "approve without asking (owner token approvals)")
	cmd.Flags().Duration("wait", 0, "wait for the outcome (default 10m once approved)")
	cmd.Flags().Lookup("wait").NoOptDefVal = "10m"
	cmd.Flags().String("accept-licence", "", "APP_ID: accept a blocked or unknown licence class for this install (the owner, in person)")
}

func appDeployCommand(a *App) *cobra.Command {
	var gitURL, ref string
	cmd := &cobra.Command{
		Use:   "deploy --git URL --ref REF",
		Short: "Deploy a custom app from a Git repository (checks it, then waits for an owner's approval)",
		Long: "Fetches the repository at the ref in the gateway's sandbox, checks onemind.app.yaml and the manifests like a Market app, " +
			"and records a revision. Nothing is installed until an owner approves the install or update request this files.",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if u, err := url.Parse(gitURL); err != nil || u.Scheme != "https" || u.User != nil || u.RawQuery != "" || u.Host == "" {
				return exitWith(ExitUsage, "usage", "--git must be an https:// URL with no user name, password or query")
			}
			noApprove, _ := cmd.Flags().GetBool("no-approve")
			yes, _ := cmd.Flags().GetBool("yes")
			if !noApprove && !yes && !a.Interactive() {
				return exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --no-approve to only plan and file the request (or --yes to approve it as the owner)")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/custom-apps/plan", map[string]any{"url": gitURL, "ref": ref}, &raw); err != nil {
				return err
			}
			plan := decodeInto[customPlan](raw)
			// With --json the plan goes to stderr so stdout stays one document: the action the request files.
			out := a.Stdout
			if a.G.JSON {
				out = a.Stderr
			}
			if plan.Verdict != "ready" {
				if a.G.JSON {
					_ = printJSON(a.Stdout, raw)
				}
				for _, p := range plan.Problems {
					fmt.Fprintf(a.Stderr, "  - %s\n", p)
				}
				return exitWith(ExitVerifyFailed, "validation_failed", "the repository did not pass the checks; nothing was installed")
			}
			fmt.Fprintf(out, "Planned %s %s as revision %d (commit %s), scan %s.\n", plan.AppID, plan.Version, plan.Revision, shortCommit(plan.Commit), plan.Scan.Result)
			if plan.Signature != nil {
				fmt.Fprintf(out, "Signature: %s (%s). %s\n", plan.Signature.Status, plan.Signature.Policy, plan.Signature.Detail)
			}
			for _, n := range plan.Notes {
				fmt.Fprintf(out, "Note: %s\n", n)
			}
			return delegateRequest(a, cmd, plan.ActionType, plan.AppID)
		},
	}
	cmd.Flags().StringVar(&gitURL, "git", "", "https URL of the Git repository (required)")
	cmd.Flags().StringVar(&ref, "ref", "", "branch, tag or full commit id to deploy (required)")
	_ = cmd.MarkFlagRequired("git")
	_ = cmd.MarkFlagRequired("ref")
	addRequestFlags(cmd)
	return cmd
}

func appRollbackCommand(a *App) *cobra.Command {
	var revision int
	cmd := &cobra.Command{
		Use:   "rollback APP_ID",
		Short: "Roll a custom app back to its previously deployed revision (waits for an owner's approval)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			noApprove, _ := cmd.Flags().GetBool("no-approve")
			yes, _ := cmd.Flags().GetBool("yes")
			if !noApprove && !yes && !a.Interactive() {
				return exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --no-approve to only plan and file the request (or --yes to approve it as the owner)")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]any{}
			if cmd.Flags().Changed("revision") {
				body["revision"] = revision
			}
			var raw map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/custom-apps/"+url.PathEscape(args[0])+"/rollback", body, &raw); err != nil {
				return err
			}
			plan := decodeInto[customRollback](raw)
			out := a.Stdout
			if a.G.JSON {
				out = a.Stderr
			}
			fmt.Fprintf(out, "Rolling %s back from revision %d to revision %d (commit %s).\n", plan.AppID, plan.FromRevision, plan.ToRevision, shortCommit(plan.Commit))
			return delegateRequest(a, cmd, plan.ActionType, plan.AppID)
		},
	}
	cmd.Flags().IntVar(&revision, "revision", 0, "roll back to this earlier deployed revision (default: the previous one)")
	addRequestFlags(cmd)
	return cmd
}

func appHistoryCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "history APP_ID",
		Short: "A custom app's revisions: what was planned and deployed, newest first",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw map[string]any
			if err := c.Do(bg(), http.MethodGet, "/v1/custom-apps/"+url.PathEscape(args[0]), nil, &raw); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, raw)
			}
			var rows [][]string
			revs, _ := raw["revisions"].([]any)
			for _, r := range revs {
				m, _ := r.(map[string]any)
				scan, _ := m["scan"].(map[string]any)
				mark := ""
				if m["deployed"] == true {
					mark = "running"
				} else if m["current"] == true {
					mark = "next"
				}
				rows = append(rows, []string{fmt.Sprint(m["revision"]), shortCommit(fmt.Sprint(m["commit"])), dash(fmt.Sprint(m["version"])),
					fmt.Sprint(scan["result"]), dash(strings.TrimSpace(fmt.Sprint(valueOr(m["deployed_at"], "")))), mark})
			}
			return table(a.Stdout, "REV\tCOMMIT\tVERSION\tSCAN\tDEPLOYED\tNOW", rows)
		},
	}
}

func shortCommit(commit string) string {
	if len(commit) > 12 {
		return commit[:12]
	}
	return commit
}

func valueOr(v any, d string) any {
	if v == nil {
		return d
	}
	return v
}

// decodeInto reads the fields the CLI needs from a reply it also prints unchanged.
func decodeInto[T any](raw map[string]any) T {
	var out T
	b, _ := json.Marshal(raw)
	_ = json.Unmarshal(b, &out)
	return out
}
