// Command onemindd is the OneMind node agent (contract sdk/contracts/poc-v0.md
// §1-§2). It runs on every OneMind machine, serves the node's heartbeat on
// :7480 and publishes it to the hub's NATS every 10 seconds.
//
// Configuration comes from environment variables (contract §1):
//
//	ONEMIND_NATS_URL    hub NATS URL, e.g. nats://hub.local:4222 (empty = API only)
//	ONEMIND_NODE_ROLE   hub | node (default node)
//	ONEMIND_NODE_ID     override the id derived from /etc/machine-id
//	ONEMIND_AGENT_ADDR  local API address (default 127.0.0.1:7480, loopback only)
//	ONEMIND_DISK_PATH   filesystem measured for disk_* (default /)
//	ONEMIND_LOG_LEVEL   debug | info | warn | error (default info)
//	ONEMIND_UPDATE_CONF OS update settings (default /etc/onemind/update.conf);
//	                    when present, the heartbeat carries the "update" object
//
// `onemindd update [-config FILE]` runs the OS update service instead
// (brief 30 B4.2, contract §10.1; unit deploy/systemd/onemind-update.service).
// It is a separate process because it needs write access to /data and the
// right to install and reboot, which the read-only heartbeat agent must not have.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/onemindos/onemindos/internal/agent"
	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/service"
	"github.com/onemindos/onemindos/internal/update"
	"github.com/onemindos/onemindos/internal/version"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// validate checks the role and the optional ONEMIND_NODE_ID override. The id
// becomes a NATS subject token, so a bad one would make the node invisible
// to the hub (the gateway drops subjects it cannot parse).
func validate(role, nodeID string) error {
	if err := heartbeat.ValidateRole(role); err != nil {
		return err
	}
	if nodeID != "" {
		if err := heartbeat.ValidateNodeID(nodeID); err != nil {
			return fmt.Errorf("ONEMIND_NODE_ID: %w", err)
		}
	}
	return nil
}

func newLogger() *slog.Logger {
	var lvl slog.Level
	if err := lvl.UnmarshalText([]byte(env("ONEMIND_LOG_LEVEL", "info"))); err != nil {
		lvl = slog.LevelInfo
	}
	return slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: lvl}))
}

// updateReport returns the heartbeat's "update" source, or nil when the box
// has no update.conf (developer installs: contract §10.1, no A/B).
func updateReport(path string, log *slog.Logger) func() *heartbeat.Update {
	c, err := update.LoadConfig(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	} else if err != nil {
		log.Warn("update.conf invalid; heartbeat omits the update object", "err", err)
		return nil
	}
	return func() *heartbeat.Update { return update.Report(c) }
}

// runUpdate is `onemindd update`: the update service loop.
func runUpdate(args []string) int {
	fs := flag.NewFlagSet("onemindd update", flag.ContinueOnError)
	conf := fs.String("config", env("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), "update.conf path")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	log := newLogger()
	c, err := update.LoadConfig(*conf)
	if err != nil {
		log.Error("onemindd update: cannot start", "err", err)
		return 2
	}
	if len(c.Ignored) > 0 {
		log.Warn("update.conf: unknown keys ignored", "keys", c.Ignored)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	log.Info("update service starting", "version", version.Version, "channel", c.Channel, "url", c.URL,
		"policy", c.Policy, "window", c.Window.String(), "restic", c.ResticConfigured())
	update.New(c, log).Daemon(ctx)
	return 0
}

func main() {
	if len(os.Args) > 1 && subcommands[os.Args[1]] != nil { // registry.go
		os.Exit(subcommands[os.Args[1]](os.Args[2:]))
	}
	listen := flag.String("listen", env("ONEMIND_AGENT_ADDR", agent.DefaultListen), "local API listen address")
	natsURL := flag.String("nats", os.Getenv("ONEMIND_NATS_URL"), "hub NATS URL (empty = do not publish)")
	role := flag.String("role", env("ONEMIND_NODE_ROLE", "node"), "hub or node")
	interval := flag.Duration("interval", agent.DefaultInterval, "heartbeat interval")
	showVersion := flag.Bool("version", false, "print version and exit")
	flag.Parse()
	if flag.NArg() > 0 { // a typo or a missing subcommand must not start a second agent
		fmt.Fprintf(os.Stderr, "onemindd: unknown command %q\n", flag.Arg(0))
		os.Exit(2)
	}

	if *showVersion {
		fmt.Println("onemindd", version.Version)
		return
	}
	nodeID := os.Getenv("ONEMIND_NODE_ID")
	if err := validate(*role, nodeID); err != nil {
		fmt.Fprintln(os.Stderr, "onemindd:", err)
		os.Exit(2)
	}

	log := newLogger()

	col := detect.New()
	col.Role = *role
	col.NodeID = nodeID
	col.DiskPath = env("ONEMIND_DISK_PATH", "/")

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	log.Info("onemindd starting", "version", version.Version, "node_id", col.ID(), "role", *role, "board", col.Board())
	a := agent.New(agent.Config{Listen: *listen, NATSURL: *natsURL, Interval: *interval, Collector: col, Logger: log,
		UpdateReport: updateReport(env("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), log),
		BackupReport: backupReport(env("ONEMIND_BACKUP_CONF", backup.DefaultConfigPath)),
		Mounts:       service.Mounts(ctx, optionalServices)})
	wait := service.Start(ctx, log, optionalServices) // registry.go
	err := a.Run(ctx)
	stop()
	wait()
	if err != nil {
		log.Error("onemindd stopped", "err", err)
		os.Exit(1)
	}
	log.Info("onemindd stopped")
}
