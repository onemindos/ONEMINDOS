// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// workCommands is `onemind work`: the work engine's task list from a terminal (or from an AI agent
// that uses the CLI). `add` takes one line of quick-add text, for example
// `onemind work add "Pay rent every month #Home @bills p1"`, and the gateway turns it into a task.
// An agent's token can add and read tasks in projects that let AI work; it cannot create or delete
// projects or tasks, and nothing here approves anything.
func workCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "work", Short: "Tasks and projects (the work engine)"}

	var tz, key string
	add := &cobra.Command{Use: "add TEXT...", Short: "Add a task from one line of text (#project @label p1-p4 +person, dates, every ...)", Args: cobra.MinimumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if key == "" {
				b := make([]byte, 12)
				if _, err := rand.Read(b); err != nil {
					return err
				}
				key = "cli-" + hex.EncodeToString(b)
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]any{"text": strings.Join(args, " ")}
			if tz != "" {
				body["tz"] = tz
			}
			var t map[string]any
			if err := c.DoHeaders(bg(), http.MethodPost, "/v1/work/capture", map[string]string{"Idempotency-Key": key}, body, &t); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, t)
			}
			id, _ := t["id"].(string)
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, id)
				return nil
			}
			fmt.Fprintf(a.Stdout, "Added %s  %s%s\n", id, sanitize(str(t["title"])), dueSuffix(t))
			return nil
		}}
	add.Flags().StringVar(&tz, "tz", "", "time zone for dates, e.g. America/New_York (default UTC)")
	add.Flags().StringVar(&key, "idempotency-key", "", "send the same key again to retry without adding a second task")

	today := &cobra.Command{Use: "today", Short: "Your overdue tasks and the ones due today", Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			q := ""
			if tz != "" {
				q = "?tz=" + url.QueryEscape(tz)
			}
			var raw map[string]any
			if err := a.workGet("/v1/work/today"+q, &raw); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, raw)
			}
			rows := [][]string{}
			for _, k := range []string{"overdue", "today"} {
				for _, t := range list(raw[k]) {
					rows = append(rows, []string{k, str(t["id"]), "p" + str(t["priority"]), str(t["title"]), dueSuffix(t)})
				}
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "Nothing due today.")
				return nil
			}
			return table(a.Stdout, "WHEN\tID\tPRIORITY\tTITLE\tDUE", rows)
		}}
	today.Flags().StringVar(&tz, "tz", "", "time zone, e.g. America/New_York (default UTC)")

	var project, status string
	ls := &cobra.Command{Use: "list", Short: "Tasks you can see", Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			v := url.Values{}
			if project != "" {
				v.Set("project_id", project)
			}
			if status != "" {
				v.Set("status", status)
			}
			path := "/v1/work/tasks"
			if len(v) > 0 {
				path += "?" + v.Encode()
			}
			var raw map[string]any
			if err := a.workGet(path, &raw); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, raw)
			}
			rows := [][]string{}
			for _, t := range list(raw["items"]) {
				rows = append(rows, []string{str(t["id"]), str(t["status"]), "p" + str(t["priority"]), str(t["title"]), dueSuffix(t)})
			}
			return table(a.Stdout, "ID\tSTATUS\tPRIORITY\tTITLE\tDUE", rows)
		}}
	ls.Flags().StringVar(&project, "project", "", "only this project (its id)")
	ls.Flags().StringVar(&status, "status", "", "todo, doing, done or cancelled")

	done := &cobra.Command{Use: "done ID", Short: "Mark a task done (a repeating task moves to its next date)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var t map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/work/tasks/"+url.PathEscape(args[0])+"/complete", nil, &t); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, t)
			}
			if !a.G.Quiet {
				fmt.Fprintf(a.Stdout, "%s is now %s%s\n", args[0], str(t["status"]), dueSuffix(t))
			}
			return nil
		}}
	root.AddCommand(add, today, ls, done)
	return []*cobra.Command{root}
}

func (a *App) workGet(path string, out any) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	return c.Do(bg(), http.MethodGet, path, nil, out)
}

func str(v any) string {
	switch x := v.(type) {
	case nil:
		return ""
	case string:
		return x
	case float64:
		return fmt.Sprintf("%g", x)
	}
	return fmt.Sprint(v)
}

func list(v any) []map[string]any {
	out := []map[string]any{}
	items, _ := v.([]any)
	for _, i := range items {
		if m, ok := i.(map[string]any); ok {
			out = append(out, m)
		}
	}
	return out
}

// dueSuffix is "  due 2026-11-12" (date only for an all-day task) or "".
func dueSuffix(t map[string]any) string {
	s := str(t["due_at"])
	if s == "" {
		return ""
	}
	if ts, err := time.Parse(time.RFC3339, s); err == nil {
		if allDay, _ := t["due_all_day"].(bool); allDay {
			return "  due " + ts.UTC().Format("2006-01-02")
		}
		return "  due " + ts.UTC().Format("2006-01-02 15:04 UTC")
	}
	return ""
}
