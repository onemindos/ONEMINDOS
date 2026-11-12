// SPDX-License-Identifier: Apache-2.0

// Package cli holds the onemind commands, one file per command group
// (docs/leap/core/PLUMBING.md §6). A group is a function returning its
// commands; adding a group is one new file plus one line in groups below.
package cli

import (
	"fmt"
	"io"
	"log/slog"
	"strings"

	"github.com/onemindos/onemindos/internal/update"
)

// Env is what a command gets besides its arguments.
type Env struct {
	Stdout, Stderr io.Writer
	// NewEngine builds the OS update engine; tests replace it (fake rauc, restic and reboot).
	NewEngine func(c *update.Config, log *slog.Logger) *update.Engine
}

// Command is one leaf of the command tree, e.g. Path {"update", "check"}.
type Command struct {
	Path  []string
	Usage string // the line printed under "usage:", without the two-space indent
	Run   func(env *Env, args []string) error
}

// groups is the registry, in the order the usage text lists them.
var groups = []func() []Command{
	nodeCommands,
	fabricCommands,
	meshCommands,
	updateCommands,
	versionCommands,
}

// Commands returns every registered command in usage order.
func Commands() []Command {
	var all []Command
	for _, g := range groups {
		all = append(all, g()...)
	}
	return all
}

// Usage is the text printed when no command matches.
func Usage() string {
	var b strings.Builder
	b.WriteString("usage:\n")
	for _, c := range Commands() {
		b.WriteString("  " + c.Usage + "\n")
	}
	return b.String()
}

// DefaultEngine is the real update engine constructor.
func DefaultEngine(c *update.Config, log *slog.Logger) *update.Engine { return update.New(c, log) }

// Run dispatches args to the command whose path they start with and returns
// the exit code: 0 ok, 1 command error (printed as "onemind: ..."), 2 usage.
func Run(args []string, env Env) int {
	if env.NewEngine == nil {
		env.NewEngine = DefaultEngine
	}
	cmd, rest := match(args)
	if cmd == nil {
		fmt.Fprint(env.Stderr, Usage())
		return 2
	}
	if err := cmd.Run(&env, rest); err != nil {
		fmt.Fprintln(env.Stderr, "onemind:", err)
		return 1
	}
	return 0
}

func match(args []string) (*Command, []string) {
	var best *Command
	for _, c := range Commands() {
		if len(args) < len(c.Path) || (best != nil && len(best.Path) >= len(c.Path)) {
			continue
		}
		ok := true
		for i, p := range c.Path {
			if args[i] != p {
				ok = false
				break
			}
		}
		if ok {
			c := c
			best = &c
		}
	}
	if best == nil {
		return nil, nil
	}
	return best, args[len(best.Path):]
}
