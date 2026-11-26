// SPDX-License-Identifier: Apache-2.0

package cli

// onemind automation: rules that file requests for you on a schedule or an event, their runs, the
// pause switch, the standing approvals that let a rule's requests go through unattended, and the
// maintenance windows those use (/v1/automation/*, /v1/approval-policies, /v1/windows). A rule can
// only FILE requests; whether one needs a person is decided by the gateway, as for any request. The
// gateway refuses agent tokens for the pause switch, and wants a fresh passkey sign-in to change a
// window, which a terminal cannot do (the message says where to do it). Creating a standing approval
// is not here: it adds power, so it stays in the dashboard with the passkey step.

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"

	"github.com/spf13/cobra"
)

func automationCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "automation", Short: "Rules that act for you on a schedule or an event: list, run history, pause, standing approvals, windows"}

	rules := &cobra.Command{Use: "rules", Short: "Automation rules"}
	rules.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every rule (GET /v1/automation/rules)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/automation/rules", "ID\tNAME\tON\tTRIGGER\tLAST FIRED\tBREAKER", func(m map[string]any) []string {
				on := "no"
				if m["enabled"] == true {
					on = "yes"
				}
				return []string{str(m["id"]), str(m["name"]), on, triggerText(obj(m["trigger"])), dash(str(m["last_fired_at"])), dash(str(m["breaker"]))}
			})
		},
	})
	rules.AddCommand(&cobra.Command{
		Use:   "show RULE_ID",
		Short: "One rule in full (GET /v1/automation/rules/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/automation/rules/"+pathID(args[0]), func(w io.Writer, v any) error { return printJSON(w, v) })
		},
	})
	var file string
	create := &cobra.Command{
		Use:   "create --file rule.json",
		Short: "Add a rule, off until a dry run has been looked at (POST /v1/automation/rules)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			body, err := a.readJSONInput(cmd, file)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPost, "/v1/automation/rules", body)
			if err != nil {
				return err
			}
			return a.printDone(v, "Added rule %s (off). Try it with: onemind automation rules dry-run %s", str(obj(v)["id"]), str(obj(v)["id"]))
		},
	}
	create.Flags().StringVar(&file, "file", "", "the rule as JSON: name, trigger, conditions, actions")
	post := func(use, short, suffix, done string) *cobra.Command {
		return &cobra.Command{
			Use:   use + " RULE_ID",
			Short: short,
			Args:  cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				v, err := a.gwDo(http.MethodPost, "/v1/automation/rules/"+pathID(args[0])+suffix, nil)
				if err != nil {
					return err
				}
				return a.printDone(v, done, args[0])
			},
		}
	}
	enable := post("enable", "Turn a rule on (POST .../enable); needs a dry run first", "/enable", "Turned on %s.")
	disable := post("disable", "Turn a rule off (POST .../disable)", "/disable", "Turned off %s.")
	dry := &cobra.Command{
		Use:   "dry-run RULE_ID",
		Short: "Show what a rule would have done, without doing it (POST .../dry-run)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodPost, "/v1/automation/rules/"+pathID(args[0])+"/dry-run", map[string]any{})
			if err != nil {
				return err
			}
			return printJSON(a.Stdout, v)
		},
	}
	var yes bool
	del := &cobra.Command{
		Use:   "delete RULE_ID --yes",
		Short: "Remove a rule (DELETE /v1/automation/rules/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, yes, "deleting "+args[0]+" cannot be undone"); err != nil {
				return err
			}
			if _, err := a.gwDo(http.MethodDelete, "/v1/automation/rules/"+pathID(args[0]), nil); err != nil {
				return err
			}
			return a.printDone(map[string]any{"id": args[0], "deleted": true}, "Deleted %s.", args[0])
		},
	}
	del.Flags().BoolVar(&yes, "yes", false, "confirm")
	rules.AddCommand(create, enable, disable, dry, del)

	var ruleID string
	var limit int
	runs := &cobra.Command{
		Use:   "runs",
		Short: "What rules did and when (GET /v1/automation/runs)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/automation/runs"+query("rule_id", ruleID, "limit", strconv.Itoa(limit)), "WHEN\tRULE\tOUTCOME\tREQUESTS", func(m map[string]any) []string {
				return []string{str(m["fired_at"]), str(m["rule_id"]), str(m["outcome"]), joinStrs(m["action_ids"], 40)}
			})
		},
	}
	runs.Flags().StringVar(&ruleID, "rule", "", "only this rule")
	runs.Flags().IntVar(&limit, "limit", 50, "at most this many runs (1 to 500)")

	schedules := &cobra.Command{
		Use:   "schedules",
		Short: "When each scheduled rule runs next (GET /v1/automation/schedules)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/automation/schedules", "RULE\tNAME\tON\tCRON\tNEXT RUN", func(m map[string]any) []string {
				on := "no"
				if m["enabled"] == true {
					on = "yes"
				}
				return []string{str(m["rule_id"]), str(m["name"]), on, str(m["cron"]) + " " + str(m["tz"]), dash(str(m["next_fire_at"]))}
			})
		},
	}

	state := &cobra.Command{
		Use:   "state",
		Short: "Is automation paused? (GET /v1/automation/state)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/automation/state", func(w io.Writer, v any) error {
				m := obj(v)
				s := "running"
				if m["paused"] == true {
					s = "PAUSED"
				}
				return kv(w, [][2]string{{"automation", s}, {"changed by", dash(str(m["changed_by"]))}, {"changed at", dash(str(m["changed_at"]))}, {"reason", dash(str(m["reason"]))}})
			})
		},
	}
	var reason string
	sw := func(use, short, route, done string) *cobra.Command {
		c := &cobra.Command{
			Use:   use,
			Short: short,
			Args:  cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error {
				body := map[string]any{}
				if reason != "" {
					body["reason"] = reason
				}
				v, err := a.gwDo(http.MethodPost, route, body)
				if err != nil {
					return err
				}
				return a.printDone(v, "%s", done)
			},
		}
		c.Flags().StringVar(&reason, "reason", "", "why, kept in the history")
		return c
	}
	pause := sw("pause", "Stop every rule at once (POST /v1/automation/pause); owner only", "/v1/automation/pause", "Automation is paused. No rule will file a request until you resume.")
	resume := sw("resume", "Let rules run again (POST /v1/automation/resume); owner only", "/v1/automation/resume", "Automation is running again.")

	policies := &cobra.Command{Use: "policies", Short: "Standing approvals: requests an owner pre-approved within limits (owner only)"}
	policies.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every standing approval (GET /v1/approval-policies)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/approval-policies", "ID\tNAME\tSTATE\tLIMIT PER DAY\tUSED 24H\tEXPIRES", func(m map[string]any) []string {
				return []string{str(m["id"]), str(m["name"]), str(m["state"]), jnum(obj(m["limits"])["per_day"]), jnum(m["uses_24h"]), dash(str(m["expires_at"]))}
			})
		},
	})
	var pYes bool
	pdel := &cobra.Command{
		Use:   "revoke POLICY_ID --yes",
		Short: "Take a standing approval back (DELETE /v1/approval-policies/ID); requests will ask a person again",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, pYes, "revoking "+args[0]+" makes its requests wait for a person again"); err != nil {
				return err
			}
			if _, err := a.gwDo(http.MethodDelete, "/v1/approval-policies/"+pathID(args[0]), nil); err != nil {
				return err
			}
			return a.printDone(map[string]any{"id": args[0], "revoked": true}, "Revoked %s.", args[0])
		},
	}
	pdel.Flags().BoolVar(&pYes, "yes", false, "confirm")
	policies.AddCommand(pdel)

	windows := &cobra.Command{Use: "windows", Short: "Maintenance windows: the times unattended work may run"}
	windows.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every window and whether it is open now (GET /v1/windows)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/windows", "ID\tNAME\tZONE\tOPEN NOW\tRANGES", func(m map[string]any) []string {
				open := "no"
				if m["open_now"] == true {
					open = "yes"
				}
				rj, _ := json.Marshal(m["ranges"])
				return []string{str(m["id"]), str(m["name"]), str(m["tz"]), open, string(rj)}
			})
		},
	})
	var wFile string
	wset := &cobra.Command{
		Use:   "set WINDOW_ID --file window.json",
		Short: "Create or replace a window (PUT /v1/windows/ID); owner only, with a passkey sign-in",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			body, err := a.readJSONInput(cmd, wFile)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPut, "/v1/windows/"+pathID(args[0]), body)
			if err != nil {
				return err
			}
			return a.printDone(v, "Saved window %s.", args[0])
		},
	}
	wset.Flags().StringVar(&wFile, "file", "", `JSON like {"name": "Nights", "tz": "box", "ranges": [{"days": ["mon"], "start": "01:00", "end": "05:00"}]}`)
	windows.AddCommand(wset)

	root.AddCommand(rules, runs, schedules, state, pause, resume, policies, windows)
	return []*cobra.Command{root}
}

// triggerText says in words what starts a rule.
func triggerText(t map[string]any) string {
	for k, v := range t {
		switch k {
		case "schedule":
			return "schedule " + str(obj(v)["cron"])
		case "event":
			return "event " + str(obj(v)["type"])
		}
		return k
	}
	return "-"
}

func init() { groups = append(groups, automationCommands) }
