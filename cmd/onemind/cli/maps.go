// SPDX-License-Identifier: Apache-2.0

package cli

// onemind map and onemind subjects. `map packs list` and `map sites list` read (GET /v1/map/packs, GET /v1/sites).
// `map packs add` and `remove` only FILE a request (map.pack.add / map.pack.remove) that waits for an owner; nothing
// is downloaded or deleted until it is approved. `subjects list` and `subjects check` read the event subject tree and
// never publish anything.

import (
	"fmt"
	"io"
	"net/url"
	"strconv"
	"strings"

	"github.com/spf13/cobra"
)

func mapCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "map", Short: "Offline maps: installed packs and map sites"}
	packs := &cobra.Command{Use: "packs", Short: "Offline map packs (adding or removing waits for an owner)"}
	packs.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The installed map packs and the free map disk (GET /v1/map/packs)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/map/packs", func(w io.Writer, v any) error {
				m := obj(v)
				if f, ok := m["free_bytes"].(float64); ok {
					fmt.Fprintf(w, "free for map packs: %s\n", mapGB(f))
				} else {
					fmt.Fprintln(w, "free for map packs: - (Offline Maps is not set up on this box)")
				}
				rows := [][]string{}
				for _, p := range list(m["packs"]) {
					pm := obj(p)
					size := "-"
					if f, ok := pm["bytes"].(float64); ok {
						size = fmt.Sprintf("%.0f MB", f/1e6)
					}
					rows = append(rows, []string{str(pm["id"]), sanitize(str(pm["region"])), size, str(pm["installed_at"])})
				}
				return table(w, "PACK\tREGION\tSIZE\tINSTALLED", rows)
			})
		},
	})
	var reason string
	add := &cobra.Command{
		Use:   "add REGION_ID",
		Short: "Request downloading a map region; an owner approves it (POST /v1/actions, map.pack.add)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.fileAction("map.pack.add", map[string]any{"region_id": args[0]}, reason, "Map pack download")
		},
	}
	rm := &cobra.Command{
		Use:   "remove PACK_ID",
		Short: "Request deleting an installed pack; an owner approves it (POST /v1/actions, map.pack.remove)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.fileAction("map.pack.remove", map[string]any{"pack_id": args[0]}, reason, "Map pack removal")
		},
	}
	for _, c := range []*cobra.Command{add, rm} {
		c.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")
		packs.AddCommand(c)
	}
	root.AddCommand(packs)

	sites := &cobra.Command{Use: "sites", Short: "Map sites: buildings and properties with floors and areas"}
	sites.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The map sites (GET /v1/sites)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/sites", func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, s := range list(v) {
					m := obj(s)
					rows = append(rows, []string{str(m["id"]), sanitize(str(m["name"])), fmt.Sprint(len(list(m["floors"]))), fmt.Sprint(len(list(m["areas"])))})
				}
				return table(w, "ID\tNAME\tFLOORS\tAREAS", rows)
			})
		},
	})
	root.AddCommand(sites)
	return []*cobra.Command{root}
}

func subjectsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "subjects", Short: "The event subject tree: who may send which messages (read only)"}
	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every message kind, who may send it, its stream and how long it is kept (GET /v1/subjects)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/subjects", func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, k := range list(obj(v)["kinds"]) {
					m := obj(k)
					pubs := map[string]bool{}
					for _, s := range list(m["subjects"]) {
						for _, p := range list(obj(s)["publishers"]) {
							pubs[str(p)] = true
						}
					}
					names := []string{}
					for _, p := range []string{"gateway", "node", "app", "agent"} {
						if pubs[p] {
							names = append(names, p)
						}
					}
					rows = append(rows, []string{sanitize(str(m["kind"])), dash(strings.Join(names, ",")), dash(str(m["stream"])), str(obj(m["retention"])["policy"])})
				}
				return table(w, "KIND\tPUBLISHERS\tSTREAM\tKEPT", rows)
			})
		},
	})
	var publisher, owner string
	check := &cobra.Command{
		Use:   "check SUBJECT [--publisher gateway|node|app|agent] [--owner-id ID]",
		Short: "Would this sender be allowed to publish on SUBJECT? It only answers (GET /v1/subjects/check)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			switch publisher {
			case "gateway", "node", "app", "agent":
			default:
				return usageErr(cmd, "--publisher must be gateway, node, app or agent")
			}
			q := url.Values{"subject": {args[0]}, "publisher": {publisher}}
			if owner != "" {
				q.Set("owner_id", owner)
			}
			return a.read("/v1/subjects/check?"+q.Encode(), func(w io.Writer, v any) error {
				m := obj(v)
				verdict := "not allowed"
				if m["ok"] == true {
					verdict = "allowed"
				}
				return kv(w, [][2]string{{"verdict", verdict}, {"reason", sanitize(str(m["reason"]))}, {"kind", dash(str(m["kind"]))}, {"pattern", dash(str(m["pattern"]))}})
			})
		},
	}
	check.Flags().StringVar(&publisher, "publisher", "app", "who sends: gateway, node, app or agent")
	check.Flags().StringVar(&owner, "owner-id", "", "the sender's own node, app or agent id")
	root.AddCommand(check)
	return []*cobra.Command{root}
}

// mapGB prints bytes as GB with at most two decimals ("20.5 GB").
func mapGB(b float64) string {
	return strings.TrimRight(strings.TrimRight(strconv.FormatFloat(b/1e9, 'f', 2, 64), "0"), ".") + " GB"
}
