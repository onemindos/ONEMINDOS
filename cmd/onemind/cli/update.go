// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"text/tabwriter"
	"time"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/update"
)

func updateCommands(a *App) []*cobra.Command {
	upd := &cobra.Command{Use: "update", Short: "OS updates: status and check run the local engine (rollback needs root); apply files an approval; settings shows and requests the OS update policy and window; policy shows and sets the app update rules"}
	var conf string
	var noReboot bool
	var mirror string
	sub := func(name, short string) *cobra.Command {
		return &cobra.Command{
			Use:   name,
			Short: short,
			Args:  cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error {
				return updateCmd(&a.Env, name, conf, mirror, a.G.JSON, noReboot, a.Stdout, a.Stderr)
			},
		}
	}
	status, check, apply := sub("status", "Show the update state (--json: status.json as is)"),
		sub("check", "Check for an update now"), sub("apply", "Install an available update")
	for _, c := range []*cobra.Command{status, check, apply} {
		c.Flags().StringVar(&conf, "config", envOr("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), "update.conf path")
	}
	for _, c := range []*cobra.Command{check, apply} {
		c.Flags().StringVar(&mirror, "mirror", "", "read the channel from this directory (USB stick or mounted LAN share) instead of the network; "+
			"signatures and hashes are checked exactly as online, only expiry gets the offline_grace allowance")
	}
	apply.Flags().BoolVar(&noReboot, "no-reboot", false, "install but leave the reboot to the maintenance window (--local only)")
	gatewayApply(a, apply, func() error {
		return updateCmd(&a.Env, "apply", apply.Flag("config").Value.String(), apply.Flag("mirror").Value.String(), a.G.JSON, noReboot, a.Stdout, a.Stderr)
	})
	upd.AddCommand(status, check, apply, updatePolicyCommand(a), updateSettingsCommand(a), rollbackCommand(a), fleetCommand(a), rolloutsCommand(a))
	return []*cobra.Command{upd}
}

// updateCmd implements `onemind update status|check|apply` (brief 30 B4.2,
// contract §10.1). check and apply need root: they write the update state
// under /data and apply installs with RAUC.
func updateCmd(env *Env, sub, conf, mirror string, asJSON, noReboot bool, out, errw io.Writer) error {
	c, err := update.LoadConfig(conf)
	if err != nil {
		return err
	}
	if sub == "status" {
		return printStatus(c, asJSON, out)
	}
	log := slog.New(slog.NewTextHandler(errw, &slog.HandlerOptions{Level: slog.LevelDebug}))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	mode := update.ModeCheck
	if sub == "apply" {
		mode = update.ModeApply
	}
	eng := env.NewEngine(c, log)
	eng.Mirror = mirror
	res, err := eng.Run(ctx, mode, noReboot)
	if res != nil && res.Decision != "" {
		fmt.Fprintf(out, "decision: %s (%s)\n", res.Decision, res.Reason)
		for _, s := range res.Skips {
			fmt.Fprintf(out, "  skipped %s: %s\n", s.Path, s.Why)
		}
	}
	if err != nil {
		return err
	}
	return printStatus(c, false, out)
}

func printStatus(c *update.Config, asJSON bool, out io.Writer) error {
	st, err := update.LoadStatus(c)
	if err != nil {
		return err
	}
	if asJSON {
		return printJSON(out, st)
	}
	avail, check := "-", "never"
	if st.AvailableVersion != nil {
		avail = *st.AvailableVersion
	}
	if st.LastCheck != nil {
		check = *st.LastCheck
	}
	tw := tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	fmt.Fprintf(tw, "channel\t%s (%s)\n", c.Channel, c.URL)
	p, w, src, oerr := c.Effective()
	fmt.Fprintf(tw, "policy\t%s, window %s (set by: %s)\n", p, w, src)
	if oerr != nil {
		fmt.Fprintf(tw, "warning\towner update settings ignored: %v\n", oerr)
	}
	fmt.Fprintf(tw, "current\t%s\n", dash(st.CurrentVersion))
	fmt.Fprintf(tw, "available\t%s\n", avail)
	fmt.Fprintf(tw, "state\t%s\n", st.State)
	fmt.Fprintf(tw, "last check\t%s\n", check)
	fmt.Fprintf(tw, "last result\t%s\n", dash(st.LastResult))
	if st.Snapshot != "" {
		fmt.Fprintf(tw, "snapshot\t%s\n", st.Snapshot)
	}
	for _, w := range st.Warnings {
		fmt.Fprintf(tw, "warning\t%s\n", w)
	}
	for _, h := range st.History {
		fmt.Fprintf(tw, "history\t%s %s %s->%s %s\n", h.At, h.Result, dash(h.From), h.To, h.Detail)
	}
	return tw.Flush()
}

// rollbackCommand is `onemind update rollback`: it files an os.rollback request for the owner and
// never approves it (P-16). Going back discards the running version, so the owner approves it with a
// passkey in the dashboard (Approvals). The CLI files the request with the owner's token and
// never approves it; an agent token is refused (403), since only a person files a rollback. It asks the hub what the
// previous version is, so the request names exactly the version the owner will read on the approval card.
func rollbackCommand(a *App) *cobra.Command {
	var node, version string
	c := &cobra.Command{
		Use:   "rollback",
		Short: "Request going back to the previous OS version (an owner approves it with a passkey)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			var st struct {
				Nodes []struct {
					NodeID   string `json:"node_id"`
					Hostname string `json:"hostname"`
					Current  string `json:"current_version"`
					Rollback struct {
						Available bool   `json:"available"`
						Version   string `json:"version"`
						Slot      string `json:"slot"`
						Message   string `json:"message"`
					} `json:"rollback"`
				} `json:"nodes"`
			}
			if err := cl.Do(bg(), http.MethodGet, "/v1/os/updates", nil, &st); err != nil {
				return err
			}
			idx := -1
			for i, n := range st.Nodes {
				if node != "" && n.NodeID != node {
					continue
				}
				if node == "" && len(st.Nodes) > 1 {
					return fmt.Errorf("%d machines report; name one with --node (see: onemind nodes)", len(st.Nodes))
				}
				idx = i
			}
			if idx < 0 {
				return fmt.Errorf("no machine %q has reported to this hub", node)
			}
			n := st.Nodes[idx]
			if !n.Rollback.Available {
				return fmt.Errorf("%s cannot go back: %s", n.NodeID, dash(n.Rollback.Message))
			}
			if version != "" && version != n.Rollback.Version {
				return fmt.Errorf("the previous version of %s is %s, not %s", n.NodeID, n.Rollback.Version, version)
			}
			key := make([]byte, 12)
			if _, err := rand.Read(key); err != nil {
				return err
			}
			body := map[string]any{"type": "os.rollback", "params": map[string]any{"node_id": n.NodeID, "version": n.Rollback.Version},
				"idempotency_key": "cli-" + hex.EncodeToString(key), "expires_at": time.Now().Add(time.Hour).UTC().Format(time.RFC3339)}
			var act map[string]any
			if err := cl.Do(bg(), http.MethodPost, "/v1/actions", body, &act); err != nil {
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
			fmt.Fprintf(a.Stdout, "Requested going back from %s to %s (slot %s) on %s (%s).\n"+
				"It waits for an owner, who approves it with a passkey in the dashboard (Approvals). The box restarts into the previous version.\n",
				dash(n.Current), n.Rollback.Version, dash(n.Rollback.Slot), n.NodeID, id)
			return nil
		},
	}
	c.Flags().StringVar(&node, "node", "", "the machine to go back on (needed when more than one reports)")
	c.Flags().StringVar(&version, "version", "", "refuse unless this is the previous version")
	return c
}
