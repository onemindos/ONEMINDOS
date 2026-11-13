// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

func statusCommands(a *App) []*cobra.Command {
	return []*cobra.Command{{
		Use:   "status",
		Short: "One-screen health of the current box",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			ctx := bg()
			inst, err := c.Instance.Get(ctx)
			if err != nil {
				return err
			}
			nodes, err := c.Nodes.List(ctx)
			if err != nil {
				return err
			}
			counts := map[string]int{"online": 0, "stale": 0, "offline": 0}
			for _, n := range nodes {
				counts[n.Status]++
			}
			var pending *int
			if acts, err := c.Actions.List(ctx); err == nil {
				p := 0
				for _, x := range acts {
					if x.State == "awaiting_approval" {
						p++
					}
				}
				pending = &p
			}
			var audit map[string]any
			if v, err := c.Audit.Verify(ctx); err == nil {
				audit = map[string]any{"ok": v.Ok, "records": v.Records, "head": v.Head, "first_bad_seq": v.FirstBadSeq}
			} else if !errors.Is(err, onemind.ErrPermissionDenied) && !errors.Is(err, onemind.ErrNotFound) {
				return err
			}
			if a.G.JSON {
				var acts any
				if pending != nil {
					acts = map[string]int{"awaiting_approval": *pending}
				}
				return printJSON(a.Stdout, map[string]any{
					"schema": "onemind.cli.status/v1", "hub": c.BaseURL(), "instance": inst, "nodes": counts,
					"actions": acts, "update": nil, "backup": nil, "audit": audit,
				})
			}
			hubNode := dash(deref(inst.HubNodeId))
			lines := [][2]string{
				{"Box", fmt.Sprintf("%s · OneMind %s · hub node %s", inst.Name, inst.Version, hubNode)},
				{"Nodes", fmt.Sprintf("%d online · %d stale · %d offline", counts["online"], counts["stale"], counts["offline"])},
			}
			if pending != nil {
				hint := ""
				if *pending > 0 {
					hint = "  → onemind actions list --pending"
				}
				lines = append(lines, [2]string{"Approvals", fmt.Sprintf("%d waiting%s", *pending, hint)})
			}
			lines = append(lines, [2]string{"Updates", "not available over the API yet (on the box: onemind update status)"},
				[2]string{"Backups", "not available on this box"})
			switch {
			case audit == nil:
				lines = append(lines, [2]string{"Audit", "not visible to this principal"})
			case audit["ok"] == true:
				head := audit["head"].(*onemind.AuditHead)
				seq, h := 0, ""
				if head != nil {
					seq, h = head.Seq, head.Hash
					if len(h) > 12 {
						h = h[:12] + "…"
					}
				}
				lines = append(lines, [2]string{"Audit", fmt.Sprintf("seq %d, chain ok (sha256:%s)", seq, h)})
			default:
				lines = append(lines, [2]string{"Audit", fmt.Sprintf("CHAIN BROKEN at seq %v: run onemind audit verify", *audit["first_bad_seq"].(*int))})
			}
			return kv(a.Stdout, lines)
		},
	}}
}
