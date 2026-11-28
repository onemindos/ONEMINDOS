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
	root.AddCommand(a.workManage()...)
	root.AddCommand(add, ls, view("today", "today", "Tasks due today or overdue"),
		view("upcoming", "upcoming", "Tasks due after today"), view("inbox", "inbox", "Your Inbox"), done)
	return []*cobra.Command{root}
}

func (a *App) workList(view, project string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	tasks, err := c.Work.List(bg(), view, project, localZone(), 100)
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
	if t.Repeat != nil && t.DueAt != nil {
		return dueOnly(t) + "  repeats every " + strconv.Itoa(max(t.Repeat.Interval, 1)) + " " + t.Repeat.Every
	}
	return dueOnly(t)
}

func dueOnly(t *onemind.WorkTask) string {
	if t.DueAt == nil {
		return ""
	}
	loc, err := time.LoadLocation(localZone())
	if err != nil {
		loc = time.UTC
	}
	return "  due " + t.DueAt.In(loc).Format("2006-01-02 15:04 MST")
}

// workManage is the project, member, preview and history commands of `onemind work`.
func (a *App) workManage() []*cobra.Command {
	var tz, name, access string
	projects := &cobra.Command{Use: "projects", Short: "Projects you belong to", Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			list, err := c.Work.Projects(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, list)
			}
			rows := make([][]string, 0, len(list))
			for _, p := range list {
				rows = append(rows, []string{p.ID, sanitize(p.Name), p.AIAccess})
			}
			return table(a.Stdout, "ID\tNAME\tAI ACCESS", rows)
		}}
	rename := &cobra.Command{Use: "project-edit PROJECT_ID", Short: "Rename a project or set what AI may see (creator only)",
		Args: cobra.ExactArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			p, err := c.Work.UpdateProject(bg(), args[0], name, access)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, p)
			}
			fmt.Fprintf(a.Stdout, "%s is now %q (AI access %s)\n", p.ID, sanitize(p.Name), p.AIAccess)
			return nil
		}}
	rename.Flags().StringVar(&name, "name", "", "new name")
	rename.Flags().StringVar(&access, "ai-access", "", "none, read or work")
	remove := &cobra.Command{Use: "project-delete PROJECT_ID", Short: "Delete a project and its tasks (creator only)",
		Args: cobra.ExactArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			return c.Work.DeleteProject(bg(), args[0])
		}}
	member := func(use, short string, call func(c *onemind.Client, project, person string) error) *cobra.Command {
		return &cobra.Command{Use: use + " PROJECT_ID PERSON_ID", Short: short, Args: cobra.ExactArgs(2),
			RunE: func(_ *cobra.Command, args []string) error {
				c, _, err := a.client()
				if err != nil {
					return err
				}
				return call(c, args[0], args[1])
			}}
	}
	parse := &cobra.Command{Use: "parse TEXT", Short: "Preview what a quick-add line would become", Args: cobra.MinimumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if tz == "" {
				tz = localZone()
			}
			p, err := c.Work.Parse(bg(), joinArgs(args), tz)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, p)
			}
			fmt.Fprintf(a.Stdout, "title %q  labels %v  project found %v\n", sanitize(p.Title), p.Labels, p.ProjectFound)
			return nil
		}}
	parse.Flags().StringVar(&tz, "tz", "", "time zone for dates (default this machine's zone)")
	activity := &cobra.Command{Use: "activity PROJECT_ID TASK_ID", Short: "What changed on a task, newest first", Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			log, err := c.Work.Activity(bg(), args[0], args[1])
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, log)
			}
			rows := make([][]string, 0, len(log))
			for _, e := range log {
				rows = append(rows, []string{e.At.Local().Format("2006-01-02 15:04"), e.ActorID, e.Kind, strings.Join(e.Fields, ",")})
			}
			return table(a.Stdout, "WHEN\tWHO\tWHAT\tFIELDS", rows)
		}}
	return []*cobra.Command{projects, rename, remove, parse, activity, a.workNotes(),
		member("member-add", "Add a person to a project (creator only)", func(c *onemind.Client, p, who string) error {
			return c.Work.AddMember(bg(), p, who)
		}),
		member("member-remove", "Remove a person from a project (creator only)", func(c *onemind.Client, p, who string) error {
			return c.Work.RemoveMember(bg(), p, who)
		})}
}

// workNotes is `onemind work notes` (comments on a task) and `onemind work sections`.
func (a *App) workNotes() *cobra.Command {
	var key string
	notes := &cobra.Command{Use: "notes", Short: "Comments on a task and sections of a project"}
	list := &cobra.Command{Use: "list PROJECT_ID TASK_ID", Short: "Comments on a task, oldest first", Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := c.Work.Comments(bg(), args[0], args[1])
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			rows := make([][]string, 0, len(v))
			for _, n := range v {
				rows = append(rows, []string{n.ID, n.AuthorID, n.CreatedAt.Local().Format("2006-01-02 15:04"), sanitize(n.Body)})
			}
			return table(a.Stdout, "ID\tWHO\tWHEN\tCOMMENT", rows)
		}}
	add := &cobra.Command{Use: "add PROJECT_ID TASK_ID TEXT", Short: "Comment on a task", Args: cobra.MinimumNArgs(3),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			n, err := c.Work.AddComment(bg(), args[0], args[1], joinArgs(args[2:]), key)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, n)
			}
			fmt.Fprintf(a.Stdout, "Added %s\n", n.ID)
			return nil
		}}
	add.Flags().StringVar(&key, "idempotency-key", "", "send the same key again to retry without adding a second comment")
	del := &cobra.Command{Use: "delete PROJECT_ID TASK_ID COMMENT_ID", Short: "Delete your comment", Args: cobra.ExactArgs(3),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			return c.Work.DeleteComment(bg(), args[0], args[1], args[2])
		}}
	sections := &cobra.Command{Use: "sections PROJECT_ID", Short: "Sections of a project", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := c.Work.Sections(bg(), args[0])
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			rows := make([][]string, 0, len(v))
			for _, sec := range v {
				rows = append(rows, []string{sec.ID, strconv.Itoa(sec.Position), sanitize(sec.Name)})
			}
			return table(a.Stdout, "ID\tPOSITION\tNAME", rows)
		}}
	secAdd := &cobra.Command{Use: "section-add PROJECT_ID NAME", Short: "Add a section to a project", Args: cobra.MinimumNArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			sec, err := c.Work.AddSection(bg(), args[0], joinArgs(args[1:]), key)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, sec)
			}
			fmt.Fprintf(a.Stdout, "Added %s\n", sec.ID)
			return nil
		}}
	secAdd.Flags().StringVar(&key, "idempotency-key", "", "send the same key again to retry without adding a second section")
	secDel := &cobra.Command{Use: "section-delete PROJECT_ID SECTION_ID", Short: "Delete a section (its tasks stay)", Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			return c.Work.DeleteSection(bg(), args[0], args[1])
		}}
	notes.AddCommand(list, add, del, sections, secAdd, secDel)
	return notes
}
