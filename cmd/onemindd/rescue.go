// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"crypto/tls"
	"errors"
	"flag"
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
	fs := flag.NewFlagSet("onemindd rescue", flag.ContinueOnError)
	listen := fs.String("listen", env("ONEMIND_RESCUE_ADDR", ":7443"), "listen address (LAN clients only)")
	tokens := fs.String("tokens", env("ONEMIND_TOKENS_FILE", rescue.DefaultTokensFile), "gateway tokens file (owner sha256)")
	tlsDir := fs.String("tls-dir", env("ONEMIND_NET_TLS_DIR", "/var/lib/onemind/tls"), "box CA directory with https.crt and https.key")
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
	srv := &http.Server{Addr: *listen, ReadHeaderTimeout: 10 * time.Second, IdleTimeout: time.Minute,
		Handler: rescue.New(rescue.Config{TokensFile: *tokens, Version: version.Version, Runner: rescue.Exec{}, Logger: log})}
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
