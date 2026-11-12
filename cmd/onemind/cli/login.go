// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/url"
	"os"
	"regexp"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"
)

func loginCommands(a *App) []*cobra.Command {
	var name, principal string
	login := &cobra.Command{
		Use:   "login",
		Short: "Sign in to a box and save it as a context",
		Long: "Asks for a token without echo (or reads --token-stdin / ONEMIND_TOKEN), checks it against\n" +
			"GET /v1/instance, and saves the context. The token goes to credentials.yaml (mode 0600) next to\n" +
			"the config; the OS keychain and device sign-in with a passkey come with the identity work.",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return a.login(name, principal, false)
		},
	}
	login.Flags().StringVar(&name, "name", "", "context name (default: from the hub's host name)")
	login.Flags().StringVar(&principal, "principal", "", "the principal id this token belongs to (lets a lost approve be confirmed)")

	var all bool
	logout := &cobra.Command{
		Use:   "logout",
		Short: "Forget the credential of the current context (or --all)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadConfig(a.G.ConfigFile)
			if err != nil {
				return err
			}
			cr, err := cfg.loadCreds()
			if err != nil {
				return err
			}
			target := a.G.Context
			if target == "" {
				target = cfg.CurrentContext
			}
			if all {
				cr.Tokens = map[string]string{}
			} else {
				if target == "" {
					return exitWith(ExitUsage, "usage", "no current context; pass --context NAME or --all")
				}
				delete(cr.Tokens, target)
			}
			if err := cfg.saveCreds(cr); err != nil {
				return err
			}
			if !a.G.Quiet {
				fmt.Fprintln(a.Stderr, "Credential removed. (Server-side session revocation arrives with sessions, §12.6.)")
			}
			return nil
		},
	}
	logout.Flags().BoolVar(&all, "all", false, "forget every context's credential")
	return []*cobra.Command{login, logout, contextCommand(a)}
}

var ctxName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$`)

// login is shared with `onemind mcp login` (agent=true checks the token is an agent's).
func (a *App) login(name, principal string, agent bool) error {
	if a.G.Hub == "" {
		return exitWith(ExitUsage, "usage", "--hub is required (or set ONEMIND_HUB)")
	}
	u, err := url.Parse(a.G.Hub)
	if err != nil || u.Host == "" {
		return exitWith(ExitUsage, "usage", fmt.Sprintf("--hub %q is not a URL", a.G.Hub))
	}
	if name == "" {
		name = strings.NewReplacer(":", "-", ".", "-").Replace(u.Hostname())
	}
	if !ctxName.MatchString(name) {
		return exitWith(ExitUsage, "usage", fmt.Sprintf("context name %q: letters, digits, . _ - only", name))
	}
	token := os.Getenv("ONEMIND_TOKEN")
	switch {
	case a.G.TokenStdin:
		if token, err = readSecretLine(a.Stdin); err != nil {
			return err
		}
	case a.G.Token != "":
		fmt.Fprintln(a.Stderr, "onemind: warning: --token lands in shell history; prefer ONEMIND_TOKEN or --token-stdin")
		token = a.G.Token
	case token == "":
		f, ok := a.Stdin.(*os.File)
		if !ok || !a.Interactive() {
			return exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --token-stdin or set ONEMIND_TOKEN")
		}
		fmt.Fprint(a.Stderr, "Token: ")
		raw, err := term.ReadPassword(int(f.Fd()))
		fmt.Fprintln(a.Stderr)
		if err != nil {
			return err
		}
		token = strings.TrimSpace(string(raw))
	}
	t := &target{name: name, hub: a.G.Hub, token: token, principal: principal}
	c, err := a.clientFor(t)
	if err != nil {
		return err
	}
	inst, err := c.Instance.Get(bg())
	if err != nil {
		return err
	}
	if agent {
		if err := checkAgentToken(a, t); err != nil {
			return err
		}
	}
	cfg, err := loadConfig(a.G.ConfigFile)
	if err != nil {
		return err
	}
	cfg.Contexts[name] = &Context{
		Hub: c.BaseURL(), Principal: principal, Credential: "file", Agent: agent, BoxVersion: inst.Version,
		InsecureHTTP: u.Scheme == "http",
	}
	if !agent || cfg.CurrentContext == "" {
		cfg.CurrentContext = name
	}
	cr, err := cfg.loadCreds()
	if err != nil {
		return err
	}
	cr.Tokens[name] = token
	if err := cfg.save(); err != nil {
		return err
	}
	if err := cfg.saveCreds(cr); err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.login/v1", "context": name, "hub": c.BaseURL(), "instance": inst})
	}
	fmt.Fprintf(a.Stdout, "Box:      %s (OneMind %s)\n", sanitize(inst.Name), sanitize(inst.Version))
	if u.Scheme == "http" {
		fmt.Fprintln(a.Stdout, "Warning:  plain http; the token crosses the network unencrypted (HTTPS with a pinned box CA comes with §12.7)")
	}
	fmt.Fprintf(a.Stdout, "Saved:    context %q; token in %s (mode 0600)\n", name, cfg.credsPath())
	return nil
}

func contextCommand(a *App) *cobra.Command {
	c := &cobra.Command{Use: "context", Short: "List and switch boxes (local config only)"}
	list := &cobra.Command{Use: "list", Short: "List contexts", Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
		cfg, err := loadConfig(a.G.ConfigFile)
		if err != nil {
			return err
		}
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.contexts/v1", "current": cfg.CurrentContext, "contexts": cfg.Contexts})
		}
		var rows [][]string
		for _, n := range cfg.names() {
			x := cfg.Contexts[n]
			cur, ver := "", dash(x.BoxVersion)
			if n == cfg.CurrentContext {
				cur = "*"
			}
			if x.InsecureHTTP {
				ver += " (insecure http)"
			}
			kind := ""
			if x.Agent {
				kind = " (agent)"
			}
			rows = append(rows, []string{cur, n, x.Hub, dash(x.Principal) + kind, ver})
		}
		return table(a.Stdout, "CURRENT\tNAME\tHUB\tPRINCIPAL\tBOX VERSION", rows)
	}}
	use := &cobra.Command{Use: "use NAME", Short: "Switch the current context", Args: cobra.ExactArgs(1), RunE: func(_ *cobra.Command, args []string) error {
		cfg, err := loadConfig(a.G.ConfigFile)
		if err != nil {
			return err
		}
		if _, ok := cfg.Contexts[args[0]]; !ok {
			return exitWith(ExitNotFound, "not_found", fmt.Sprintf("no context %q", args[0]))
		}
		cfg.CurrentContext = args[0]
		if err := cfg.save(); err != nil {
			return err
		}
		fmt.Fprintf(a.Stderr, "Switched to context %q.\n", args[0])
		return nil
	}}
	show := &cobra.Command{Use: "show [NAME]", Short: "Show one context", Args: cobra.MaximumNArgs(1), RunE: func(_ *cobra.Command, args []string) error {
		cfg, err := loadConfig(a.G.ConfigFile)
		if err != nil {
			return err
		}
		n := cfg.CurrentContext
		if len(args) == 1 {
			n = args[0]
		}
		x, ok := cfg.Contexts[n]
		if !ok {
			return exitWith(ExitNotFound, "not_found", fmt.Sprintf("no context %q", n))
		}
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"name": n, "context": x})
		}
		return kv(a.Stdout, [][2]string{{"name", n}, {"hub", x.Hub}, {"principal", dash(x.Principal)},
			{"credential", dash(x.Credential)}, {"box version", dash(x.BoxVersion)}, {"insecure http", fmt.Sprint(x.InsecureHTTP)}})
	}}
	rename := &cobra.Command{Use: "rename OLD NEW", Short: "Rename a context", Args: cobra.ExactArgs(2), RunE: func(_ *cobra.Command, args []string) error {
		cfg, err := loadConfig(a.G.ConfigFile)
		if err != nil {
			return err
		}
		x, ok := cfg.Contexts[args[0]]
		if !ok {
			return exitWith(ExitNotFound, "not_found", fmt.Sprintf("no context %q", args[0]))
		}
		if !ctxName.MatchString(args[1]) {
			return exitWith(ExitUsage, "usage", "bad context name")
		}
		delete(cfg.Contexts, args[0])
		cfg.Contexts[args[1]] = x
		if cfg.CurrentContext == args[0] {
			cfg.CurrentContext = args[1]
		}
		cr, err := cfg.loadCreds()
		if err != nil {
			return err
		}
		if tok, ok := cr.Tokens[args[0]]; ok {
			delete(cr.Tokens, args[0])
			cr.Tokens[args[1]] = tok
		}
		if err := cfg.save(); err != nil {
			return err
		}
		return cfg.saveCreds(cr)
	}}
	del := &cobra.Command{Use: "delete NAME", Short: "Delete a context and its credential", Args: cobra.ExactArgs(1), RunE: func(_ *cobra.Command, args []string) error {
		cfg, err := loadConfig(a.G.ConfigFile)
		if err != nil {
			return err
		}
		if _, ok := cfg.Contexts[args[0]]; !ok {
			return exitWith(ExitNotFound, "not_found", fmt.Sprintf("no context %q", args[0]))
		}
		delete(cfg.Contexts, args[0])
		if cfg.CurrentContext == args[0] {
			cfg.CurrentContext = ""
		}
		cr, err := cfg.loadCreds()
		if err != nil {
			return err
		}
		delete(cr.Tokens, args[0])
		if err := cfg.save(); err != nil {
			return err
		}
		return cfg.saveCreds(cr)
	}}
	c.AddCommand(list, use, show, rename, del)
	return c
}
