// SPDX-License-Identifier: Apache-2.0

package cli

// onemind windows: the maintenance windows (GET /v1/windows, PUT /v1/windows/{id}). A window is a set
// of weekly time ranges that standing approvals and update policy wait for, so editing one adds
// power: the gateway answers 403 to anyone but an owner and wants a fresh passkey sign-in once the
// box has passkeys, which a token on a command line cannot do (the error says where to do it).
// Editing a window bumps the revision of every standing approval that uses it.

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"

	"github.com/spf13/cobra"
)

var (
	windowIDRe    = regexp.MustCompile(`^win_[a-z0-9_]{1,36}$`)
	windowRangeRe = regexp.MustCompile(`^(?:([a-z,]+)\s+)?(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$`)
)

// parseWindowRange reads "mon,tue 22:00-06:00" (or "22:00-06:00" for every day) into the API's shape.
func parseWindowRange(s string) (map[string]any, error) {
	m := windowRangeRe.FindStringSubmatch(strings.TrimSpace(strings.ToLower(s)))
	if m == nil {
		return nil, fmt.Errorf("range %q: write it like \"mon,tue 22:00-06:00\", or \"22:00-06:00\" for every day", s)
	}
	out := map[string]any{"start": m[2], "end": m[3]}
	if m[1] != "" {
		out["days"] = strings.Split(m[1], ",")
	}
	return out, nil
}

func windowsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "windows", Short: "Maintenance windows that standing approvals and updates wait for: list, set (owner only)"}
	root.AddCommand(&cobra.Command{
		Use: "list", Short: "The windows, and whether each is open now (GET /v1/windows)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/windows", func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(v) {
					m := obj(x)
					var rs []string
					for _, r := range list(m["ranges"]) {
						rm := obj(r)
						days := "every day"
						if d := list(rm["days"]); len(d) > 0 {
							var ds []string
							for _, e := range d {
								ds = append(ds, str(e))
							}
							days = strings.Join(ds, ",")
						}
						rs = append(rs, fmt.Sprintf("%s %s-%s", days, str(rm["start"]), str(rm["end"])))
					}
					open := "closed"
					if m["open_now"] == true {
						open = "open now"
					}
					rows = append(rows, []string{str(m["id"]), str(m["name"]), str(m["tz"]), open, strings.Join(rs, "; ")})
				}
				return table(w, "WINDOW\tNAME\tZONE\tNOW\tRANGES", rows)
			})
		},
	})
	var name, tz string
	var ranges []string
	set := &cobra.Command{
		Use:   "set WINDOW_ID --name NAME --range \"mon,tue 22:00-06:00\" [--range ...] [--tz box]",
		Short: "Create or replace a window as an owner (PUT /v1/windows/{id}); replaces all its ranges",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !windowIDRe.MatchString(args[0]) {
				return usageErr(cmd, "window ids look like win_<lower-case name>, for example win_nightly")
			}
			if name == "" || len(ranges) == 0 {
				return usageErr(cmd, "--name and at least one --range are required")
			}
			var rs []any
			for _, r := range ranges {
				p, err := parseWindowRange(r)
				if err != nil {
					return usageErr(cmd, err.Error())
				}
				rs = append(rs, p)
			}
			v, err := a.gwDo(http.MethodPut, "/v1/windows/"+url.PathEscape(args[0]), map[string]any{"name": name, "tz": tz, "ranges": rs})
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				_, err := fmt.Fprintf(w, "Saved %s. Standing approvals that use it were given a new revision.\n", str(obj(v)["id"]))
				return err
			})
		},
	}
	set.Flags().StringVar(&name, "name", "", "what the window is called")
	set.Flags().StringVar(&tz, "tz", "box", "time zone the times are in: box (this box's zone) or a name like Europe/Berlin")
	set.Flags().StringArrayVar(&ranges, "range", nil, "a weekly range, for example \"mon,tue 22:00-06:00\"; repeat for more (1 to 14)")
	root.AddCommand(set)
	return []*cobra.Command{root}
}
