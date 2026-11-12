// SPDX-License-Identifier: Apache-2.0

package mesh

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"
	"text/tabwriter"
	"time"
)

const cliUsage = `usage:
  onemindd mesh enroll --bundle FILE [--key-dir DIR] [--timeout 60s]
  onemindd mesh wait-ip [--timeout 120s]
  onemindd mesh status [--json]
`

// RunCLI is `onemindd mesh …`. cmd/onemindd/main.go dispatches to it with one
// line (NETWORKING.md §18). It returns the process exit code.
func RunCLI(args []string, stdout, stderr io.Writer) int {
	return runCLI(NewClient(), args, stdout, stderr)
}

func runCLI(c *Client, args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, cliUsage)
		return 2
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var err error
	switch args[0] {
	case "enroll":
		err = cliEnroll(ctx, c, args[1:], stdout)
	case "wait-ip":
		err = cliWaitIP(ctx, c, args[1:], stdout)
	case "status":
		err = cliStatus(ctx, c, args[1:], stdout)
	default:
		fmt.Fprint(stderr, cliUsage)
		return 2
	}
	if errors.Is(err, flag.ErrHelp) {
		return 2
	}
	if err != nil {
		fmt.Fprintln(stderr, "onemindd mesh:", err)
		return 1
	}
	return 0
}

// cliEnroll reads the bundle's mesh block from a file (the fabric join flow
// will call Enroll directly; this is for the installer and for repairs).
func cliEnroll(ctx context.Context, c *Client, args []string, out io.Writer) error {
	fs := flag.NewFlagSet("mesh enroll", flag.ContinueOnError)
	bundle := fs.String("bundle", "", "JSON file with the join bundle's mesh block (contains a one-time key)")
	keyDir := fs.String("key-dir", DefaultKeyDir, "tmpfs directory for the short-lived key file")
	timeout := fs.Duration("timeout", DefaultUpTimeout, "limit for tailscale up and for the mesh address")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *bundle == "" {
		return errors.New("--bundle is required")
	}
	raw, err := os.ReadFile(*bundle)
	if err != nil {
		return err
	}
	var b Bundle
	if err := json.Unmarshal(raw, &b); err != nil {
		return fmt.Errorf("bundle: invalid JSON: %w", err)
	}
	res, err := c.Enroll(ctx, &b, EnrollOptions{KeyDir: *keyDir, Timeout: *timeout})
	if err != nil {
		return err
	}
	if res.Already {
		fmt.Fprintln(out, "already on the mesh at", res.Addr, "(key not used)")
	} else {
		fmt.Fprintln(out, "joined the mesh at", res.Addr)
	}
	return nil
}

func cliWaitIP(ctx context.Context, c *Client, args []string, out io.Writer) error {
	fs := flag.NewFlagSet("mesh wait-ip", flag.ContinueOnError)
	timeout := fs.Duration("timeout", 120*time.Second, "how long to wait")
	if err := fs.Parse(args); err != nil {
		return err
	}
	addr, err := c.WaitIP(ctx, *timeout, time.Second)
	if err != nil {
		return err
	}
	fmt.Fprintln(out, addr)
	return nil
}

func cliStatus(ctx context.Context, c *Client, args []string, out io.Writer) error {
	fs := flag.NewFlagSet("mesh status", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "print the full local state as JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return PrintState(out, c.Status(ctx), *asJSON)
}

// PrintState writes s as a table or JSON (shared with `onemind mesh status`).
func PrintState(out io.Writer, s *State, asJSON bool) error {
	if asJSON {
		enc := json.NewEncoder(out)
		enc.SetIndent("", "  ")
		return enc.Encode(s)
	}
	tw := tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	fmt.Fprintf(tw, "state:\t%s\n", s.State)
	if s.Backend != "" {
		fmt.Fprintf(tw, "backend:\t%s\n", s.Backend)
	}
	if s.Addr != "" {
		fmt.Fprintf(tw, "address:\t%s\n", s.Addr)
	}
	fmt.Fprintf(tw, "path:\t%s (hub: %s)\n", s.Path, s.HubPath)
	fmt.Fprintf(tw, "last handshake:\t%s\n", deref(s.LastHandshake))
	if s.Error != "" {
		fmt.Fprintf(tw, "error:\t%s\n", s.Error)
	}
	for _, h := range s.Health {
		fmt.Fprintf(tw, "health:\t%s\n", h)
	}
	if err := tw.Flush(); err != nil {
		return err
	}
	if len(s.Peers) == 0 {
		return nil
	}
	fmt.Fprintln(out)
	tw = tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	fmt.Fprintln(tw, "PEER\tADDRESS\tONLINE\tPATH\tLAST_HANDSHAKE")
	for _, p := range s.Peers {
		fmt.Fprintf(tw, "%s\t%s\t%t\t%s\t%s\n", p.Name, dash(p.Addr), p.Online, p.Path, deref(p.LastHandshake))
	}
	return tw.Flush()
}

func deref(s *string) string {
	if s == nil {
		return "-"
	}
	return *s
}

func dash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}
