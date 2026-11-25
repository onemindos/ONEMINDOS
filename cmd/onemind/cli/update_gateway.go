// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind update apply` through the gateway, and `onemind update policy`.
//
// Apply has two paths. The normal one asks the gateway for the `os.update.install` action
// (POST /v1/actions): an owner approves it (with a passkey when the box has one), and the box's host
// service installs into the other A/B slot with the health gate and rollback. That path needs no
// root and works from any machine with a token. The other one is break-glass: `--local` (or no box
// selected at all) runs the engine on this machine as root, with no approval and no owner in the
// loop, so it says so every time. Use it only when the gateway is down.

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// gatewayApply makes `update apply` file an approval when a box is selected, and keeps the local
// root path as break-glass behind --local.
func gatewayApply(a *App, apply *cobra.Command, local func() error) {
	var forceLocal bool
	var node, version string
	apply.Flags().BoolVar(&forceLocal, "local", false, "BREAK-GLASS: install on this machine as root now, with no approval (default when no box is selected)")
	apply.Flags().StringVar(&node, "node", "", "gateway mode: the node to update (default: the hub)")
	apply.Flags().StringVar(&version, "target-version", "", "gateway mode: the version on offer to install (default: the one the node offers)")
	apply.Short = "Install an available update: files an approval on the box; --local is the break-glass root path"
	apply.RunE = func(cmd *cobra.Command, _ []string) error {
		if !forceLocal {
			c, _, err := a.client()
			if err == nil {
				a.gw = c
				if cmd.Flags().Changed("no-reboot") || cmd.Flags().Changed("mirror") {
					return usageErr(cmd, "--no-reboot and --mirror act on this machine: add --local, or drop them to ask the box to install")
				}
				return a.updateApplyViaGateway(node, version)
			}
			if !strings.Contains(err.Error(), "no box selected") {
				return err
			}
		} else if node != "" || version != "" {
			return usageErr(cmd, "--node and --target-version are for the gateway path, not --local")
		}
		fmt.Fprintln(a.Stderr, "onemind: BREAK-GLASS: installing on this machine as root with no approval and no owner in the loop. "+
			"Normally run this against the box so an owner approves it: onemind login, then onemind update apply.")
		return local()
	}
}

func (a *App) updateApplyViaGateway(node, version string) error {
	inst, err := a.gwDo(http.MethodGet, "/v1/instance", nil)
	if err != nil {
		return err
	}
	if node == "" {
		node = str(obj(inst)["hub_node_id"])
	}
	st, err := a.gwDo(http.MethodGet, "/v1/os/updates", nil)
	if err != nil {
		return err
	}
	var offered string
	found := false
	for _, n := range list(obj(st)["nodes"]) {
		if m := obj(n); str(m["node_id"]) == node {
			found, offered = true, str(m["available_version"])
		}
	}
	switch {
	case !found:
		return exitWith(ExitNotFound, "not_found", fmt.Sprintf("node %q has not reported to this box (see `onemind nodes`)", node))
	case offered == "" && version == "":
		return exitWith(ExitConflict, "conflict", fmt.Sprintf("node %s has no update on offer; run `onemind update check` there first", node))
	}
	if version == "" {
		version = offered
	}
	if in := obj(obj(st)["install"]); in["available"] == false {
		fmt.Fprintln(a.Stderr, "onemind: warning: the box cannot run an approved install yet:", sanitize(str(in["message"])))
	}
	key := make([]byte, 12)
	if _, err := rand.Read(key); err != nil {
		return err
	}
	body := map[string]any{"type": "os.update.install", "params": map[string]any{"node_id": node, "version": version},
		"idempotency_key": "cli-" + hex.EncodeToString(key), "expires_at": time.Now().Add(24 * time.Hour).UTC().Format(time.RFC3339)}
	act, err := a.gwDo(http.MethodPost, "/v1/actions", body)
	if err != nil {
		return err
	}
	return a.printRequested("OS update "+version+" for "+node, act)
}

func updatePolicyCommand(a *App) *cobra.Command {
	root := &cobra.Command{Use: "policy", Short: "The rules for unattended app updates: show, set (owner only)"}
	root.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "Show the policy and the apps paused after failures (GET /v1/update-policy)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/update-policy", func(w io.Writer, v any) error {
				m := obj(v)
				on := "off"
				if obj(m["ai_schedule"])["enabled"] == true {
					on = "on"
				}
				pairs := [][2]string{
					{"window", str(m["window_id"])},
					{"cool-off hours", str(m["cool_off_hours"])},
					{"same major only", str(m["same_major_only"])},
					{"pause after failures", str(m["backoff_after_failures"])},
					{"AI power schedule", on},
					{"customised", str(m["customized"])},
				}
				if p := list(m["paused_apps"]); len(p) > 0 {
					pairs = append(pairs, [2]string{"paused apps", fmt.Sprint(len(p))})
				}
				return kv(w, pairs)
			})
		},
	})

	var window string
	var coolOff, backoff int
	var sameMajor bool
	set := &cobra.Command{
		Use:   "set",
		Short: "Change the policy; flags you leave out keep their current value (PUT /v1/update-policy)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			f := cmd.Flags()
			if !f.Changed("window") && !f.Changed("cool-off-hours") && !f.Changed("same-major-only") && !f.Changed("backoff-after-failures") {
				return usageErr(cmd, "nothing to change: give at least one flag")
			}
			cur, err := a.gwDo(http.MethodGet, "/v1/update-policy", nil)
			if err != nil {
				return err
			}
			// PUT replaces the whole policy, so start from what is there now.
			c := obj(cur)
			body := map[string]any{}
			for _, k := range []string{"window_id", "cool_off_hours", "same_major_only", "backoff_after_failures", "ai_schedule"} {
				body[k] = c[k]
			}
			if f.Changed("window") {
				body["window_id"] = window
			}
			if f.Changed("cool-off-hours") {
				body["cool_off_hours"] = coolOff
			}
			if f.Changed("same-major-only") {
				body["same_major_only"] = sameMajor
			}
			if f.Changed("backoff-after-failures") {
				body["backoff_after_failures"] = backoff
			}
			v, err := a.gwDo(http.MethodPut, "/v1/update-policy", body)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			fmt.Fprintln(a.Stdout, "Update policy saved.")
			return nil
		},
	}
	set.Flags().StringVar(&window, "window", "", "maintenance window id")
	set.Flags().IntVar(&coolOff, "cool-off-hours", 0, "wait this long after a release before updating to it (0 to 720)")
	set.Flags().BoolVar(&sameMajor, "same-major-only", true, "never auto-update across a major version")
	set.Flags().IntVar(&backoff, "backoff-after-failures", 0, "pause an app's auto-update after this many failures in a row (1 to 10)")
	root.AddCommand(set)
	return root
}
