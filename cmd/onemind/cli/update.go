// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"text/tabwriter"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/update"
)

func updateCommands(a *App) []*cobra.Command {
	upd := &cobra.Command{Use: "update", Short: "OS updates on this box (local engine; needs root except status)"}
	var conf string
	var noReboot bool
	sub := func(name, short string) *cobra.Command {
		return &cobra.Command{
			Use:   name,
			Short: short,
			Args:  cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error {
				return updateCmd(&a.Env, name, conf, a.G.JSON, noReboot, a.Stdout, a.Stderr)
			},
		}
	}
	status, check, apply := sub("status", "Show the update state (--json: status.json as is)"),
		sub("check", "Check for an update now"), sub("apply", "Install an available update")
	for _, c := range []*cobra.Command{status, check, apply} {
		c.Flags().StringVar(&conf, "config", envOr("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), "update.conf path")
	}
	apply.Flags().BoolVar(&noReboot, "no-reboot", false, "install but leave the reboot to the maintenance window")
	upd.AddCommand(status, check, apply)
	return []*cobra.Command{upd}
}

// updateCmd implements `onemind update status|check|apply` (brief 30 B4.2,
// contract §10.1). check and apply need root: they write the update state
// under /data and apply installs with RAUC.
func updateCmd(env *Env, sub, conf string, asJSON, noReboot bool, out, errw io.Writer) error {
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
	res, err := env.NewEngine(c, log).Run(ctx, mode, noReboot)
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
	fmt.Fprintf(tw, "policy\t%s, window %s\n", c.Policy, c.Window)
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
