// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"os/user"
	"strconv"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/firewall"
	"github.com/onemindos/onemindos/internal/host"
	"github.com/onemindos/onemindos/internal/netview"
	"github.com/onemindos/onemindos/internal/smb"
	"github.com/onemindos/onemindos/internal/storage/ops"
	"github.com/onemindos/onemindos/internal/svcregistry"
	"github.com/onemindos/onemindos/internal/update"
	"github.com/onemindos/onemindos/internal/version"
)

const hostUsage = `usage:
  onemindd host serve [--socket PATH] [--user NAME] [--journal DIR] [--update-conf FILE] [--firewall-dir DIR] [--delay 3s]
  onemindd host plan factory-reset    print what a factory reset would erase and keep (JSON, read-only, root)
  onemindd factory-reset wipe [--esp DIR]   early boot only: run the armed reset (onemind-factory-reset.service)
`

// runHost is `onemindd host`: the host action service (#146, #142), its own
// privileged unit (os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-host.service).
// It restarts, shuts down and installs OS updates for actions the owner
// approved in the gateway (docs/leap/core/HOST-ACTIONS.md).
func runHost(args []string) int {
	if len(args) == 2 && args[0] == "plan" && args[1] == "factory-reset" {
		p := (&host.FactoryReset{}).Plan(context.Background())
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(p)
		return 0
	}
	if len(args) == 0 || args[0] != "serve" {
		fmt.Fprint(os.Stderr, hostUsage)
		return 2
	}
	fs := flag.NewFlagSet("onemindd host serve", flag.ContinueOnError)
	sock := fs.String("socket", env("ONEMIND_HOST_SOCKET", "/run/onemind/host.sock"), "Unix socket for the gateway")
	gwUser := fs.String("user", env("ONEMIND_HOST_USER", "onemind"), "the one user besides root allowed on the socket (the gateway's)")
	journal := fs.String("journal", env("ONEMIND_HOST_JOURNAL", "/data/onemind/host/actions"), "action journal directory")
	conf := fs.String("update-conf", env("ONEMIND_UPDATE_CONF", update.DefaultConfigPath), "update.conf for OS installs")
	fwDir := fs.String("firewall-dir", env("ONEMIND_HOST_FIREWALL_DIR", "/data/onemind/firewall"), "where confirmed owner allow rules are kept")
	fwTTL := fs.Duration("firewall-ttl", envDuration("ONEMIND_HOST_FIREWALL_TTL", firewall.DefaultTTL), "how long a new owner allow rule waits for confirmation before it reverts")
	delay := fs.Duration("delay", 3*time.Second, "wait before the box goes down, so the gateway records the answer first")
	if err := fs.Parse(args[1:]); err != nil {
		return 2
	}
	log := newLogger()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	units := &svcregistry.Reader{Version: version.Version} // service cards, logs and approved restarts (#623, #636)
	svc := &host.Service{Power: host.Systemd{}, OS: &host.UpdateEngine{ConfigPath: *conf, Log: log},
		BootID: host.BootID(), Delay: *delay, Log: log,
		Reset: &host.FactoryReset{},
		Units: units,
		SMB:   &smb.Manager{P: smb.DefaultPaths(), Run: smb.ExecRunner{}}}
	if st, err := host.OpenStore(*journal); err != nil {
		log.Error("host journal unavailable: status only, every action refused", "dir", *journal, "err", err)
	} else {
		svc.Store = st
	}
	if err := svc.Resume(); err != nil {
		// Fail closed: an unreadable journal may hide an open action.
		log.Error("host journal unreadable: status only, every action refused", "err", err)
		svc.Store = nil
	}
	uid := -1
	if u, err := user.Lookup(*gwUser); err == nil {
		uid, _ = strconv.Atoi(u.Uid)
	} else {
		log.Warn("gateway user not found; root only", "user", *gwUser)
	}
	// The image passes the socket from onemind-host.socket (0660 root:onemind), so
	// nothing here chowns. Without systemd (development) it opens one, root only.
	l, err := host.ActivationListener(os.Getenv, os.Getpid(), 3)
	if err == nil && l == nil {
		l, err = ops.Listen(*sock, -1)
	}
	if err != nil {
		log.Error("cannot listen", "socket", *sock, "err", err)
		return 1
	}
	log.Info("host service listening", "socket", *sock, "journal", svc.Store != nil, "boot_id", svc.BootID, "gateway_uid", uid)
	// Owner allow rules (P-09 part 2): confirmed ones come back from /data, pending ones are dropped (reverted).
	allow := &firewall.Allower{Dir: *fwDir, Reload: reloadOwnerFirewall, TTL: *fwTTL, Log: log}
	if err := allow.Open(ctx); err != nil {
		log.Error("firewall owner rules not loaded; new ones are refused until the firewall has its owner lists", "err", err)
	}
	err = (&host.Server{S: svc, AllowUID: uid, AllowGID: -1, Ctx: ctx, Network: networkView, Firewall: firewallView(allow), FirewallAllow: allow,
		Services: serviceCards, ServiceLogs: units.Logs}).Serve(ctx, l)
	stop()
	svc.Wait()
	if err != nil {
		log.Error("host service stopped", "err", err)
		return 1
	}
	return 0
}

// runFactoryReset is `onemindd factory-reset wipe`, run by
// onemind-factory-reset.service early in boot, before /data is assembled. Exit
// 0: wiped, or nothing was armed; the boot goes on. Exit 1: the wipe failed or
// the marker is stale; the unit's OnFailure= isolates recovery mode, so the old
// data is never mounted after a reset was approved. Writes the reason to
// /run/onemind-recovery/status like onemind-data-check does.
func runFactoryReset(args []string) int {
	fs := flag.NewFlagSet("onemindd factory-reset wipe", flag.ContinueOnError)
	esp := fs.String("esp", "/boot/efi", "the ESP mount holding the marker")
	if len(args) == 0 || args[0] != "wipe" || fs.Parse(args[1:]) != nil {
		fmt.Fprint(os.Stderr, hostUsage)
		return 2
	}
	log := newLogger()
	err := host.Wipe(context.Background(), ops.ExecRunner{}, *esp, time.Now())
	switch {
	case err == nil:
		log.Info("factory reset done: the box is set up again on this boot")
		return 0
	case errors.Is(err, host.ErrNoMarker):
		return 0
	}
	reason := "factory-reset"
	if errors.Is(err, host.ErrStaleMarker) {
		reason = "factory-reset-stale"
	}
	log.Error("factory reset did not complete: recovery mode", "reason", reason, "err", err)
	_ = os.MkdirAll("/run/onemind-recovery", 0o755)
	_ = os.WriteFile("/run/onemind-recovery/status",
		[]byte(fmt.Sprintf("REASON=%s\nDETAIL=%q\nSINCE=%s\n", reason, err.Error(), time.Now().UTC().Format(time.RFC3339))), 0o644)
	return 1
}

// networkView is GET /v1/network: the box's interfaces, gateways, DNS and listening ports, read from
// /sys and /proc (internal/netview). Files are capped so an odd host cannot make one answer huge.
func networkView() (any, error) {
	read := func(p string) ([]byte, error) {
		f, err := os.Open(p)
		if err != nil {
			return nil, err
		}
		defer f.Close()
		return io.ReadAll(io.LimitReader(f, 1<<20))
	}
	exists := func(p string) bool { _, err := os.Stat(p); return err == nil }
	return netview.System(read, exists).Collect()
}

// firewallView is GET /v1/firewall: `nft -j list ruleset`, run with fixed arguments and no shell, parsed by
// internal/firewall into a structured form. Output is capped and the run has a deadline, so a stuck
// nft cannot hold the host service.
func firewallView(al *firewall.Allower) func(context.Context) (any, error) {
	return func(ctx context.Context) (any, error) { return collectFirewall(ctx, al) }
}

func collectFirewall(ctx context.Context, al *firewall.Allower) (any, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	c := firewall.Collector{Allower: al, Run: readRuleset}
	return c.Collect(ctx)
}

// serviceCards is GET /v1/services (#623): every unit in the image's services registry
// (/usr/lib/onemind/services.yaml) with systemd's state and memory, plus OneMind units the registry
// does not list (known=false). Read-only: systemctl show and list-unit-files only.
func serviceCards(ctx context.Context) (any, error) {
	return (&svcregistry.Reader{Version: version.Version}).Collect(ctx)
}

// envDuration is a duration from an environment variable; unset or not a positive duration gives def.
func envDuration(key string, def time.Duration) time.Duration {
	if d, err := time.ParseDuration(os.Getenv(key)); err == nil && d > 0 {
		return d
	}
	return def
}

// reloadOwnerFirewall has systemd load /data/onemind/firewall/live.nft. The unit holds CAP_NET_ADMIN, the host
// service does not: it can only hand over a file, and `nft -c` in the unit refuses a file that is not valid.
func reloadOwnerFirewall(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if out, err := exec.CommandContext(ctx, "systemctl", "restart", "onemind-firewall-owner.service").CombinedOutput(); err != nil {
		return fmt.Errorf("systemctl restart onemind-firewall-owner.service: %w: %s", err, out)
	}
	return nil
}

// rulesetFile is where onemind-firewall-read.service leaves the ruleset (see that unit for why).
const rulesetFile = "/run/onemind-fw/ruleset.json"

// readRuleset asks systemd to run the reader unit, which holds CAP_NET_ADMIN (this service does not), and reads
// the JSON it wrote. Without the unit (a development box) it runs `nft -j list ruleset` itself, which works
// only with enough privilege; either way the output is capped and nothing here can change a rule.
func readRuleset(ctx context.Context) ([]byte, error) {
	if err := exec.CommandContext(ctx, "systemctl", "restart", "onemind-firewall-read.service").Run(); err == nil {
		f, err := os.Open(rulesetFile)
		if err != nil {
			return nil, err
		}
		defer f.Close()
		return io.ReadAll(io.LimitReader(f, 8<<20))
	}
	cmd := exec.CommandContext(ctx, "/usr/sbin/nft", "-j", "list", "ruleset")
	out, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	raw, rerr := io.ReadAll(io.LimitReader(out, 8<<20))
	if err := cmd.Wait(); err != nil {
		return nil, err
	}
	return raw, rerr
}
