// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// aboutCommands is `onemind about`: the same facts as Settings > About this box in the dashboard
// (GET /v1/os/about, UMB-P14 #432). With --support it prints the block an owner pastes into a
// support request: no serial numbers and no addresses (the box never reports them), and no node
// ids unless --include-node-id says so.
func aboutCommands(a *App) []*cobra.Command {
	var support, ids bool
	c := &cobra.Command{
		Use:   "about",
		Short: "About this box: version, A/B slot, Debian base, kernel, CPU, memory, disk, uptime (GET /v1/os/about)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			ab, err := cl.About.Get(bg())
			if err != nil {
				return err
			}
			switch {
			case a.G.JSON:
				return printJSON(a.Stdout, ab)
			case support:
				_, err = fmt.Fprint(a.Stdout, SupportText(ab, ids))
				return err
			}
			rows := [][]string{}
			for _, n := range ab.Nodes {
				rows = append(rows, []string{n.NodeId, s(n.Hostname), s(n.OnemindVersion), s(n.BootedSlot), s(n.OsPretty), s(n.Kernel), s(n.Board), uptime(n.UptimeS)})
			}
			return table(a.Stdout, "NODE\tHOSTNAME\tONEMIND\tSLOT\tOS\tKERNEL\tBOARD\tUPTIME", rows)
		},
	}
	c.Flags().BoolVar(&support, "support", false, "print the text for a support request (no serials or addresses)")
	c.Flags().BoolVar(&ids, "include-node-id", false, "with --support: also print the node id")
	return []*cobra.Command{c}
}

func s(p *string) string { return dash(sanitize(deref(p))) }

func uptime(sec *int) string {
	if sec == nil {
		return "-"
	}
	d, h, m := *sec/86400, *sec%86400/3600, *sec%3600/60
	if d > 0 {
		return fmt.Sprintf("%dd %dh", d, h)
	}
	return fmt.Sprintf("%dh %dm", h, m)
}

func gb(p *float32) string {
	if p == nil {
		return "-"
	}
	return fmt.Sprintf("%.0f GB", *p)
}

func mem(p *int) string {
	if p == nil {
		return "-"
	}
	return fmt.Sprintf("%.1f GB", float64(*p)/1024)
}

// SupportText is the support-request block, one section per node. Serials and addresses are never
// in the API response; the node id is left out unless includeIDs is set.
func SupportText(ab *onemind.About, includeIDs bool) string {
	var b strings.Builder
	fmt.Fprintf(&b, "OneMind support details (%d node%s)\n", ab.NodeCount, map[bool]string{true: "", false: "s"}[ab.NodeCount == 1])
	for _, n := range ab.Nodes {
		b.WriteString("\n")
		if includeIDs {
			fmt.Fprintf(&b, "Node ID: %s\n", sanitize(n.NodeId))
		}
		for _, kv := range [][2]string{
			{"Hostname", s(n.Hostname)}, {"Board", s(n.Board)}, {"OneMind", s(n.OnemindVersion)}, {"A/B slot", s(n.BootedSlot)},
			{"OS", s(n.OsPretty)}, {"Kernel", s(n.Kernel)}, {"CPU", s(n.CpuModel)}, {"Memory", mem(n.MemTotalMb)},
			{"Disk", gb(n.DiskTotalGb) + " (" + gb(n.DiskFreeGb) + " free)"}, {"Uptime", uptime(n.UptimeS)},
		} {
			fmt.Fprintf(&b, "%s: %s\n", kv[0], kv[1])
		}
	}
	return b.String()
}
