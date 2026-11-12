// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

func appsCommands(a *App) []*cobra.Command {
	apps := &cobra.Command{Use: "apps", Short: "Apps on a box (the Market catalog and what is installed)"}
	var installed bool
	var category string
	list := &cobra.Command{
		Use:   "list",
		Short: "The catalog with install status (GET /v1/apps)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			keep := func(cat string, inst bool) bool {
				return (category == "" || cat == category) && (!installed || inst)
			}
			if a.G.JSON {
				var raw []map[string]any
				if err := c.Do(bg(), http.MethodGet, "/v1/apps", nil, &raw); err != nil {
					return err
				}
				out := []map[string]any{}
				for _, x := range raw {
					cat, _ := x["category"].(string)
					inst, _ := x["installed"].(bool)
					if keep(cat, inst) {
						out = append(out, x)
					}
				}
				return printJSON(a.Stdout, out)
			}
			all, err := c.Apps.List(bg())
			if err != nil {
				return err
			}
			var rows [][]string
			for _, x := range all {
				if !keep(deref(x.Category), x.Installed) {
					continue
				}
				tier, scan := "-", "none"
				if x.Tier != nil {
					tier = string(*x.Tier)
				}
				if x.Scan != nil {
					scan = string(x.Scan.Result) + " " + age(x.Scan.ScannedAt, time.Now()) + " ago"
				}
				rows = append(rows, []string{x.Id, deref(x.Name), deref(x.Version), dash(deref(x.Category)), tier, scan, x.Status})
			}
			return table(a.Stdout, "ID\tNAME\tVERSION\tCATEGORY\tTIER\tSCAN\tSTATUS", rows)
		},
	}
	list.Flags().BoolVar(&installed, "installed", false, "only installed apps")
	list.Flags().StringVar(&category, "category", "", "only this category")

	info := &cobra.Command{
		Use:   "info APP_ID",
		Short: "One catalog entry",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if a.G.JSON {
				var raw []map[string]any
				if err := c.Do(bg(), http.MethodGet, "/v1/apps", nil, &raw); err != nil {
					return err
				}
				for _, x := range raw {
					if x["id"] == args[0] {
						return printJSON(a.Stdout, x)
					}
				}
				return exitWith(ExitNotFound, "not_found", fmt.Sprintf("app %q is not in the catalog", args[0]))
			}
			x, err := c.Apps.Get(bg(), args[0])
			if err != nil {
				return err
			}
			return kv(a.Stdout, appFacts(x))
		},
	}
	install := requestCommand(a, onemind.ActionAppInstall, "install APP_ID", "Request an install, then approve it (owners)")
	remove := requestCommand(a, onemind.ActionAppRemove, "remove APP_ID", "Request a removal, then approve it (owners)")
	apps.AddCommand(list, info, install, remove)
	return []*cobra.Command{apps}
}

func appFacts(x *onemind.CatalogApp) [][2]string {
	tier, scan := "none", "none (install is refused without a passing scan)"
	if x.Tier != nil {
		tier = string(*x.Tier)
	}
	if x.Scan != nil {
		scan = fmt.Sprintf("%s, %s ago", x.Scan.Result, age(x.Scan.ScannedAt, time.Now()))
	}
	web := "-"
	if x.WebPort != nil {
		web = fmt.Sprintf("port %d", *x.WebPort)
	}
	return [][2]string{
		{"id", x.Id}, {"name", deref(x.Name)}, {"version", deref(x.Version)}, {"category", dash(deref(x.Category))},
		{"description", deref(x.Description)}, {"licence", dash(deref(x.License))}, {"source", dash(deref(x.Source))},
		{"archs", strings.Join(x.Archs, ", ")}, {"web", web}, {"tier", tier}, {"scan", scan}, {"status", x.Status},
	}
}

// requestCommand is `apps install` / `apps remove`: request, then (owners) approve in the same
// session. Two audit entries: requested by you, approved by you (CLI.md §6.3).
func requestCommand(a *App, typ, use, short string) *cobra.Command {
	var noApprove, yes bool
	var wait time.Duration
	cmd := &cobra.Command{
		Use:   use,
		Short: short,
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			waitSet := cmd.Flags().Changed("wait")
			if !noApprove && !yes && !a.Interactive() {
				return exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --no-approve to only file the request (or --yes to approve it as the owner)")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			app, err := c.Apps.Get(bg(), args[0])
			if err != nil {
				return err
			}
			act, err := c.Actions.Request(bg(), onemind.ActionRequest{Type: typ, AppID: args[0]})
			if err != nil {
				return err
			}
			if !a.G.JSON {
				fmt.Fprintf(a.Stdout, "Requested action %s  %s %s %s\n", act.Id, typ, app.Id, deref(app.Version))
				fmt.Fprintln(a.Stdout, "What the box will do (from the catalog and scan record; gateway-computed effects come with the install sandbox):")
				ns := "app-" + app.Id
				if typ == onemind.ActionAppRemove {
					fmt.Fprintf(a.Stdout, "  delete namespace %s\n", ns)
				} else {
					facts := appFacts(app)
					fmt.Fprintf(a.Stdout, "  namespace %s · licence %s · tier %s · scan %s\n", ns, facts[5][1], facts[9][1], facts[10][1])
				}
			}
			if noApprove {
				if waitSet {
					return a.waitAction(c, act.Id, wait)
				}
				if a.G.JSON {
					return printJSON(a.Stdout, act)
				}
				if a.G.Quiet {
					fmt.Fprintln(a.Stdout, act.Id)
				} else {
					fmt.Fprintf(a.Stdout, "Waiting for an owner: onemind actions approve %s\n", act.Id)
				}
				return nil
			}
			ok := yes
			if !ok {
				if typ == onemind.ActionAppRemove {
					ok, err = a.confirmTyped("Approve the removal?", app.Id, "--yes")
				} else {
					ok, err = a.confirm("Approve now?", "--yes")
				}
				if err != nil {
					return err
				}
			}
			if !ok {
				return exitWith(ExitPending, "pending", fmt.Sprintf("left waiting for approval: onemind actions approve %s", act.Id))
			}
			if _, err := c.Actions.Approve(bg(), act.Id); err != nil {
				if errors.Is(err, onemind.ErrPermissionDenied) {
					return exitWith(ExitPermissionDenied, "permission_denied",
						fmt.Sprintf("requested %s, but this principal may not approve; an owner runs: onemind actions approve %s", act.Id, act.Id))
				}
				return err
			}
			if !waitSet {
				wait = 10 * time.Minute
			}
			return a.waitAction(c, act.Id, wait)
		},
	}
	cmd.Flags().BoolVar(&noApprove, "no-approve", false, "only file the request (scripts, agents, non-owners)")
	cmd.Flags().BoolVar(&yes, "yes", false, "approve without asking (v0: owner token approvals; passkey step-up replaces this, §12.3)")
	cmd.Flags().DurationVar(&wait, "wait", 10*time.Minute, "wait for the outcome (default 10m)")
	cmd.Flags().Lookup("wait").NoOptDefVal = "10m"
	return cmd
}

// waitAction follows an action to its end, printing each state, and maps it to an exit code.
func (a *App) waitAction(c *onemind.Client, id string, d time.Duration) error {
	ctx, cancel := ctxTimeout(d)
	defer cancel()
	start := time.Now()
	var states []string
	final, err := c.Actions.Wait(ctx, id, 2*time.Second, func(x *onemind.Action) {
		states = append(states, x.State)
		if !a.G.JSON && !a.G.Quiet {
			fmt.Fprintf(a.Stderr, "  %s\n", x.State)
		}
	})
	if final == nil {
		return err
	}
	if a.G.JSON {
		if perr := printJSON(a.Stdout, final); perr != nil {
			return perr
		}
	} else if onemind.Terminal(final.State) {
		fmt.Fprintf(a.Stdout, "%s in %s\n", strings.Join(states, " · "), time.Since(start).Round(time.Second))
	}
	return exitForState(final.State)
}
