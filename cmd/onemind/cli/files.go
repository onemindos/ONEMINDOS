// SPDX-License-Identifier: Apache-2.0

package cli

// onemind files: reads and the owner's storage limits over the gateway (/v1/files/*). `stat` shows one file or
// folder; `quotas list` shows each person's limit and use, `quotas set` changes one person's limit. Both quota
// calls are owner only (the gateway answers 403 to anyone else). Nothing here deletes or shares a file.

import (
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/spf13/cobra"
)

const gib = 1 << 30

func filesCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "files", Short: "Your files: details of one file, and storage limits per person (owner)"}

	var rootID string
	stat := &cobra.Command{
		Use:   "stat PATH",
		Short: "Details of one file or folder (GET /v1/files/stat); the space defaults to your own files",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			q := url.Values{"path": {args[0]}}
			if rootID != "" {
				q.Set("root", rootID)
			}
			return a.read("/v1/files/stat?"+q.Encode(), func(w io.Writer, v any) error {
				m := obj(v)
				return kv(w, [][2]string{
					{"name", str(m["name"])}, {"path", str(m["path"])}, {"space", str(m["root"])}, {"type", str(m["type"])},
					{"size", dash(str(m["size"]))}, {"modified", dash(str(m["mtime"]))}, {"access", str(m["access"])},
				})
			})
		},
	}
	stat.Flags().StringVar(&rootID, "root", "", "the space, for example home:<person> or shared (default: your own files)")
	root.AddCommand(stat)

	quotas := &cobra.Command{Use: "quotas", Short: "How much each person's files may use (owner)"}
	quotas.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Each space's limit and use (GET /v1/files/quotas)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/files/quotas", func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, q := range list(v) {
					m := obj(q)
					limit := "no limit"
					if f, ok := m["limit_bytes"].(float64); ok {
						limit = gbText(f)
					}
					used := 0.0
					if f, ok := m["used_bytes"].(float64); ok {
						used = f
					}
					rows = append(rows, []string{dash(str(m["person_id"])), str(m["root"]), gbText(used), limit})
				}
				return table(w, "PERSON\tSPACE\tUSED\tLIMIT", rows)
			})
		},
	})
	var gb float64
	var none bool
	set := &cobra.Command{
		Use:   "set PERSON (--gb N | --none)",
		Short: "Set one person's limit in GB, or --none for no limit (PUT /v1/files/quotas/PERSON)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if none == cmd.Flags().Changed("gb") {
				return usageErr(cmd, "give exactly one of --gb N or --none")
			}
			var limit any
			if !none {
				if math.IsNaN(gb) || math.IsInf(gb, 0) || gb < 0 || gb > 1e9 {
					return usageErr(cmd, "--gb must be a number from 0 up")
				}
				limit = int64(math.Round(gb * gib))
			}
			v, err := a.gwDo(http.MethodPut, "/v1/files/quotas/"+url.PathEscape(args[0]), map[string]any{"limit_bytes": limit})
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				m := obj(v)
				text := "no limit"
				if f, ok := m["limit_bytes"].(float64); ok {
					text = gbText(f)
				}
				_, err := fmt.Fprintf(w, "Limit for %s is now %s.\n", sanitize(args[0]), text)
				return err
			})
		},
	}
	set.Flags().Float64Var(&gb, "gb", 0, "the limit in GB")
	set.Flags().BoolVar(&none, "none", false, "remove the limit")
	quotas.AddCommand(set)
	root.AddCommand(quotas)
	return []*cobra.Command{root}
}

// gbText prints bytes as GB with at most two decimals ("1.5 GB").
func gbText(b float64) string {
	return strings.TrimRight(strings.TrimRight(strconv.FormatFloat(b/gib, 'f', 2, 64), "0"), ".") + " GB"
}
