// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

// newMeshClient is replaced in tests (fake tailscale CLI).
var newMeshClient = mesh.NewClient

// meshCmd implements `onemind mesh status [--json] [--leaf-monitor ADDR]`
// (docs/architecture/NETWORKING.md §12): this machine's mesh state and the
// health of its local NATS leaf. Registered as the `mesh` group in cli/root.go.
// Mesh addresses are printed because this is the owner at the box; they are
// never part of the heartbeat.
func meshCmd(args []string, out io.Writer) error {
	if len(args) == 0 || args[0] != "status" {
		return errors.New("usage: onemind mesh status [--json] [--leaf-monitor 127.0.0.1:8222]")
	}
	fs := flag.NewFlagSet("mesh status", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "print JSON")
	mon := fs.String("leaf-monitor", leaf.DefaultMonitor, "local NATS leaf monitoring address (loopback)")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	st := newMeshClient().Status(ctx)
	lh := leaf.CheckHealth(ctx, &http.Client{Timeout: 3 * time.Second}, *mon)
	if *asJSON {
		enc := json.NewEncoder(out)
		enc.SetIndent("", "  ")
		return enc.Encode(struct {
			Mesh *mesh.State `json:"mesh"`
			Leaf leaf.Health `json:"leaf"`
		}{st, lh})
	}
	if err := mesh.PrintState(out, st, false); err != nil {
		return err
	}
	fmt.Fprintf(out, "\nnats leaf: %s", lh.State)
	if lh.RTT != "" {
		fmt.Fprintf(out, " (rtt %s)", lh.RTT)
	}
	if lh.Error != "" {
		fmt.Fprintf(out, " (%s)", lh.Error)
	}
	fmt.Fprintln(out)
	return nil
}

// meshCommands registers `onemind mesh` (a group line in root.go). `mesh status` keeps its own
// flag handling (meshCmd), so cobra passes its arguments through untouched; `mesh settings` is a
// normal subcommand that talks to the hub.
func meshCommands(a *App) []*cobra.Command {
	m := &cobra.Command{
		Use:                "mesh status [--json] [--leaf-monitor ADDR]",
		Short:              "Show this machine's mesh and NATS leaf state, or the hub's mesh settings",
		DisableFlagParsing: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			args, err := takeLeadingGlobals(cmd, args)
			if err != nil {
				return err
			}
			if a.G.JSON { // the global --json (typed before the command) means the same as the local one
				args = insertJSON(args, 1)
			}
			return meshCmd(args, a.Stdout)
		},
	}
	m.AddCommand(meshSettingsCommand(a))
	return []*cobra.Command{m}
}

// meshView is the part of GET /v1/mesh (and of PUT /v1/mesh/settings' answer) that `mesh settings` prints.
type meshView struct {
	Settings struct {
		Enabled    bool    `json:"enabled"`
		Provider   *string `json:"provider"`
		ControlURL string  `json:"control_url"`
		Saved      bool    `json:"saved"`
		UpdatedAt  *string `json:"updated_at"`
	} `json:"settings"`
	Setup struct {
		State    string  `json:"state"`
		Reason   *string `json:"reason"`
		Detail   string  `json:"detail"`
		NextStep *string `json:"next_step"`
	} `json:"setup"`
}

// meshSettingsCommand is `onemind mesh settings` (CORE-NET-8): the hub's mesh state and its next step.
// With --enable, --disable, --provider or --control-url it changes the state through PUT
// /v1/mesh/settings, which only the owner may call and which writes an audit entry.
func meshSettingsCommand(a *App) *cobra.Command {
	var enable, disable bool
	var provider, controlURL string
	cmd := &cobra.Command{
		Use:   "settings [--enable|--disable] [--provider headscale|none] [--control-url URL]",
		Short: "Show or change the hub's mesh: on or off, its provider, its control URL (changing it is owner only)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if enable && disable {
				return exitWith(ExitUsage, "usage", "mesh settings: --enable and --disable together")
			}
			body := map[string]any{}
			if enable {
				body["enabled"] = true
			}
			if disable {
				body["enabled"] = false
			}
			if cmd.Flags().Changed("provider") {
				body["provider"] = provider
			}
			if cmd.Flags().Changed("control-url") {
				body["control_url"] = controlURL
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var v meshView
			if len(body) == 0 {
				err = c.Do(bg(), http.MethodGet, "/v1/mesh", nil, &v)
			} else {
				err = c.Do(bg(), http.MethodPut, "/v1/mesh/settings", body, &v)
			}
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			return printMeshSettings(a.Stdout, v)
		},
	}
	f := cmd.Flags()
	f.BoolVar(&enable, "enable", false, "turn the mesh on (needs a provider)")
	f.BoolVar(&disable, "disable", false,
		"stop minting mesh keys and managing the coordinator; machines and phones that already joined stay connected")
	f.StringVar(&provider, "provider", "", "the mesh provider: headscale, or none to clear the choice")
	f.StringVar(&controlURL, "control-url", "", "the https URL machines and phones reach the coordinator at")
	return cmd
}

func printMeshSettings(out io.Writer, v meshView) error {
	on := "off"
	if v.Settings.Enabled {
		on = "on"
	}
	provider := "none chosen"
	if v.Settings.Provider != nil {
		provider = *v.Settings.Provider
	}
	source := "install settings"
	if v.Settings.Saved {
		source = "changed by the owner " + deref(v.Settings.UpdatedAt)
	}
	pairs := [][2]string{
		{"mesh:", on}, {"provider:", provider}, {"control url:", v.Settings.ControlURL}, {"from:", source},
		{"state:", v.Setup.State}, {"detail:", v.Setup.Detail},
	}
	if v.Setup.NextStep != nil {
		pairs = append(pairs, [2]string{"next step:", *v.Setup.NextStep})
	}
	return kv(out, pairs)
}
