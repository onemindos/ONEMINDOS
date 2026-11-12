// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/version"
	onemind "github.com/onemindos/onemindos/sdk/go"
)

// target is the resolved box for one invocation.
type target struct {
	name      string // context name, "" when --hub/ONEMIND_HUB was used without one
	hub       string
	token     string
	principal string
	ctx       *Context
}

// resolve applies the precedence flag > environment > context > default (CLI.md §3.1).
func (a *App) resolve() (*target, error) {
	cfg, err := loadConfig(a.G.ConfigFile)
	if err != nil {
		return nil, err
	}
	t := &target{name: a.G.Context}
	if t.name == "" && a.G.Hub == "" {
		t.name = cfg.CurrentContext
	}
	if t.name != "" {
		c, ok := cfg.Contexts[t.name]
		if !ok {
			return nil, exitWith(ExitNotFound, "not_found", fmt.Sprintf("no context %q (see `onemind context list`)", t.name))
		}
		t.ctx, t.hub, t.principal = c, c.Hub, c.Principal
		if cr, err := cfg.loadCreds(); err == nil {
			t.token = cr.Tokens[t.name]
		}
	}
	if a.G.Hub != "" {
		if t.ctx != nil && strings.TrimRight(a.G.Hub, "/") != strings.TrimRight(t.ctx.Hub, "/") {
			// A context's saved token belongs to that context's box: never send it elsewhere.
			// An explicit ONEMIND_TOKEN, --token or --token-stdin below still applies.
			t.token = ""
		}
		t.hub = a.G.Hub
	}
	if env := os.Getenv("ONEMIND_TOKEN"); env != "" {
		t.token = env
	}
	if a.G.Token != "" {
		fmt.Fprintln(a.Stderr, "onemind: warning: --token lands in shell history; prefer ONEMIND_TOKEN or --token-stdin")
		t.token = a.G.Token
	}
	if a.G.TokenStdin {
		tok, err := readSecretLine(a.Stdin)
		if err != nil {
			return nil, err
		}
		t.token = tok
	}
	if t.hub == "" {
		return nil, exitWith(ExitUsage, "usage", "no box selected: run `onemind login --hub URL`, or pass --hub (or set ONEMIND_HUB)")
	}
	return t, nil
}

func readSecretLine(r io.Reader) (string, error) {
	line, err := bufio.NewReader(r).ReadString('\n')
	if err != nil && err != io.EOF {
		return "", err
	}
	tok := strings.TrimSpace(line)
	if tok == "" {
		return "", exitWith(ExitUsage, "usage", "--token-stdin: nothing on stdin")
	}
	return tok, nil
}

func (a *App) clientFor(t *target) (*onemind.Client, error) {
	opts := []onemind.Option{
		onemind.WithToken(t.token), onemind.WithTimeout(a.G.Timeout), onemind.WithPrincipal(t.principal),
		onemind.WithUserAgent("onemind-cli/" + version.Version),
		onemind.WithWarn(func(s string) {
			if t.ctx == nil || !t.ctx.InsecureHTTP {
				fmt.Fprintln(a.Stderr, "onemind: warning:", s)
			}
		}),
	}
	if a.G.Verbose {
		opts = append(opts, onemind.WithTrace(func(method, path string, status int, d time.Duration) {
			fmt.Fprintf(a.Stderr, "%s %s %d %s (Authorization redacted)\n", method, path, status, d.Round(time.Millisecond))
		}))
	}
	c, err := onemind.New(t.hub, opts...)
	if err != nil {
		return nil, exitWith(ExitUsage, "usage", err.Error())
	}
	return c, nil
}

// client resolves the box and returns an SDK client for it.
func (a *App) client() (*onemind.Client, *target, error) {
	t, err := a.resolve()
	if err != nil {
		return nil, nil, err
	}
	c, err := a.clientFor(t)
	return c, t, err
}

func bg() context.Context { return context.Background() }

// confirm asks a yes/no question on a TTY. Without one it returns a usage error naming the flag.
func (a *App) confirm(question, flag string) (bool, error) {
	if !a.Interactive() {
		return false, exitWith(ExitUsage, "usage", fmt.Sprintf("stdin is not a terminal: pass %s to answer %q", flag, question))
	}
	fmt.Fprintf(a.Stderr, "%s [y/N] ", question)
	line, _ := bufio.NewReader(a.Stdin).ReadString('\n')
	ans := strings.ToLower(strings.TrimSpace(line))
	return ans == "y" || ans == "yes", nil
}

// confirmTyped asks the person to type want (destructive actions).
func (a *App) confirmTyped(question, want, flag string) (bool, error) {
	if !a.Interactive() {
		return false, exitWith(ExitUsage, "usage", fmt.Sprintf("stdin is not a terminal: pass %s to answer %q", flag, question))
	}
	fmt.Fprintf(a.Stderr, "%s Type %s to confirm: ", question, want)
	line, _ := bufio.NewReader(a.Stdin).ReadString('\n')
	return strings.TrimSpace(line) == want, nil
}
