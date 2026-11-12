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

// meshCommands registers `onemind mesh` (a group line in root.go). The command keeps its own
// flag handling (meshCmd), so cobra passes the arguments through untouched.
func meshCommands(a *App) []*cobra.Command {
	return []*cobra.Command{{
		Use:                "mesh status [--json] [--leaf-monitor ADDR]",
		Short:              "Show this machine's mesh and NATS leaf state",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			return meshCmd(args, a.Stdout)
		},
	}}
}
