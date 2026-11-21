// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// printUsage is `onemind status --usage` (UMB-P11, #429): the numbers the dashboard's Live usage
// panel shows, from GET /v1/usage. A reading that is old says so; a number the box does not report is
// a dash, never 0. Read-only.
func (a *App) printUsage(c *onemind.Client) error {
	u, err := c.Nodes.Usage(bg())
	if err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, u)
	}
	num := func(v *float32, unit string) string {
		if v == nil {
			return "-"
		}
		return fmt.Sprintf("%.1f%s", *v, unit)
	}
	of := func(used, total *float32, unit string) string {
		if used == nil || total == nil {
			return "-"
		}
		return fmt.Sprintf("%.1f / %.1f %s", *used, *total, unit)
	}
	rows := [][]string{}
	for _, n := range u.Nodes {
		state := n.Status
		if n.Stale {
			state = fmt.Sprintf("%s (STALE: last heard %ds ago)", n.Status, n.AgeS)
		}
		rows = append(rows, []string{n.NodeId, dash(deref(n.Hostname)), num(n.CpuPct, "%"),
			of(n.MemUsedMb, n.MemTotalMb, "MB"), of(n.DiskUsedGb, n.DiskTotalGb, "GB"), num(n.TempC, "C"), state})
	}
	if err := table(a.Stdout, "NODE_ID\tHOSTNAME\tCPU\tMEMORY\tDISK\tTEMP\tSTATE", rows); err != nil {
		return err
	}
	fmt.Fprintln(a.Stdout)
	switch {
	case u.Apps.Source == "unavailable":
		fmt.Fprintln(a.Stdout, "Apps: this box has no app runtime to read (nothing is shown, nothing is guessed).")
		return nil
	case u.Apps.Stale:
		fmt.Fprintf(a.Stdout, "Apps: STALE, last read %s; the runtime has not answered since.\n", dash(deref(u.Apps.SampledAt)))
	}
	apps := [][]string{}
	for _, x := range u.Apps.Items {
		apps = append(apps, []string{x.AppId, num(x.CpuMillicores, "m"), num(x.MemMb, "MB"), num(x.DiskMb, "MB")})
	}
	return table(a.Stdout, "APP\tCPU\tMEMORY\tDISK", apps)
}
