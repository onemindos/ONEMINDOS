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

	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

// newMeshClient is replaced in tests (fake tailscale CLI).
var newMeshClient = mesh.NewClient

func meshCommands() []Command {
	return []Command{{
		Path:  []string{"mesh", "status"},
		Usage: "onemind mesh status [--json] [--leaf-monitor 127.0.0.1:8222]",
		Run:   func(env *Env, args []string) error { return meshCmd(append([]string{"status"}, args...), env.Stdout) },
	}}
}

// meshCmd implements `onemind mesh status [--json] [--leaf-monitor ADDR]`
// (docs/architecture/NETWORKING.md §12): this machine's mesh state and the
// health of its local NATS leaf.
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
