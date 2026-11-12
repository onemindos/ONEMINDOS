// SPDX-License-Identifier: Apache-2.0

// Command devrepo writes a throwaway TUF channel for local dry runs of the
// box updater (internal/update/README.md "Try it"): one bundle signed with
// keys that exist only in this process's memory and are gone when it exits.
// It is not a release tool and its output must never be published.
//
//	go run ./internal/update/tuftest/devrepo -out DIR -bundle FILE -version 0.1.1 [-board vm]
//
// DIR gets the repository (serve it over http://127.0.0.1) and DIR/root.json,
// the root to place at <tuf_root_dir>/<channel>/root.json on the test box.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/onemindos/onemindos/internal/update/tuftest"
)

func main() {
	out := flag.String("out", "", "output directory")
	bundle := flag.String("bundle", "", "bundle file to publish")
	ver := flag.String("version", "", "bundle version")
	board := flag.String("board", "vm", "board name (os/boards/<board>)")
	compat := flag.String("compatible", "", "RAUC compatible (default onemind-<board>)")
	minFrom := flag.String("min-from", "0.0.0", "min_from_version")
	security := flag.Bool("security", true, "mark as a security release")
	flag.Parse()
	if *out == "" || *bundle == "" || *ver == "" {
		flag.Usage()
		os.Exit(2)
	}
	if *compat == "" {
		*compat = "onemind-" + *board
	}
	if err := run(*out, *bundle, *ver, *board, *compat, *minFrom, *security); err != nil {
		fmt.Fprintln(os.Stderr, "devrepo:", err)
		os.Exit(1)
	}
}

func run(out, bundle, ver, board, compat, minFrom string, security bool) error {
	b, err := os.ReadFile(bundle)
	if err != nil {
		return err
	}
	r, err := tuftest.New(time.Now())
	if err != nil {
		return err
	}
	p := r.AddTarget(tuftest.Meta{Board: board, Version: ver, Compatible: compat, MinFromVersion: minFrom,
		Security: security, BuiltFromSnapshot: "dev", SBOM: "dev", CVEReport: "dev"}, b)
	if err := r.Publish(out, 0); err != nil {
		return err
	}
	fmt.Printf("published %s (DEV KEYS, discarded on exit)\nroot: %s\n", p, filepath.Join(out, "root.json"))
	return nil
}
