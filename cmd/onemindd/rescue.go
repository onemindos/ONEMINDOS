// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"crypto/tls"
	"errors"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/rescue"
	"github.com/onemindos/onemindos/internal/version"
)

// runRescue is `onemindd rescue`: the rescue console (CORE-UPDATE-8). Its own
// process and unit (deploy/systemd/onemind-rescue.service), because rollback
// needs `rauc status mark-active` and a reboot, which the read-only heartbeat
// agent must not have, and because it must keep working when k3s is down.
func runRescue(args []string) int {
	if len(args) > 0 && args[0] == "terminal" {
		return runRescueTerminal(args[1:])
	}
	fs := flag.NewFlagSet("onemindd rescue", flag.ContinueOnError)
	listen := fs.String("listen", env("ONEMIND_RESCUE_ADDR", ":7443"), "listen address (LAN clients only)")
	tokens := fs.String("tokens", env("ONEMIND_TOKENS_FILE", rescue.DefaultTokensFile), "gateway tokens file (owner sha256)")
	tlsDir := fs.String("tls-dir", env("ONEMIND_NET_TLS_DIR", "/var/lib/onemind/tls"), "box CA directory with https.crt and https.key")
	sw := fs.String("terminal-switch", env("ONEMIND_RESCUE_TERMINAL_SWITCH", defaultTerminalSwitch), "file whose presence turns the owner terminal on")
	auditPath := fs.String("audit", env("ONEMIND_RESCUE_AUDIT", defaultRescueAudit), "the console's own audit chain")
	gateway := fs.String("gateway", env("ONEMIND_RESCUE_GATEWAY", defaultRescueGateway), "gateway on this box (loopback only) that checks the owner's passkey")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	log := newLogger()
	crt, key := filepath.Join(*tlsDir, "https.crt"), filepath.Join(*tlsDir, "https.key")
	_, errC := os.Stat(crt)
	_, errK := os.Stat(key)
	useTLS := errC == nil && errK == nil
	if !useTLS && !loopbackAddr(*listen) {
		log.Error("onemindd rescue: no TLS certificate from the box CA; plain HTTP is allowed on loopback only",
			"cert", crt, "listen", *listen)
		return 2
	}
	cfg := rescue.Config{TokensFile: *tokens, Version: version.Version, Runner: rescue.Exec{}, Logger: log}
	// The owner terminal (SEC-TERM-01). A start needs a fresh owner passkey assertion that the gateway on this
	// box verifies (D-014: never a shell behind the plain owner token). With a bad -gateway address Reauth
	// stays nil and every start is refused.
	if au, err := rescue.OpenAudit(*auditPath, nil); err != nil {
		log.Error("rescue terminal not mounted: the audit chain does not verify", "file", *auditPath, "err", err)
	} else {
		cfg.Terminal = &rescue.Terminal{SwitchFile: *sw, Spawner: rescue.PTY{}, Audit: au,
			IdleTimeout: 10 * time.Minute, MaxDuration: time.Hour}
		if re, err := rescue.NewGatewayReauth(*gateway, nil); err != nil {
			log.Error("rescue terminal has no passkey check, so it cannot open", "err", err)
		} else {
			cfg.Terminal.Reauth = re
		}
	}
	srv := &http.Server{Addr: *listen, ReadHeaderTimeout: 10 * time.Second, IdleTimeout: time.Minute,
		Handler: rescue.New(cfg)}
	if useTLS {
		// Re-read the pair on every handshake: the gateway renews it in place (core/onemind_core/ca.py).
		srv.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12,
			GetCertificate: func(*tls.ClientHelloInfo) (*tls.Certificate, error) {
				c, err := tls.LoadX509KeyPair(crt, key)
				return &c, err
			}}
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		sctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(sctx)
	}()
	log.Info("rescue console starting", "version", version.Version, "listen", *listen, "https", useTLS, "tokens", *tokens)
	var err error
	if useTLS {
		err = srv.ListenAndServeTLS("", "")
	} else {
		err = srv.ListenAndServe()
	}
	if err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Error("rescue console stopped", "err", err)
		return 1
	}
	return 0
}

// loopbackAddr reports whether a listen address binds only to loopback.
func loopbackAddr(addr string) bool {
	h, _, err := net.SplitHostPort(addr)
	if err != nil {
		return false
	}
	if h == "localhost" {
		return true
	}
	ip := net.ParseIP(h)
	return ip != nil && ip.IsLoopback()
}

const (
	defaultTerminalSwitch = "/etc/onemind/rescue-terminal.on"
	defaultRescueAudit    = "/var/lib/onemind/rescue-audit.jsonl"
	defaultRescueGateway  = "http://127.0.0.1:8080" // the gateway's loopback-only HTTP port
)

// runRescueTerminal is `onemindd rescue terminal enable|disable|status`: the owner's switch for the web
// terminal, run as root on the box. Off by default; each change is written to the audit chain.
func runRescueTerminal(args []string) int {
	fs := flag.NewFlagSet("onemindd rescue terminal", flag.ContinueOnError)
	sw := fs.String("terminal-switch", env("ONEMIND_RESCUE_TERMINAL_SWITCH", defaultTerminalSwitch), "switch file")
	auditPath := fs.String("audit", env("ONEMIND_RESCUE_AUDIT", defaultRescueAudit), "the console's audit chain")
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "usage: onemindd rescue terminal enable|disable|status [-terminal-switch FILE] [-audit FILE]")
		return 2
	}
	cmd := args[0]
	if err := fs.Parse(args[1:]); err != nil {
		return 2
	}
	on := rescue.SwitchOn(*sw)
	switch cmd {
	case "status":
		if on {
			fmt.Println("on (the console still refuses every shell until passkey sign-in exists)")
		} else {
			fmt.Println("off")
		}
		return 0
	case "enable", "disable":
		au, err := rescue.OpenAudit(*auditPath, nil)
		if err != nil {
			fmt.Fprintln(os.Stderr, "onemindd rescue terminal: the audit chain does not verify:", err)
			return 1
		}
		// Record first: no line, no change.
		if err := au.Append("terminal.switch", map[string]any{"kind": "local", "role": "root"},
			map[string]any{"state": cmd + "d"}); err != nil {
			fmt.Fprintln(os.Stderr, "onemindd rescue terminal: cannot write the audit chain:", err)
			return 1
		}
		if cmd == "enable" {
			err = os.WriteFile(*sw, []byte("on\n"), 0o600)
		} else if err = os.Remove(*sw); errors.Is(err, os.ErrNotExist) {
			err = nil
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, "onemindd rescue terminal:", err)
			return 1
		}
		fmt.Println("terminal " + cmd + "d")
		return 0
	}
	fmt.Fprintln(os.Stderr, "onemindd rescue terminal: unknown command", cmd)
	return 2
}
