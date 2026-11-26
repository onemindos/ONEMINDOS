// SPDX-License-Identifier: Apache-2.0

package cli

// onemind work project-add, edit and delete: the Work writes that had a route and no command
// (POST /v1/work/projects, PATCH and DELETE on a task). They act on the signed-in person's own Work;
// an edit or delete reads the task's revision first and sends it in If-Match, so a task changed
// meanwhile is refused (409) rather than overwritten.

import (
	"fmt"
	"time"

	"github.com/spf13/cobra"
)

func (a *App) workEdit() []*cobra.Command {
	var access string
	add := &cobra.Command{Use: "project-add NAME", Short: "Create a project (POST /v1/work/projects)", Args: cobra.MinimumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			name := ""
			for i, w := range args {
				if i > 0 {
					name += " "
				}
				name += w
			}
			p, err := c.Work.CreateProject(bg(), name, access, "")
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, p)
			}
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, p.ID)
				return nil
			}
			fmt.Fprintf(a.Stdout, "Created project %s (%s, AI access %s)\n", p.ID, sanitize(p.Name), p.AIAccess)
			return nil
		}}
	add.Flags().StringVar(&access, "ai-access", "", "what an AI agent may do in it: none (default), read or work")

	var title, body, due, status string
	var priority int
	edit := &cobra.Command{Use: "edit PROJECT_ID TASK_ID", Short: "Change a task's title, notes, due time, priority or status (PATCH, with the revision just read)",
		Args: cobra.ExactArgs(2), RunE: func(cmd *cobra.Command, args []string) error {
			changes := map[string]any{}
			f := cmd.Flags()
			if f.Changed("title") {
				if title == "" {
					return usageErr(cmd, "--title cannot be empty")
				}
				changes["title"] = title
			}
			if f.Changed("body") {
				changes["body"] = body
			}
			if f.Changed("priority") {
				if priority < 1 || priority > 4 {
					return usageErr(cmd, "--priority is 1 (most urgent) to 4")
				}
				changes["priority"] = priority
			}
			if f.Changed("due") {
				if due == "none" {
					changes["due_at"] = nil
				} else if t, err := time.Parse(time.RFC3339, due); err != nil {
					return usageErr(cmd, "--due is a time like 2026-12-01T17:00:00Z, or none to clear it")
				} else {
					changes["due_at"] = t.UTC().Format(time.RFC3339)
				}
			}
			if f.Changed("status") {
				if status != "todo" && status != "in_progress" && status != "done" {
					return usageErr(cmd, "--status is todo, in_progress or done")
				}
				changes["status"] = status
			}
			if len(changes) == 0 {
				return usageErr(cmd, "nothing to change: give --title, --body, --priority, --due or --status")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			t, err := c.Work.UpdateTask(bg(), args[0], args[1], changes)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, t)
			}
			if !a.G.Quiet {
				fmt.Fprintf(a.Stdout, "Updated %s: %s (%s)\n", t.ID, sanitize(t.Title), t.Status)
			}
			return nil
		}}
	edit.Flags().StringVar(&title, "title", "", "new title")
	edit.Flags().StringVar(&body, "body", "", "new notes (empty clears them)")
	edit.Flags().IntVar(&priority, "priority", 4, "1 (most urgent) to 4")
	edit.Flags().StringVar(&due, "due", "", "due time (RFC 3339), or none to clear")
	edit.Flags().StringVar(&status, "status", "", "todo, in_progress or done")

	del := &cobra.Command{Use: "delete PROJECT_ID TASK_ID", Short: "Delete a task (DELETE, with the revision just read)", Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Work.DeleteTask(bg(), args[0], args[1]); err != nil {
				return err
			}
			if !a.G.JSON && !a.G.Quiet {
				fmt.Fprintf(a.Stdout, "Deleted %s\n", args[1])
			}
			return nil
		}}
	return []*cobra.Command{add, edit, del}
}
