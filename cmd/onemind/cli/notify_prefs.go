// SPDX-License-Identifier: Apache-2.0

package cli

// onemind notify prefs and notify sources: how and where you hear about things (GET/PUT
// /v1/notifications/preferences, GET /v1/notifications/sources, PUT /v1/notifications/sources/{id}).
// They are your own settings: the gateway applies them to the person whose token is used. Muting only
// quietens delivery; the item still lands in the inbox, and a critical alert is never hidden by it.

import (
	"fmt"
	"io"
	"net/http"

	"github.com/spf13/cobra"
)

func notifyPrefsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "prefs", Short: "Your delivery settings: quiet hours, digest, muted topics (GET/PUT /v1/notifications/preferences)"}
	g.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "Your settings",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/notifications/preferences", func(w io.Writer, v any) error {
				m := obj(v)
				quiet := "off"
				if q := obj(m["quiet_hours"]); len(q) > 0 {
					quiet = fmt.Sprintf("%s to %s (%s)", str(q["from"]), str(q["to"]), str(q["tz"]))
				}
				digest := "off"
				if d := obj(m["digest"]); d["enabled"] == true {
					digest = "daily at " + str(d["at"])
				}
				var mutes []any
				for _, x := range list(m["mutes"]) {
					mutes = append(mutes, str(obj(x)["topic"])+" on "+str(obj(x)["channel"]))
				}
				silence := "off"
				if s := obj(m["silence"]); len(s) > 0 {
					silence = "until " + str(s["until"])
				}
				return kv(w, [][2]string{{"quiet hours", quiet}, {"daily digest", digest}, {"muted", joinStrs(mutes, 0)}, {"silenced", silence},
					{"routes", jnum(float64(len(list(m["routes"]))))}, {"keep for days", dash(jnum(m["retention_days"]))}})
			})
		},
	})
	var channel string
	edit := func(use, short string, add bool) *cobra.Command {
		return &cobra.Command{
			Use:   use + " TOPIC [--channel CHANNEL]",
			Short: short,
			Args:  cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				cur, err := a.gwDo(http.MethodGet, "/v1/notifications/preferences", nil)
				if err != nil {
					return err
				}
				doc := obj(cur)
				var mutes []any
				found := false
				for _, x := range list(doc["mutes"]) {
					if str(obj(x)["topic"]) == args[0] && str(obj(x)["channel"]) == channel {
						found = true
						if !add {
							continue
						}
					}
					mutes = append(mutes, x)
				}
				if add && !found {
					mutes = append(mutes, map[string]any{"topic": args[0], "channel": channel})
				}
				if mutes == nil {
					mutes = []any{}
				}
				doc["mutes"] = mutes
				v, err := a.gwDo(http.MethodPut, "/v1/notifications/preferences", doc)
				if err != nil {
					return err
				}
				return a.printDone(v, "%s %s on %s.", map[bool]string{true: "Muted", false: "Unmuted"}[add], args[0], channel)
			},
		}
	}
	mute := edit("mute", "Stop delivery of a topic to a channel, device, in_app or all (*); the inbox keeps it", true)
	unmute := edit("unmute", "Deliver a topic again", false)
	for _, c := range []*cobra.Command{mute, unmute} {
		c.Flags().StringVar(&channel, "channel", "*", "a channel or device id, in_app, or * for all")
	}
	var file string
	set := &cobra.Command{
		Use:   "set --file prefs.json",
		Short: "Replace all your settings from a JSON file, or - for stdin; start from `show --json`",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			body, err := a.readJSONInput(cmd, file)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPut, "/v1/notifications/preferences", body)
			if err != nil {
				return err
			}
			return a.printDone(v, "Saved your notification settings.")
		},
	}
	set.Flags().StringVar(&file, "file", "", "the settings document")
	g.AddCommand(mute, unmute, set)
	return g
}

func notifySourcesCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "sources", Short: "Which apps and parts of the box send you things: list, mute one"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Each sender and how busy it was (GET /v1/notifications/sources)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/notifications/sources", "ID\tNAME\tKIND\tLAST HOUR\tSTATE", func(m map[string]any) []string {
				state := "on"
				if m["muted"] == true {
					state = "muted"
				}
				return []string{str(m["id"]), str(m["name"]), str(m["kind"]), jnum(m["posts_last_hour"]), state}
			})
		},
	})
	set := func(use, short string, muted bool) *cobra.Command {
		return &cobra.Command{
			Use:   use + " SOURCE_ID",
			Short: short,
			Args:  cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				v, err := a.gwDo(http.MethodPut, "/v1/notifications/sources/"+pathID(args[0]), map[string]any{"muted": muted})
				if err != nil {
					return err
				}
				return a.printDone(v, "%s %s.", map[bool]string{true: "Muted", false: "Unmuted"}[muted], args[0])
			},
		}
	}
	g.AddCommand(set("mute", "Stop a sender reaching your inbox (PUT /v1/notifications/sources/ID)", true), set("unmute", "Let a sender through again", false))
	return g
}
