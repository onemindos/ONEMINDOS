// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"text/tabwriter"
	"time"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/update"
)

// catalogCommands is `onemind catalog status|sync`: the signed Market catalog channel
// (internal/update/catalog.go). Local, like `onemind update`: sync writes under /data.
func catalogCommands(a *App) []*cobra.Command {
	cat := &cobra.Command{Use: "catalog", Short: "The signed Market catalog channel (new apps without an OS update; needs root except status)"}
	var conf string
	sub := func(name, short string) *cobra.Command {
		c := &cobra.Command{
			Use: name, Short: short, Args: cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error { return catalogCmd(name, conf, a.G.JSON, a.Stdout) },
		}
		c.Flags().StringVar(&conf, "config", envOr("ONEMIND_CATALOG_CONF", update.DefaultCatalogConfigPath), "catalog.conf path")
		return c
	}
	cat.AddCommand(sub("status", "Show the active channel catalog (--json for scripts)"),
		sub("sync", "Fetch, verify and activate the newest signed catalog now"))
	return []*cobra.Command{cat}
}

func catalogCmd(sub, conf string, asJSON bool, out io.Writer) error {
	c, err := update.LoadCatalogConfig(conf)
	if err != nil {
		return err
	}
	if sub == "sync" {
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer stop()
		res, err := update.SyncCatalog(ctx, c, &http.Client{Timeout: 2 * time.Minute}, time.Now())
		if err != nil {
			return fmt.Errorf("catalog not updated, the box keeps the one it has: %w", err)
		}
		if asJSON {
			return printJSON(out, res)
		}
		fmt.Fprintf(out, "catalog %s: %s\n", res.Version, res.Decision)
		return nil
	}
	act, err := update.CatalogStatus(c)
	if err != nil {
		return err
	}
	if asJSON {
		return printJSON(out, act)
	}
	tw := tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	fmt.Fprintf(tw, "channel\t%s\n", c.URL)
	if act.Version == "" {
		fmt.Fprintf(tw, "active\tnone yet (the apps in the OS image are used)\n")
	} else {
		fmt.Fprintf(tw, "active\t%s (applied %s)\n", act.Version, act.AppliedAt)
	}
	return tw.Flush()
}
