// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"github.com/spf13/cobra"
)

// machinesCommands is `onemind machines` (MACH-01, #281): which boxes can run virtual machines, the
// machines there are, and requests to create, start, stop and delete one. Every change is a request
// that waits for an owner (`onemind actions approve ID`); this command never approves, so an agent
// token can use it and still never actuate (docs/umbrel2/machines.md §5).
func machinesCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "machines", Short: "Virtual machines on an x86 hub (requests wait for an owner)"}
	get := func(path string) error {
		c, _, err := a.client()
		if err != nil {
			return err
		}
		var raw any
		if err := c.Do(bg(), http.MethodGet, path, nil, &raw); err != nil {
			return err
		}
		return printJSON(a.Stdout, raw)
	}
	list := &cobra.Command{Use: "list", Short: "Machines on this box (GET /v1/machines)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error { return get("/v1/machines") }}
	caps := &cobra.Command{Use: "capabilities", Short: "Which nodes can run machines, and why the others cannot", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error { return get("/v1/machines/capabilities") }}
	info := &cobra.Command{Use: "info NAME", Short: "One machine", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error { return get("/v1/machines/" + url.PathEscape(args[0])) }}

	var ram, cpus, disk int
	var image string
	create := &cobra.Command{Use: "create NAME", Short: "Request a new machine (stopped; an owner approves)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.machineRequest("machine.create", map[string]any{"name": args[0], "ram_mb": ram, "cpus": cpus, "disk_gb": disk, "image_url": image})
		}}
	create.Flags().IntVar(&ram, "ram-mb", 2048, "memory for the machine, in MB")
	create.Flags().IntVar(&cpus, "cpus", 2, "processor cores")
	create.Flags().IntVar(&disk, "disk-gb", 20, "disk size, in GB")
	create.Flags().StringVar(&image, "image-url", "", "https URL of the disk image to start from")
	_ = create.MarkFlagRequired("image-url")
	ref := func(verb string) *cobra.Command {
		return &cobra.Command{Use: verb + " NAME", Short: "Request to " + verb + " a machine (an owner approves)", Args: cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				return a.machineRequest("machine."+verb, map[string]any{"name": args[0]})
			}}
	}
	var confirm string
	del := &cobra.Command{Use: "delete NAME", Short: "Request to delete a machine and its disk (an owner approves)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.machineRequest("machine.delete", map[string]any{"name": args[0], "confirm": confirm})
		}}
	del.Flags().StringVar(&confirm, "confirm", "", "the machine's name again; deleting erases its disk")
	console := &cobra.Command{Use: "console NAME", Short: "A one-minute console ticket (owners only)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw any
			if err := c.Do(bg(), http.MethodPost, "/v1/machines/"+url.PathEscape(args[0])+"/console", nil, &raw); err != nil {
				return err
			}
			return printJSON(a.Stdout, raw)
		}}
	root.AddCommand(list, caps, info, create, ref("start"), ref("stop"), del, console)
	return []*cobra.Command{root}
}

// machineRequest files one action and says who must approve it. It never approves.
func (a *App) machineRequest(typ string, params map[string]any) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	key := make([]byte, 12)
	if _, err := rand.Read(key); err != nil {
		return err
	}
	body := map[string]any{"type": typ, "params": params, "idempotency_key": "cli-" + hex.EncodeToString(key),
		"expires_at": time.Now().Add(time.Hour).UTC().Format(time.RFC3339)}
	var act map[string]any
	if err := c.Do(bg(), http.MethodPost, "/v1/actions", body, &act); err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, act)
	}
	id, _ := act["id"].(string)
	if a.G.Quiet {
		fmt.Fprintln(a.Stdout, id)
		return nil
	}
	fmt.Fprintf(a.Stdout, "Requested %s (%s). Waiting for an owner: onemind actions approve %s\n", typ, id, id)
	return nil
}
