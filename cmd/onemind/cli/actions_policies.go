// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind actions policies list|create|confirm|remove` (contract §12.17; issue #1214): standing
// approvals, the owner's "yes, in advance" for a narrow kind of request. The gateway keeps every hard
// limit (only read and write requests, exact names, at most 90 days, a daily limit). Creating one and
// confirming a paused legacy one add power: once the box holds passkeys the gateway asks for a passkey
// confirmation bound to that change (D-028), which a token cannot make, so the CLI then says to do it in
// the dashboard (Settings > Standing approvals). Removing one takes power away and works here. Owner only.

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

const policiesPath = "/v1/approval-policies"

func policiesCommand(a *App) *cobra.Command {
	g := &cobra.Command{Use: "policies", Aliases: []string{"standing"}, Short: "Standing approvals: say yes in advance to a narrow kind of request (owner only)"}
	showList := func(w io.Writer, v any) error {
		var rows [][]string
		for _, p := range list(v) {
			m := obj(p)
			allow, limits := obj(m["allow"]), obj(m["limits"])
			win := str(m["window_id"])
			if win == "" {
				win = "any time"
			}
			rows = append(rows, []string{sanitize(str(m["id"])), sanitize(str(m["state"])), sanitize(strings.Join(strList(allow["types"]), ",")),
				sanitize(strings.Join(strList(allow["requested_by"]), ",")), str(m["uses_24h"]) + "/" + str(limits["per_day"]), sanitize(win),
				sanitize(str(m["expires_at"])), sanitize(str(m["name"]))})
		}
		if len(rows) == 0 {
			_, err := fmt.Fprintln(w, "No standing approvals: every request waits for a person.")
			return err
		}
		return table(w, "ID\tSTATE\tCOVERS\tWHO MAY ASK\tTODAY\tONLY DURING\tENDS\tNAME", rows)
	}
	stepUpHint := func(err error, what string) error {
		var ge *onemind.Error
		if errors.As(err, &ge) && ge.Reason == "step_up_required" {
			return exitWith(ExitUsage, "usage", what+" needs your passkey: do it in the dashboard (Settings > Standing approvals), which asks for it in place; the CLI cannot make that confirmation")
		}
		return err
	}
	g.AddCommand(&cobra.Command{Use: "list", Short: "Standing approvals, with today's use (GET /v1/approval-policies)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error { return a.read(policiesPath, showList) }})

	var name, window, params string
	var types, from []string
	var perDay, days int
	create := &cobra.Command{
		Use:     "create",
		Short:   "Create a standing approval (POST /v1/approval-policies)",
		Example: "  onemind actions policies create --type app.restart --from agent:hermes --per-day 3 --days 30 --window win_nightly",
		Args:    cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if len(types) == 0 || len(from) == 0 {
				return usageErr(cmd, "say what it covers (--type) and who may ask (--from)")
			}
			if perDay < 1 || perDay > 1000 {
				return usageErr(cmd, "--per-day must be 1 to 1000")
			}
			if days < 1 || days > 90 {
				return usageErr(cmd, "--days must be 1 to 90: a standing approval always ends")
			}
			constraints := map[string]any{}
			if params != "" {
				if err := json.Unmarshal([]byte(params), &constraints); err != nil {
					return usageErr(cmd, `--params must be a JSON object, e.g. {"app_id": {"enum": ["notes"]}}`)
				}
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if _, err := c.Instance.Get(bg()); err != nil { // learn the hub clock, so expires_at is on its time
				return err
			}
			body := map[string]any{
				"allow":      map[string]any{"types": types, "requested_by": from, "params": constraints},
				"limits":     map[string]any{"per_day": perDay},
				"expires_at": c.HubNow().Add(time.Duration(days) * 24 * time.Hour).UTC().Format(time.RFC3339),
			}
			if name != "" {
				body["name"] = name
			}
			if window != "" {
				body["window_id"] = window
			}
			var out any
			if err := c.Do(bg(), http.MethodPost, policiesPath, body, &out); err != nil {
				return stepUpHint(err, "creating a standing approval")
			}
			return a.withJSONOrText(out, func(w io.Writer, v any) error {
				_, err := fmt.Fprintf(w, "Standing approval %s created; it ends %s.\n", sanitize(str(obj(v)["id"])), sanitize(str(obj(v)["expires_at"])))
				return err
			})
		},
	}
	f := create.Flags()
	f.StringSliceVar(&types, "type", nil, "request type it covers, e.g. app.restart (repeatable; read and write requests only)")
	f.StringSliceVar(&from, "from", nil, "who may ask, named exactly: agent:<id>, automation:<rule id>, plugin:<id> or person:<id> (repeatable)")
	f.IntVar(&perDay, "per-day", 3, "at most this many approvals in 24 hours (1 to 1000)")
	f.IntVar(&days, "days", 30, "ends after this many days (1 to 90)")
	f.StringVar(&window, "window", "", "only while this maintenance window is open (a win_<name> id)")
	f.StringVar(&name, "name", "", "a name to recognise it by")
	f.StringVar(&params, "params", "", `limits on request values as JSON, e.g. {"app_id": {"enum": ["notes"]}}`)
	g.AddCommand(create)

	g.AddCommand(&cobra.Command{Use: "confirm POLICY_ID", Short: "Turn a paused legacy standing approval back on (POST .../confirm)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodPost, policiesPath+"/"+url.PathEscape(args[0])+"/confirm", nil, &out); err != nil {
				return stepUpHint(err, "turning a standing approval back on")
			}
			return a.withJSONOrText(out, func(w io.Writer, v any) error {
				_, err := fmt.Fprintf(w, "Standing approval %s is on again.\n", sanitize(str(obj(v)["id"])))
				return err
			})
		}})
	g.AddCommand(&cobra.Command{Use: "remove POLICY_ID", Aliases: []string{"delete"}, Short: "Remove a standing approval; its requests wait for a person again", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if _, err := a.gwDo(http.MethodDelete, policiesPath+"/"+url.PathEscape(args[0]), nil); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"id": args[0], "removed": true})
			}
			_, err := fmt.Fprintf(a.Stdout, "Standing approval %s removed; its requests wait for a person again.\n", sanitize(args[0]))
			return err
		}})
	return g
}
