// SPDX-License-Identifier: Apache-2.0

package cli

// onemind family: private, owner-managed controls for each person and each app's age rating
// (GET/PUT /v1/family/profiles/{user_id}, GET/PUT /v1/family/apps/{app_id}). Owner only. Changing
// either is a security setting: once the box has passkeys the gateway wants a fresh passkey sign-in,
// which a terminal cannot do, so the CLI explains that and points to the dashboard (explainGateway).

import (
	"fmt"
	"io"
	"net/http"

	"github.com/spf13/cobra"
)

func familyCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "family", Short: "Family controls: who may use which apps, and when (owner only)"}
	profile := &cobra.Command{Use: "profile", Short: "A person's controls: age limit, blocked app tags, allowed apps, time windows"}
	apps := &cobra.Command{Use: "app", Short: "An app's family classification: minimum age and tags"}

	profile.AddCommand(&cobra.Command{
		Use:   "show USER_ID",
		Short: "A person's controls (GET /v1/family/profiles/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/family/profiles/"+pathID(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				// null and [] mean opposite things here (core/onemind_core/family.py): null leaves the
				// rule off, [] blocks everything. On a child-safety screen neither may print as "-".
				allowed := "every app that passes the age and tag rules"
				if m["allowed_apps"] != nil {
					allowed = joinStrs(m["allowed_apps"], 0)
					if len(list(m["allowed_apps"])) == 0 {
						allowed = "none: every app is blocked"
					}
				}
				windows := "no time limits"
				if m["windows"] != nil {
					var parts []any
					for _, x := range list(m["windows"]) {
						wm := obj(x)
						parts = append(parts, dayNames(wm["days"])+" "+minutes(wm["start_minute"])+"-"+minutes(wm["end_minute"]))
					}
					windows = joinStrs(parts, 0)
					if len(parts) == 0 {
						windows = "none: no time is allowed, so apps are blocked all day"
					}
				}
				return kv(w, [][2]string{
					{"age limit", dash(jnum(m["max_age_rating"]))},
					{"birth date", dash(str(m["birth_date"]))},
					{"blocked tags", joinStrs(m["blocked_tags"], 0)},
					{"allowed apps", allowed},
					{"time windows", windows},
					{"time zone", dash(str(m["timezone"]))},
				})
			})
		},
	})
	var file string
	set := &cobra.Command{
		Use:   "set USER_ID --file profile.json",
		Short: "Replace a person's controls from a JSON file, or - for stdin (PUT /v1/family/profiles/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			body, err := a.readJSONInput(cmd, file)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPut, "/v1/family/profiles/"+pathID(args[0]), body)
			if err != nil {
				return err
			}
			return a.printDone(v, "Saved the controls for %s.", args[0])
		},
	}
	set.Flags().StringVar(&file, "file", "", "JSON with the fields `family profile show --json` prints")
	profile.AddCommand(set)

	apps.AddCommand(&cobra.Command{
		Use:   "show APP_ID",
		Short: "An app's minimum age and tags (GET /v1/family/apps/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/family/apps/"+pathID(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				return kv(w, [][2]string{{"minimum age", dash(jnum(m["min_age"]))}, {"tags", joinStrs(m["tags"], 0)}})
			})
		},
	})
	var aFile string
	aset := &cobra.Command{
		Use:   "set APP_ID --file app.json",
		Short: "Replace an app's minimum age and tags from a JSON file (PUT /v1/family/apps/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			body, err := a.readJSONInput(cmd, aFile)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPut, "/v1/family/apps/"+pathID(args[0]), body)
			if err != nil {
				return err
			}
			return a.printDone(v, "Saved the classification of %s.", args[0])
		},
	}
	aset.Flags().StringVar(&aFile, "file", "", `JSON like {"min_age": 12, "tags": ["social"]}`)
	apps.AddCommand(aset)

	root.AddCommand(profile, apps)
	return []*cobra.Command{root}
}

// weekdays are the gateway's day numbers: Window.days holds ints 0-6 with Monday=0.
var weekdays = [7]string{"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}

// dayNames renders a window's day numbers as "Mon, Tue" ("?N" for a number outside 0-6).
func dayNames(v any) string {
	var out []any
	for _, x := range list(v) {
		f, ok := x.(float64)
		if ok && f >= 0 && f <= 6 && f == float64(int(f)) {
			out = append(out, weekdays[int(f)])
		} else {
			out = append(out, "?"+str(x))
		}
	}
	return joinStrs(out, 0)
}

// minutes renders minutes after midnight as HH:MM.
func minutes(v any) string {
	f, ok := v.(float64)
	if !ok {
		return "-"
	}
	m := int(f)
	return fmt.Sprintf("%02d:%02d", m/60, m%60)
}

func init() { groups = append(groups, familyCommands) }
