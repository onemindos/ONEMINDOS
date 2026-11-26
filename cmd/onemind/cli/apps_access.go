// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind apps access get|set` (contract §12.6; issue #1214): who can open an app. Owners and adults
// open every app; sharing decides for teens, children, guests and people added by name. Owner only.
// Narrowing goes through at once. Widening adds power (more people, or moving people to the app's own
// sign-in, which OneMind then no longer checks), so once the box holds passkeys the gateway asks
// for a passkey confirmation bound to this exact change (D-028), which a token on a command line cannot
// make: the CLI then says to do it in the dashboard (Settings > Permissions > By app), which asks for
// the key, and the code on the box's own screen before the first proven key, in place.

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

func appAccessCommand(a *App) *cobra.Command {
	root := &cobra.Command{Use: "access", Short: "Who can open an app: roles, people by name, sign-in (owner only)"}
	path := func(id string) string { return "/v1/apps/" + url.PathEscape(id) + "/access" }
	show := func(w io.Writer, v any) error {
		m := obj(v)
		var people []string
		for _, p := range list(m["people"]) {
			pm := obj(p)
			people = append(people, fmt.Sprintf("%s (%s)", sanitize(str(pm["display_name"])), sanitize(str(pm["id"]))))
		}
		var roles []string
		for _, r := range list(m["roles"]) {
			roles = append(roles, sanitize(str(r)))
		}
		auth := map[string]string{"onemind": "OneMind sign-in", "app": "the app's own sign-in"}[str(m["auth"])]
		pairs := [][2]string{{"app", sanitize(str(m["app_id"]))}, {"roles", orNone(roles)}, {"people", orNone(people)}, {"sign-in", auth}}
		if allowed, ok := m["allowed"].(bool); ok {
			pairs = append(pairs, [2]string{"you can open it", fmt.Sprint(allowed)})
		}
		if err := kv(w, pairs); err != nil {
			return err
		}
		_, err := fmt.Fprintln(w, "Owners and adults can always open every app.")
		return err
	}
	get := &cobra.Command{Use: "get APP_ID", Short: "Show who can open an app (GET /v1/apps/{id}/access)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error { return a.read(path(args[0]), show) }}

	var roles, people []string
	var auth string
	var none bool
	set := &cobra.Command{
		Use:   "set APP_ID",
		Short: "Change who can open an app; flags you leave out keep their current value (PUT /v1/apps/{id}/access)",
		Example: "  onemind apps access set notes --role guest --person usr_123\n" +
			"  onemind apps access set notes --none        # only owners and adults",
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			f := cmd.Flags()
			if !f.Changed("role") && !f.Changed("person") && !f.Changed("auth") && !none {
				return usageErr(cmd, "say what to change: --role, --person, --auth or --none")
			}
			if none && (f.Changed("role") || f.Changed("person")) {
				return usageErr(cmd, "--none cannot be combined with --role or --person")
			}
			if f.Changed("auth") && auth != "onemind" && auth != "app" {
				return usageErr(cmd, `--auth must be "onemind" or "app"`)
			}
			cur, err := a.gwDo(http.MethodGet, path(args[0]), nil)
			if err != nil {
				return err
			}
			m := obj(cur)
			body := map[string]any{"roles": []string{}, "people": []string{}, "auth": str(m["auth"])}
			if !none {
				body["roles"], body["people"] = strList(m["roles"]), idList(m["people"])
				if f.Changed("role") {
					body["roles"] = append([]string{}, roles...)
				}
				if f.Changed("person") {
					body["people"] = append([]string{}, people...)
				}
			}
			if f.Changed("auth") {
				body["auth"] = auth
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodPut, path(args[0]), body, &out); err != nil {
				var ge *onemind.Error
				if errors.As(err, &ge) && ge.Reason == "step_up_required" {
					return exitWith(ExitUsage, "usage", "sharing an app with more people, or moving it to its own sign-in, needs your passkey: do it in the dashboard (Settings > Permissions > By app), which asks for it in place; the CLI cannot make that confirmation. Taking access away works here")
				}
				return err
			}
			return a.withJSONOrText(out, show)
		},
	}
	set.Flags().StringSliceVar(&roles, "role", nil, "role that can open it: teen, child, guest (or adult); repeatable; replaces the list")
	set.Flags().StringSliceVar(&people, "person", nil, "user id that can open it (see `onemind users list`); repeatable; replaces the list")
	set.Flags().StringVar(&auth, "auth", "", `how people sign in to it: "onemind" or "app"`)
	set.Flags().BoolVar(&none, "none", false, "share with nobody beyond owners and adults")
	root.AddCommand(get, set)
	return root
}

func orNone(xs []string) string {
	if len(xs) == 0 {
		return "none"
	}
	return strings.Join(xs, ", ")
}

func strList(v any) []string {
	out := []string{}
	for _, x := range list(v) {
		if s := str(x); s != "" {
			out = append(out, s)
		}
	}
	return out
}

func idList(v any) []string {
	out := []string{}
	for _, x := range list(v) {
		if s := str(obj(x)["id"]); s != "" {
			out = append(out, s)
		}
	}
	return out
}
