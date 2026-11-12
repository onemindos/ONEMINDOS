// Command onemind is the OneMind command-line tool (v0: node commands only).
//
//	onemind node info [--root DIR] [--arch A] [--agent URL]
//	onemind nodes --hub URL [--token T] [--json]
//	onemind update status [--config F] [--json]
//	onemind update check  [--config F]
//	onemind update apply  [--config F] [--no-reboot]
//	onemind version
//
// The gateway token can come from --token or the ONEMIND_TOKEN environment
// variable (prefer the variable: flags end up in shell history).
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
