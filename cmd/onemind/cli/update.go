// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"text/tabwriter"

	"github.com/onemindos/onemindos/internal/update"
)

func updateCommands() []Command {
	sub := func(name, usage string) Command {
		return Command{
			Path:  []string{"update", name},
			Usage: usage,
			Run:   func(env *Env, args []string) error { return updateCmd(env, name, args, env.Stdout, env.Stderr) },
		}
	}
	return []Command{
		sub("status", "onemind update status [--config FILE] [--json]"),
		sub("check", "onemind update check  [--config FILE]"),
		sub("apply", "onemind update apply  [--config FILE] [--no-reboot]"),
	}
}

// updateCmd implements `onemind update status|check|apply` (brief 30 B4.2,
// contract §10.1). check and apply need root: they write the update state
// under /data and apply installs with RAUC.
func updateCmd(env *Env, sub string, args []string, out, errw io.Writer) error {
	fs := flag.NewFlagSet("update "+sub, flag.ContinueOnError)
	conf := fs.String("config", envOr("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), "update.conf path")
	asJSON := fs.Bool("json", false, "status: print status.json as is")
	noReboot := fs.Bool("no-reboot", false, "apply: install but leave the reboot to the maintenance window")
	if err := fs.Parse(args); err != nil {
		return err
	}
	c, err := update.LoadConfig(*conf)
	if err != nil {
		return err
	}
	if sub == "status" {
		return printStatus(c, *asJSON, out)
	}
	log := slog.New(slog.NewTextHandler(errw, &slog.HandlerOptions{Level: slog.LevelDebug}))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	mode := update.ModeCheck
	if sub == "apply" {
		mode = update.ModeApply
	}
	res, err := env.NewEngine(c, log).Run(ctx, mode, *noReboot)
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
