// SPDX-License-Identifier: Apache-2.0

package cli

// onemind search: one query over what the signed-in person may see on the box (GET /v1/search):
// files, settings and the items apps offer. It reads and changes nothing. The gateway filters every
// hit by the caller's own grants, and never logs the words searched.

import (
	"io"
	"net/url"
	"strconv"
	"strings"

	"github.com/spf13/cobra"
)

func searchCommands(a *App) []*cobra.Command {
	var types string
	var limit int
	c := &cobra.Command{
		Use:   "search WORDS...",
		Short: "Search files, settings and app items you may see (GET /v1/search); every word must match",
		Args:  cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			q := strings.TrimSpace(strings.Join(args, " "))
			if q == "" || len(q) > 200 {
				return usageErr(cmd, "give 1 to 200 characters to search for")
			}
			if limit < 1 || limit > 100 {
				return usageErr(cmd, "--limit must be between 1 and 100")
			}
			path := "/v1/search?q=" + url.QueryEscape(q) + "&limit=" + strconv.Itoa(limit)
			if types != "" {
				path += "&types=" + url.QueryEscape(types)
			}
			return a.read(path, func(w io.Writer, v any) error {
				hits := list(v)
				if len(hits) == 0 {
					_, err := io.WriteString(w, "Nothing found. Every word must match; items you may not see are never listed.\n")
					return err
				}
				var rows [][]string
				for _, h := range hits {
					m := obj(h)
					rows = append(rows, []string{str(m["type"]), str(m["title"]), dash(str(m["subtitle"])), str(m["link"])})
				}
				return table(w, "TYPE\tTITLE\tDETAIL\tLINK", rows)
			})
		},
	}
	c.Flags().StringVar(&types, "types", "", "only these kinds, comma-separated (for example file,folder)")
	c.Flags().IntVar(&limit, "limit", 20, "most results to show (1 to 100)")
	return []*cobra.Command{c}
}
