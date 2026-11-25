// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"
	"strconv"

	"github.com/spf13/cobra"
)

// syncChange is one entry of GET /v1/sync/changes (the SyncChange schema in sdk/openapi).
type syncChange struct {
	ID       string  `json:"id"`
	ParentID *string `json:"parent_id"`
	Path     string  `json:"path"`
	Name     string  `json:"name"`
	Type     string  `json:"type"`
	Size     *int64  `json:"size"`
	Mtime    string  `json:"mtime"`
	Hash     *string `json:"hash"`
	Revision int64   `json:"revision"`
	Deleted  bool    `json:"deleted"`
}

type syncChanges struct {
	Root       string       `json:"root"`
	Revision   int64        `json:"revision"`
	Changes    []syncChange `json:"changes"`
	NextCursor string       `json:"next_cursor"`
	HasMore    bool         `json:"has_more"`
}

// syncCommands is `onemind sync` (#698): read-only views of the hub sync contract. `sync changes`
// prints one page of a root's change feed; pass the printed cursor back to see what changed after it.
func syncCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "sync", Short: "The hub sync contract: file ids, revisions and the change feed (read-only)"}
	var space, cursor string
	var limit int
	changes := &cobra.Command{
		Use:   "changes",
		Short: "What changed in a root since a cursor (GET /v1/sync/changes); no cursor lists every entry",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			q := url.Values{"root": {space}, "limit": {strconv.Itoa(limit)}}
			if cursor != "" {
				q.Set("cursor", cursor)
			}
			var v syncChanges
			if err := c.Do(bg(), http.MethodGet, "/v1/sync/changes?"+q.Encode(), nil, &v); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			rows := [][]string{}
			for _, e := range v.Changes {
				what := e.Type
				if e.Deleted {
					what = "deleted"
				}
				size := "-"
				if e.Size != nil {
					size = strconv.FormatInt(*e.Size, 10)
				}
				rows = append(rows, []string{strconv.FormatInt(e.Revision, 10), e.ID, what, size, e.Path})
			}
			if err := table(a.Stdout, "REV\tID\tTYPE\tSIZE\tPATH", rows); err != nil {
				return err
			}
			more := ""
			if v.HasMore {
				more = " (more: run again with this cursor)"
			}
			_, err = fmt.Fprintf(a.Stdout, "\nroot %s at revision %d\nnext cursor: %s%s\n", sanitize(v.Root), v.Revision, sanitize(v.NextCursor), more)
			return err
		},
	}
	changes.Flags().StringVar(&space, "root", "", "the root: shared or home:<person_id>")
	changes.Flags().StringVar(&cursor, "cursor", "", "the next cursor a previous call printed")
	changes.Flags().IntVar(&limit, "limit", 500, "most entries in one page (1 to 1000)")
	_ = changes.MarkFlagRequired("root")
	root.AddCommand(changes)
	return []*cobra.Command{root}
}
