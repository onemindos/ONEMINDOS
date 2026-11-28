// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"os/signal"
	"os/user"
	"strconv"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/firewall"
	"github.com/onemindos/onemindos/internal/flatpak"
	"github.com/onemindos/onemindos/internal/host"
	"github.com/onemindos/onemindos/internal/netset"
	"github.com/onemindos/onemindos/internal/netview"
	"github.com/onemindos/onemindos/internal/ownerssh"
	"github.com/onemindos/onemindos/internal/smb"
	"github.com/onemindos/onemindos/internal/storage"
	"github.com/onemindos/onemindos/internal/storage/ops"
	"github.com/onemindos/onemindos/internal/svcregistry"
	"github.com/onemindos/onemindos/internal/update"
	"github.com/onemindos/onemindos/internal/version"
)

const hostUsage = `usage:
  onemindd host serve [--socket PATH] [--user NAME] [--journal DIR] [--update-conf FILE] [--firewall-dir DIR] [--delay 3s]
  onemindd host apply-hostname [--file PATH]   at boot: give the box the name the owner saved (before avahi)
  onemindd host mdns-aliases [--file PATH]     keep answering to the old names (onemind.local, the name before a rename)
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
	if len(args) >= 1 && args[0] == "mdns-aliases" {
		return runMDNSAliases(args[1:])
	}
	if len(args) >= 1 && args[0] == "apply-hostname" {
		return runApplyHostname(args[1:])
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
	nm := &netset.Manager{Run: netset.ExecRunner{}, BootID: host.BootID(), Log: log} // wired address changes with rollback (P-08)
	units := &svcregistry.Reader{Version: version.Version}                           // service cards, logs and approved restarts (#623, #636)
	svc := &host.Service{Power: host.Systemd{}, OS: &host.UpdateEngine{ConfigPath: *conf, Log: log},
		Roll:   &host.SlotRollback{ConfigPath: *conf},
		BootID: host.BootID(), Delay: *delay, Log: log,
		Reset:   &host.FactoryReset{},
		Units:   units,
		Zones:   &host.Timezone{},
		Names:   host.SystemHostname{},
		Media:   &host.Housekeeping{Run: storage.ExecRunner{}},
		Keymap:  &host.KeymapStore{Units: units}, // P-11: /data/onemind/console/keyboard, the console and kiosk units
		SMB:     &smb.Manager{P: smb.DefaultPaths(), Run: smb.ExecRunner{}},
		SSH:     &ownerssh.Manager{Run: ownerssh.ExecRunner{}},
		Flatpak: flatpak.NewDefault(),
		Net:     nm}
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
	nm.Recover(ctx)                     // a change that was waiting for confirmation when the box went down
	go nm.Watch(ctx, netset.WatchEvery) // and later: the way back never waits for somebody to open the Network screen
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
		Services: serviceCards, ServiceLogs: units.Logs,
		Time:     func(ctx context.Context) (any, error) { return (&host.Timezone{}).Status(ctx), nil },
		Hostname: func() (string, error) { return host.CurrentHostname("") }}).Serve(ctx, l)
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
	return resetOutcome(host.Wipe(context.Background(), ops.ExecRunner{}, *esp, time.Now()), log, rebootNow)
}

// rebootNow restarts the box at once. --force skips the unit shutdown, which
// is right this early: nothing of the new boot is running, and the marker, the
// wipe and the head zeroing are all fsync'd already.
func rebootNow() error {
	return exec.Command("systemctl", "reboot", "--force").Run()
}

// resetOutcome maps Wipe's result onto the boot. After a successful wipe the
// box reboots: the partitions are blank now, and making the new data disk is
// the job of onemind-data-encrypt.service, which runs BEFORE this unit, so
// without a restart nothing would format them, data.mount would fail and the
// box would land in recovery mode. The next boot has no marker (it is now
// .done) and sets the box up from scratch.
func resetOutcome(err error, log *slog.Logger, reboot func() error) int {
	switch {
	case err == nil:
		log.Info("factory reset done: restarting so the box sets itself up again")
		if rerr := reboot(); rerr != nil {
			err = fmt.Errorf("the wipe finished but the restart failed: %w", rerr)
			break
		}
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

// firewallReadSocket is where onemind-firewall-read.socket prints `nft -j list ruleset`. The host service
// has no CAP_NET_ADMIN (the kernel wants it even to read nf_tables), so it cannot run nft itself.
const firewallReadSocket = "/run/onemind/firewall-read.sock"

// firewallView is GET /v1/firewall: the ruleset read from the firewall read socket (internal/firewall),
// parsed into a structured form, plus the owner allow rules. Output is capped and the read has a deadline,
// so a stuck reader cannot hold the host service.
func firewallView(al *firewall.Allower) func(context.Context) (any, error) {
	return func(ctx context.Context) (any, error) { return collectFirewall(ctx, al) }
}

func collectFirewall(ctx context.Context, al *firewall.Allower) (any, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	c := firewall.Collector{Allower: al, Run: firewall.SocketReader(firewallReadSocket)}
	return c.Collect(ctx)
}

// serviceCards is GET /v1/services (#623): every unit in the image's services registry
// (/usr/lib/onemind/services.yaml) with systemd's state and memory, plus OneMind units the registry
// does not list (known=false). Read-only: systemctl show and list-unit-files only.
func serviceCards(ctx context.Context) (any, error) {
	return (&svcregistry.Reader{Version: version.Version}).Collect(ctx)
}

// runApplyHostname is `onemindd host apply-hostname`, run at boot by a drop-in of onemind-data-layout.service
// (before avahi). The name the owner approved lives on /data (the root is read-only), so the kernel's name is
// set from it here. A box that was never renamed has no file and keeps the image's name.
func runApplyHostname(args []string) int {
	fs := flag.NewFlagSet("onemindd host apply-hostname", flag.ContinueOnError)
	file := fs.String("file", host.DefaultHostnameFile, "the saved name")
	if fs.Parse(args) != nil {
		return 2
	}
	name, err := host.ApplyHostname(*file, "", func(n string) error { return exec.Command("hostname", n).Run() })
	if err != nil {
		fmt.Fprintln(os.Stderr, "apply-hostname:", err)
		return 1
	}
	if name != "" {
		fmt.Println("host name:", name)
	}
	return 0
}

// runMDNSAliases is `onemindd host mdns-aliases`, run by onemind-mdns-aliases.service: after a rename the box
// keeps answering to onemind.local and its old name (P-05), because avahi publishes only the host name.
func runMDNSAliases(args []string) int {
	fs := flag.NewFlagSet("onemindd host mdns-aliases", flag.ContinueOnError)
	file := fs.String("file", host.DefaultAliasesFile, "the saved old names, one per line")
	if fs.Parse(args) != nil {
		return 2
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := host.RunAliases(ctx, *file, 15*time.Second); err != nil {
		fmt.Fprintln(os.Stderr, "mdns-aliases:", err)
		return 1
	}
	return 0
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
