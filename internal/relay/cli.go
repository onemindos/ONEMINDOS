// SPDX-License-Identifier: Apache-2.0

package relay

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"math/big"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"
)

const cliUsage = `usage:
  onemindd relay init --addr PUBLIC_IP --route NAME=HOST:PORT [--route ...] [--listen :443] [--config FILE]
  onemindd relay serve [--config FILE]
  onemindd relay status [--config FILE]
`

type routeFlags []Route

func (r *routeFlags) String() string { return fmt.Sprint(*r) }
func (r *routeFlags) Set(v string) error {
	for i := range v {
		if v[i] == '=' {
			*r = append(*r, Route{Name: v[:i], Upstream: v[i+1:]})
			return nil
		}
	}
	return fmt.Errorf("route must be NAME=HOST:PORT, got %q", v)
}

// RunCLI is `onemindd relay ...`. It returns the process exit code.
func RunCLI(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, cliUsage)
		return 2
	}
	var err error
	switch args[0] {
	case "init":
		err = cliInit(args[1:], stdout)
	case "serve":
		err = cliServe(args[1:])
	case "status":
		err = cliStatus(args[1:], stdout)
	default:
		fmt.Fprint(stderr, cliUsage)
		return 2
	}
	if err == flag.ErrHelp {
		return 2
	}
	if err != nil {
		fmt.Fprintln(stderr, "onemindd relay:", err)
		return 1
	}
	return 0
}

func cliInit(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("relay init", flag.ContinueOnError)
	addr := fs.String("addr", "", "this machine's public IP address")
	listen := fs.String("listen", ":443", "address to listen on")
	path := fs.String("config", DefaultConfigPath, "config file to write")
	var routes routeFlags
	fs.Var(&routes, "route", "NAME=HOST:PORT: pass TLS for NAME to HOST:PORT without decrypting (repeatable)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if _, err := os.Stat(*path); err == nil {
		return fmt.Errorf("%s already exists; this machine is already a relay (delete it to start over)", *path)
	}
	code, err := NewCode()
	if err != nil {
		return err
	}
	fp, err := setupFingerprint()
	if err != nil {
		return err
	}
	cfg := &Config{Listen: *listen, Routes: routes, CodeHash: HashCode(code), SetupFP: fp}
	if err := cfg.Validate(); err != nil {
		return err
	}
	p := Pairing{Addr: *addr, FP: fp, Code: code}
	if _, err := ParsePairing(p.String()); err != nil {
		return err
	}
	if err := cfg.Save(*path); err != nil {
		return err
	}
	fmt.Fprintln(out, "This machine is now set up as your OneMind relay. On your hub, open Network, Relay and paste this text (shown once):")
	fmt.Fprintln(out, p.String())
	return nil
}

// setupFingerprint makes the setup certificate's fingerprint. The key lives only in memory in this
// first slice; the pairing handshake that uses it is a follow-up (docs/learning/remote-access-relay.md).
func setupFingerprint() (string, error) {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return "", err
	}
	tpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "onemind-relay-setup"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().AddDate(0, 0, 1)}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &key.PublicKey, key)
	if err != nil {
		return "", err
	}
	return sha256Hex(der), nil
}

func cliServe(args []string) error {
	fs := flag.NewFlagSet("relay serve", flag.ContinueOnError)
	path := fs.String("config", DefaultConfigPath, "config file")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := Load(*path)
	if err != nil {
		return err
	}
	ln, err := net.Listen("tcp", cfg.Listen)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	log := slog.Default()
	log.Info("relay: serving", "listen", cfg.Listen, "routes", len(cfg.Routes))
	return NewRouter(cfg, log).Serve(ctx, ln)
}

func cliStatus(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("relay status", flag.ContinueOnError)
	path := fs.String("config", DefaultConfigPath, "config file")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := Load(*path)
	if os.IsNotExist(err) {
		fmt.Fprintln(out, "This machine is not a relay. Run `onemindd relay init` to make it one.")
		return nil
	}
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "relay: listening on %s, paired: %t\n", cfg.Listen, cfg.Paired)
	for _, r := range cfg.Routes {
		fmt.Fprintf(out, "  %s -> %s (passed through encrypted)\n", r.Name, r.Upstream)
	}
	return nil
}
