// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"text/tabwriter"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/update"
)

// osUpdateNode is the part of GET /v1/os/updates these commands read.
type osUpdateNode struct {
	NodeID         string `json:"node_id"`
	Hostname       string `json:"hostname"`
	Reported       bool   `json:"reported"`
	Channel        string `json:"channel"`
	Policy         string `json:"policy"`
	Window         string `json:"window"`
	SettingsSource string `json:"settings_source"`
}

// updateSettingsCommand is `onemind update settings show|set` (REL-02, #154): the OS update policy
// (ask first by default, Z-02 answered by the founder 2026-11-28; auto is the opt-in) and the maintenance window. `set` files an
// os.update.settings request (PUT /v1/os/settings) and never approves it: the owner approves it in the dashboard
// with a passkey (D-027, D-028).
func updateSettingsCommand(a *App) *cobra.Command {
	root := &cobra.Command{Use: "settings", Short: "The OS update policy and maintenance window: show, set (files an approval)"}
	nodes := func() ([]osUpdateNode, error) {
		cl, _, err := a.client()
		if err != nil {
			return nil, err
		}
		var st struct {
			Nodes []osUpdateNode `json:"nodes"`
		}
		if err := cl.Do(bg(), http.MethodGet, "/v1/os/updates", nil, &st); err != nil {
			return nil, err
		}
		return st.Nodes, nil
	}
	show := &cobra.Command{
		Use:   "show",
		Short: "Each machine's update policy, window and who set them (GET /v1/os/updates)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			ns, err := nodes()
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, ns)
			}
			tw := tabwriter.NewWriter(a.Stdout, 0, 2, 2, ' ', 0)
			fmt.Fprintln(tw, "NODE\tCHANNEL\tPOLICY\tWINDOW\tSET BY")
			for _, n := range ns {
				if !n.Reported {
					fmt.Fprintf(tw, "%s\t-\t-\t-\tno update service\n", n.NodeID)
					continue
				}
				fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\n", n.NodeID, dash(n.Channel), dash(n.Policy), dash(n.Window), dash(n.SettingsSource))
			}
			return tw.Flush()
		},
	}
	var node, policy, window string
	set := &cobra.Command{
		Use:   "set [--node NODE] [--policy auto|notify|off] [--window HH:MM-HH:MM|any]",
		Short: "Request a new policy or window; flags you leave out keep their current value (PUT /v1/os/settings)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			if policy == "" && window == "" {
				return fmt.Errorf("give --policy, --window or both")
			}
			if policy != "" {
				if _, err := update.ParsePolicy(policy); err != nil {
					return err
				}
			}
			if window != "" {
				if _, err := update.ParseWindow(window); err != nil {
					return fmt.Errorf("--window: %w", err)
				}
			}
			ns, err := nodes()
			if err != nil {
				return err
			}
			var n *osUpdateNode
			for i := range ns {
				if node != "" && ns[i].NodeID != node {
					continue
				}
				if node == "" && len(ns) > 1 {
					return fmt.Errorf("%d machines report; name one with --node (see: onemind update settings show)", len(ns))
				}
				n = &ns[i]
			}
			if n == nil {
				return fmt.Errorf("no machine %q has reported to this hub", node)
			}
			if !n.Reported {
				return fmt.Errorf("%s runs no update service", n.NodeID)
			}
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]any{"node_id": n.NodeID}
			if policy != "" {
				body["policy"] = policy
			}
			if window != "" {
				body["window"] = window
			}
			var act map[string]any
			if err := cl.DoIdempotent(bg(), http.MethodPut, "/v1/os/settings", freshKey(), body, &act); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, act)
			}
			id, _ := act["id"].(string)
			params, _ := act["params"].(map[string]any)
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, id)
				return nil
			}
			fmt.Fprintf(a.Stdout, "Requested update policy %s, window %s on %s (%s).\n"+
				"Nothing changes until an owner approves it with a passkey in the dashboard (Approvals).\n",
				params["policy"], params["window"], n.NodeID, id)
			return nil
		},
	}
	set.Flags().StringVar(&node, "node", "", "the machine to change (needed when more than one reports)")
	set.Flags().StringVar(&policy, "policy", "", "notify (tell me and wait for my approval; the default), auto (install inside the window) or off (do not check)")
	set.Flags().StringVar(&window, "window", "", "local-time maintenance window HH:MM-HH:MM (may wrap midnight) or any")
	root.AddCommand(show, set)
	return root
}
