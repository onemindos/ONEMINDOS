// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind grants` (UI parity M3, #1232): the CLI side of Settings > Permissions > Data access and Hardware access.
// `data list|revoke` is GET /v1/data/grants and DELETE /v1/data/grants/{id} (the data commons, #615); `host
// list|revoke` is GET /v1/host-grants and POST /v1/host-grants/{id}/revoke (#186 E2). Grants are asked for as
// approval-queue actions (data.grant, host.grant) and only an owner approves them; this group does not ask for
// any. Revoking only takes access away, so it is the owner-only call the gateway already audits, like `sessions
// revoke`; the gateway refuses it for anyone else, an AI agent included.

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type dataGrant struct {
	ID        string `json:"id"`
	DataClass string `json:"data_class"`
	Grantee   struct {
		Kind string `json:"kind"`
		ID   string `json:"id"`
	} `json:"grantee"`
	Read      bool   `json:"read"`
	Write     bool   `json:"write"`
	Aggregate bool   `json:"aggregate"`
	ExpiresAt string `json:"expires_at"`
	Active    bool   `json:"active"`
}

type hostGrant struct {
	ID          string  `json:"id"`
	AppID       string  `json:"app_id"`
	Kind        string  `json:"kind"`
	DeviceClass *string `json:"device_class"`
	Path        *string `json:"path"`
	Reason      string  `json:"reason"`
	Active      bool    `json:"active"`
	GrantedAt   string  `json:"granted_at"`
}

// grantAllows says what a data grant allows: "read, count".
func grantAllows(g dataGrant) string {
	var can []string
	if g.Read {
		can = append(can, "read")
	}
	if g.Write {
		can = append(can, "add")
	}
	if g.Aggregate {
		can = append(can, "count")
	}
	if len(can) == 0 {
		return "nothing"
	}
	return strings.Join(can, ", ")
}

func grantsCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "grants", Short: "Who may reach your data and hardware: list and revoke grants an owner approved"}
	g.AddCommand(dataGrantsCmd(a), hostGrantsCmd(a))
	return []*cobra.Command{g}
}

func dataGrantsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "data", Short: "Data access: apps, agents and people allowed one class of data (GET /v1/data/grants)"}
	var all bool
	list := &cobra.Command{
		Use:   "list",
		Short: "Live data grants (an owner sees all; anyone else their own)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var grants []dataGrant
			raw, err := getBoth(a, "/v1/data/grants", &grants)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			now := time.Now()
			var rows [][]string
			ended := 0
			for _, d := range grants {
				if !d.Active && !all {
					ended++
					continue
				}
				state := in(d.ExpiresAt, now)
				if !d.Active {
					state = "ended"
				}
				rows = append(rows, []string{d.ID, sanitize(d.Grantee.Kind + ":" + d.Grantee.ID), d.DataClass, grantAllows(d), state})
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No live data grants: nobody reaches data beyond what everyone sees.")
			} else if err := table(a.Stdout, "ID\tWHO\tDATA\tMAY\tUNTIL\t", rows); err != nil {
				return err
			}
			if ended > 0 {
				fmt.Fprintf(a.Stderr, "%d ended or revoked grants not shown (--all shows them)\n", ended)
			}
			return nil
		},
	}
	list.Flags().BoolVar(&all, "all", false, "also show ended and revoked grants")
	g.AddCommand(list)
	g.AddCommand(&cobra.Command{
		Use:   "revoke GRANT_ID",
		Short: "Revoke a data grant now (owner only; revoking twice is safe)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var d dataGrant
			if err := c.DoIdempotent(bg(), http.MethodDelete, "/v1/data/grants/"+url.PathEscape(args[0]), freshKey(), nil, &d); err != nil {
				return explainGateway(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, d)
			}
			fmt.Fprintf(a.Stdout, "data grant %s revoked: %s no longer reaches %s data\n", sanitize(d.ID), sanitize(d.Grantee.Kind+":"+d.Grantee.ID), d.DataClass)
			return nil
		},
	})
	return g
}

func hostGrantsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "host", Short: "Hardware access: apps allowed a device, the GPU or the host network (GET /v1/host-grants)"}
	var app string
	var all bool
	list := &cobra.Command{
		Use:   "list",
		Short: "Live host grants of installed apps (owner only)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			path := "/v1/host-grants"
			if app != "" {
				path += "?app_id=" + url.QueryEscape(app)
			}
			var v struct {
				Grants []hostGrant `json:"grants"`
			}
			raw, err := getBoth(a, path, &v)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			now := time.Now()
			var rows [][]string
			for _, h := range v.Grants {
				if !h.Active && !all {
					continue
				}
				what := h.Kind
				if h.DeviceClass != nil {
					what += " " + *h.DeviceClass
				}
				if h.Path != nil {
					what += " " + *h.Path
				}
				state := "active"
				if !h.Active {
					state = "revoked"
				}
				rows = append(rows, []string{h.ID, sanitize(h.AppID), sanitize(what), age(h.GrantedAt, now), state, sanitize(h.Reason)})
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No app has hardware access.")
				return nil
			}
			return table(a.Stdout, "ID\tAPP\tREACHES\tGRANTED\tSTATE\tWHY\t", rows)
		},
	}
	list.Flags().StringVar(&app, "app", "", "only this app's grants")
	list.Flags().BoolVar(&all, "all", false, "also show revoked grants")
	g.AddCommand(list)
	g.AddCommand(&cobra.Command{
		Use:   "revoke GRANT_ID",
		Short: "Revoke an app's hardware access now (owner only)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var h hostGrant
			if err := c.Do(bg(), http.MethodPost, "/v1/host-grants/"+url.PathEscape(args[0])+"/revoke", nil, &h); err != nil {
				return explainGateway(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, h)
			}
			fmt.Fprintf(a.Stdout, "host grant %s revoked: %s no longer reaches %s\n", sanitize(h.ID), sanitize(h.AppID), h.Kind)
			return nil
		},
	})
	return g
}
