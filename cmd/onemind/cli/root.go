// SPDX-License-Identifier: Apache-2.0

// Package cli holds the onemind commands, one file per command group (docs/leap/core/PLUMBING.md
// §6, docs/leap/dev/CLI.md). A group is a function returning its top-level cobra commands;
// adding a group is one new file plus one line in groups below. Built with cobra (F-8).
package cli

import (
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/onemindos/onemindos/internal/update"
)

// Env is what a command gets besides its arguments.
type Env struct {
	Stdout, Stderr io.Writer
	// Stdin defaults to os.Stdin; Interactive reports whether prompts may be shown (a TTY).
	Stdin       io.Reader
	Interactive func() bool
	// NewEngine builds the OS update engine; tests replace it (fake rauc, restic and reboot).
	NewEngine func(c *update.Config, log *slog.Logger) *update.Engine
}

// Global flags (CLI.md §3.1). Precedence: flag, then environment, then context, then default.
type Global struct {
	Context    string
	Hub        string
	Token      string
	TokenStdin bool
	JSON       bool
	Quiet      bool
	NoColor    bool
	Timeout    time.Duration
	Verbose    bool
	ConfigFile string
}

// App is shared by every command of one invocation.
type App struct {
	Env
	G Global
}

// groups is the registry, in help order. One line per command group.
var groups = []func(a *App) []*cobra.Command{
	loginCommands,
	statusCommands,
	nodeCommands,
	appsCommands,
	actionsCommands,
	auditCommands,
	updateCommands,
	mcpCommands,
	versionCommands,
}

// DefaultEngine is the real update engine constructor.
func DefaultEngine(c *update.Config, log *slog.Logger) *update.Engine { return update.New(c, log) }

func envDuration(k string, def time.Duration) time.Duration {
	if d, err := time.ParseDuration(os.Getenv(k)); err == nil && d > 0 {
		return d
	}
	return def
}

// NewRoot builds the command tree for one invocation.
func NewRoot(env Env) (*cobra.Command, *App) {
	if env.NewEngine == nil {
		env.NewEngine = DefaultEngine
	}
	if env.Stdin == nil {
		env.Stdin = os.Stdin
	}
	if env.Interactive == nil {
		env.Interactive = func() bool {
			f, ok := env.Stdin.(*os.File)
			return ok && term.IsTerminal(int(f.Fd()))
		}
	}
	a := &App{Env: env}
	root := &cobra.Command{
		Use:   "onemind",
		Short: "Run and develop for a OneMind box",
		Long: "onemind talks to the gateway of a OneMind box: nodes, apps, the approval queue, the audit log,\n" +
			"updates and the MCP bridge for AI agents. `apps` acts on a box; `app` (developer) works on a folder.\n" +
			"Every change is a request that an owner approves; --json prints the gateway's objects unchanged.",
		SilenceUsage:  true,
		SilenceErrors: true,
		Args:          cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return usageErr(cmd, "a command is required")
		},
	}
	root.SetOut(env.Stdout)
	root.SetErr(env.Stderr)
	root.SetIn(env.Stdin)
	pf := root.PersistentFlags()
	pf.StringVar(&a.G.Context, "context", os.Getenv("ONEMIND_CONTEXT"), "which box (context) to talk to")
	pf.StringVar(&a.G.Hub, "hub", os.Getenv("ONEMIND_HUB"), "gateway URL, overrides the context (e.g. https://hub.local:8443)")
	pf.StringVar(&a.G.Token, "token", "", "bearer token (prefer ONEMIND_TOKEN or --token-stdin: flags land in shell history)")
	pf.BoolVar(&a.G.TokenStdin, "token-stdin", false, "read the token from stdin")
	pf.BoolVar(&a.G.JSON, "json", false, "machine output: the gateway's JSON, unchanged")
	pf.BoolVarP(&a.G.Quiet, "quiet", "q", false, "only errors and the essential value")
	pf.BoolVar(&a.G.NoColor, "no-color", os.Getenv("NO_COLOR") != "", "no colour")
	pf.DurationVar(&a.G.Timeout, "timeout", envDuration("ONEMIND_TIMEOUT", 30*time.Second), "per request")
	pf.BoolVarP(&a.G.Verbose, "verbose", "v", os.Getenv("ONEMIND_DEBUG") == "1", "log each HTTP call (method, path, status, time) to stderr")
	pf.StringVar(&a.G.ConfigFile, "config", os.Getenv("ONEMIND_CONFIG"), "config file (default ~/.config/onemind/config.yaml)")
	root.SetFlagErrorFunc(func(cmd *cobra.Command, err error) error { return usageErr(cmd, err.Error()) })
	for _, g := range groups {
		root.AddCommand(g(a)...)
	}
	setUsageOnGroups(root)
	return root, a
}

// setUsageOnGroups makes a bare group (`onemind apps`) a usage error, not a silent help page.
func setUsageOnGroups(c *cobra.Command) {
	for _, sub := range c.Commands() {
		if sub.HasSubCommands() && sub.RunE == nil && sub.Run == nil {
			sub.Args = cobra.ArbitraryArgs
			sub.RunE = func(cmd *cobra.Command, args []string) error {
				if len(args) > 0 {
					return usageErr(cmd, fmt.Sprintf("unknown command %q for %q", args[0], cmd.CommandPath()))
				}
				return usageErr(cmd, "a subcommand is required")
			}
		}
		setUsageOnGroups(sub)
	}
}

// Run executes args and returns the exit code (CLI.md §4.2).
func Run(args []string, env Env) int {
	root, a := NewRoot(env)
	root.SetArgs(args)
	err := root.Execute()
	if err == nil {
		return ExitOK
	}
	code, name := exitFor(err)
	var ue *usageError
	if errors.As(err, &ue) {
		fmt.Fprintf(env.Stderr, "onemind: %s\n\n%s", ue.msg, ue.usage)
		return ExitUsage
	}
	if strings.HasPrefix(err.Error(), "unknown command") || strings.HasPrefix(err.Error(), "unknown flag") {
		fmt.Fprintf(env.Stderr, "onemind: %s\n\n%s", err, root.UsageString())
		return ExitUsage
	}
	if a.G.JSON {
		fmt.Fprintf(env.Stderr, "%s\n", mustJSON(map[string]any{"error": name, "message": err.Error(), "exit_code": code}))
	} else {
		fmt.Fprintln(env.Stderr, "onemind:", sanitize(err.Error()))
	}
	return code
}

type usageError struct{ msg, usage string }

func (e *usageError) Error() string { return e.msg }

func usageErr(cmd *cobra.Command, msg string) error {
	return &usageError{msg: msg, usage: cmd.UsageString()}
}

// Usage is the root usage text (kept for callers of the pre-cobra API).
func Usage() string {
	root, _ := NewRoot(Env{Stdout: io.Discard, Stderr: io.Discard})
	return root.UsageString()
}
