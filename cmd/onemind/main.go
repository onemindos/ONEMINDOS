// Command onemind is the OneMind command-line tool: talk to a box's gateway (login, status,
// nodes, apps, actions, audit), run the MCP bridge for AI agents, and manage OS updates on the
// box itself. The command tree, --json and exit codes are specified in docs/leap/dev/CLI.md.
//
// The gateway token comes from the context saved by `onemind login`, ONEMIND_TOKEN or
// --token-stdin (--token works but lands in shell history).
//
// The commands live in package cli, one file per group (cli/root.go has the registry).
package main

import (
	"io"
	"os"

	"github.com/onemindos/onemindos/cmd/onemind/cli"
)

// newEngine is replaced in tests (fake rauc, restic and reboot).
var newEngine = cli.DefaultEngine

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	return cli.Run(args, cli.Env{Stdout: stdout, Stderr: stderr, NewEngine: newEngine})
}
