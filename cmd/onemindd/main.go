// Command onemindd is the OneMind node agent (contract sdk/contracts/poc-v0.md
// §1-§2). It runs on every OneMind machine, serves the node's heartbeat on
// :7480 and publishes it to the hub's NATS every 10 seconds.
//
// Configuration comes from environment variables (contract §1):
//
//	ONEMIND_NATS_URL    hub NATS URL, e.g. nats://hub.local:4222 (empty = API only)
//	ONEMIND_NODE_ROLE   hub | node (default node)
//	ONEMIND_NODE_ID     override the id derived from /etc/machine-id
//	ONEMIND_AGENT_ADDR  local API address (default :7480)
//	ONEMIND_DISK_PATH   filesystem measured for disk_* (default /)
//	ONEMIND_LOG_LEVEL   debug | info | warn | error (default info)
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/onemindos/onemindos/internal/agent"
	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
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

func main() {
	listen := flag.String("listen", env("ONEMIND_AGENT_ADDR", agent.DefaultListen), "local API listen address")
	natsURL := flag.String("nats", os.Getenv("ONEMIND_NATS_URL"), "hub NATS URL (empty = do not publish)")
	role := flag.String("role", env("ONEMIND_NODE_ROLE", "node"), "hub or node")
	interval := flag.Duration("interval", agent.DefaultInterval, "heartbeat interval")
	showVersion := flag.Bool("version", false, "print version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println("onemindd", version.Version)
		return
	}
	nodeID := os.Getenv("ONEMIND_NODE_ID")
	if err := validate(*role, nodeID); err != nil {
		fmt.Fprintln(os.Stderr, "onemindd:", err)
		os.Exit(2)
	}

	var lvl slog.Level
	if err := lvl.UnmarshalText([]byte(env("ONEMIND_LOG_LEVEL", "info"))); err != nil {
		lvl = slog.LevelInfo
	}
	log := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: lvl}))

	col := detect.New()
	col.Role = *role
	col.NodeID = nodeID
	col.DiskPath = env("ONEMIND_DISK_PATH", "/")

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	log.Info("onemindd starting", "version", version.Version, "node_id", col.ID(), "role", *role, "board", col.Board())
	a := agent.New(agent.Config{Listen: *listen, NATSURL: *natsURL, Interval: *interval, Collector: col, Logger: log})
	if err := a.Run(ctx); err != nil {
		log.Error("onemindd stopped", "err", err)
		os.Exit(1)
	}
	log.Info("onemindd stopped")
}
