// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
)

// Bridge is one row of GET /v1/bridges (#610): an approved bridge, its effective limits and the
// counters since the gateway started.
type Bridge struct {
	ID               string              `json:"id"`
	AppStatus        *string             `json:"app_status"`
	State            string              `json:"state"`
	Provider         string              `json:"provider"`
	Mode             string              `json:"mode"`
	DataClass        string              `json:"data_class"`
	Emits            []map[string]string `json:"emits"`
	EventsPerSecond  int                 `json:"events_per_second"`
	Burst            int                 `json:"burst"`
	MaxEventBytes    int                 `json:"max_event_bytes"`
	PausedAt         *string             `json:"paused_at"`
	PausedReason     *string             `json:"paused_reason"`
	Accepted         int                 `json:"accepted"`
	Duplicates       int                 `json:"duplicates"`
	Rejected         int                 `json:"rejected"`
	Throttled        int                 `json:"throttled"`
	RecentRejects    int                 `json:"recent_rejects"`
	LastEventAt      *string             `json:"last_event_at"`
	LastRejectReason *string             `json:"last_reject_reason"`
	Entities         int                 `json:"entities"`
}

// bridgeCommands is `onemind bridge`: what each data bridge is sending through the gateway intake
// (POST /v1/bridges/<id>/events). Reading needs an owner or adult; resume is owner only.
func bridgeCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "bridge", Short: "Data bridges: state, limits and what they sent (GET /v1/bridges)"}
	get := func(path string, out any) error {
		c, _, err := a.client()
		if err != nil {
			return err
		}
		return c.Do(bg(), http.MethodGet, path, nil, out)
	}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Every approved bridge: state, rate, accepted, refused and throttled events",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var bs []Bridge
			if err := get("/v1/bridges", &bs); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, bs)
			}
			return table(a.Stdout, "ID\tSTATE\tPROVIDER\tMODE\tRATE\tACCEPTED\tREFUSED\tTHROTTLED", BridgeRows(bs))
		},
	})
	g.AddCommand(&cobra.Command{
		Use:     "status ID",
		Short:   "One bridge in detail, with why it was paused",
		Example: "  onemind bridge status quake-feed",
		Args:    cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var b Bridge
			if err := get("/v1/bridges/"+url.PathEscape(args[0]), &b); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, b)
			}
			return kv(a.Stdout, BridgeStatusPairs(b))
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "resume ID",
		Short: "Let a paused bridge send again (owner only)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var b Bridge
			if err := c.Do(bg(), http.MethodPost, "/v1/bridges/"+url.PathEscape(args[0])+"/resume", nil, &b); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, b)
			}
			fmt.Fprintf(a.Stdout, "%s: %s\n", sanitize(b.ID), sanitize(b.State))
			return nil
		},
	})
	return []*cobra.Command{g}
}

// BridgeRows is the list table, one line per bridge.
func BridgeRows(bs []Bridge) [][]string {
	rows := [][]string{}
	for _, b := range bs {
		rows = append(rows, []string{b.ID, b.State, b.Provider, b.Mode, fmt.Sprintf("%d/s (burst %d)", b.EventsPerSecond, b.Burst),
			fmt.Sprint(b.Accepted), fmt.Sprint(b.Rejected), fmt.Sprint(b.Throttled)})
	}
	return rows
}

// BridgeStatusPairs is `onemind bridge status`: every field a person needs to see why a bridge is quiet.
func BridgeStatusPairs(b Bridge) [][2]string {
	emits := []string{}
	for _, e := range b.Emits {
		emits = append(emits, e["kind"]+" "+e["name"])
	}
	pairs := [][2]string{
		{"Bridge", b.ID}, {"State", b.State}, {"App", dash(deref(b.AppStatus))},
		{"Provider", b.Provider + " (" + b.Mode + ", " + b.DataClass + " data)"},
		{"Sends", dash(strings.Join(emits, ", "))},
		{"Limits", fmt.Sprintf("%d events/s, burst %d, %d bytes an event", b.EventsPerSecond, b.Burst, b.MaxEventBytes)},
		{"Accepted", fmt.Sprintf("%d (%d already seen)", b.Accepted, b.Duplicates)},
		{"Refused", fmt.Sprintf("%d (%d in the last 5 minutes)", b.Rejected, b.RecentRejects)},
		{"Throttled", fmt.Sprint(b.Throttled)}, {"Entities kept", fmt.Sprint(b.Entities)},
		{"Last event", dash(deref(b.LastEventAt))}, {"Last refusal", dash(deref(b.LastRejectReason))},
	}
	if b.PausedAt != nil {
		pairs = append(pairs, [2]string{"Paused", *b.PausedAt + ": " + deref(b.PausedReason)},
			[2]string{"Next step", "onemind bridge resume " + b.ID})
	}
	return pairs
}
