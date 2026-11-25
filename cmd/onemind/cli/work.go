// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// workCommands is `onemind work`: the Work task list from a terminal, through the gateway and the
// Go SDK. `add` takes one line of quick-add text, for example
// `onemind work add "Pay rent tomorrow at 5pm #Home @bills p1"`, and the gateway turns it into a task.
func workCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "work", Short: "Tasks and projects (Work)"}

	var tz, key string
	add := &cobra.Command{Use: "add TEXT", Short: "Add a task from one line (#project @label p1-p4 +person-id, dates)", Args: cobra.MinimumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if tz == "" {
				tz = localZone()
			}
			t, err := c.Work.QuickAdd(bg(), joinArgs(args), tz, key)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, t)
			}
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, t.ID)
				return nil
			}
			fmt.Fprintf(a.Stdout, "Added %s  %s%s\n", t.ID, sanitize(t.Title), dueSuffix(t))
			return nil
		}}
	add.Flags().StringVar(&tz, "tz", "", "time zone for dates, e.g. America/New_York (default this machine's zone)")
	add.Flags().StringVar(&key, "idempotency-key", "", "send the same key again to retry without adding a second task")

	view := func(use, name, short string) *cobra.Command {
		return &cobra.Command{Use: use, Short: short, Args: cobra.NoArgs, RunE: func(_ *cobra.Command, _ []string) error {
			return a.workList(name, "")
		}}
	}
	var project string
	ls := view("list", "all", "Tasks you can see")
	ls.RunE = func(_ *cobra.Command, _ []string) error { return a.workList("all", project) }
	ls.Flags().StringVar(&project, "project", "", "only this project (its id)")

	done := &cobra.Command{Use: "done PROJECT_ID TASK_ID", Short: "Mark a task done", Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			t, err := c.Work.Complete(bg(), args[0], args[1])
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, t)
			}
			if !a.G.Quiet {
				fmt.Fprintf(a.Stdout, "%s is now %s\n", t.ID, t.Status)
			}
			return nil
		}}
	root.AddCommand(add, ls, view("today", "today", "Tasks due today or overdue"),
		view("upcoming", "upcoming", "Tasks due after today"), view("inbox", "inbox", "Your Inbox"), done)
	return []*cobra.Command{root}
}

func (a *App) workList(view, project string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	tasks, err := c.Work.List(bg(), view, project, 100)
	if err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, tasks)
	}
	if len(tasks) == 0 {
		fmt.Fprintln(a.Stdout, "Nothing here.")
		return nil
	}
	rows := make([][]string, 0, len(tasks))
	for _, t := range tasks {
		rows = append(rows, []string{t.ProjectID, t.ID, t.Status, "p" + strconv.Itoa(t.Priority), sanitize(t.Title), dueSuffix(&t)})
	}
	return table(a.Stdout, "PROJECT\tID\tSTATUS\tPRIORITY\tTITLE\tDUE", rows)
}

func joinArgs(args []string) string {
	out := args[0]
	for _, s := range args[1:] {
		out += " " + s
	}
	return out
}

// localZone is the machine's IANA time zone name ($TZ, else the /etc/localtime link target), or "UTC".
// Dates in quick-add text ("today", "at 5pm") mean this zone unless --tz says otherwise.
func localZone() string {
	if name := os.Getenv("TZ"); name != "" {
		if _, err := time.LoadLocation(name); err == nil && name != "Local" {
			return name
		}
	}
	if link, err := filepath.EvalSymlinks("/etc/localtime"); err == nil {
		if _, after, ok := strings.Cut(filepath.ToSlash(link), "zoneinfo/"); ok {
			if _, err := time.LoadLocation(after); err == nil {
				return after
			}
		}
	}
	return "UTC"
}

// dueSuffix is "  due 2026-11-12 15:04 EST" or "", in the machine's zone (what localZone names).
func dueSuffix(t *onemind.WorkTask) string {
	if t.DueAt == nil {
		return ""
	}
	loc, err := time.LoadLocation(localZone())
	if err != nil {
		loc = time.UTC
	}
	return "  due " + t.DueAt.In(loc).Format("2006-01-02 15:04 MST")
}
