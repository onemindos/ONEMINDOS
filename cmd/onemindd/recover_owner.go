// SPDX-License-Identifier: Apache-2.0

package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"golang.org/x/term"

	"github.com/onemindos/onemindos/internal/kitrecovery"
)

// runRecoverOwner is `onemindd recover-owner`: the box's console menu for recovering owner access with the
// printed emergency kit (gateway permissions design 25c). onemind-recovery-console.service runs it on tty3 with
// --loop, so a screen and keyboard at the box can always reach it; root on the box can run it once by hand.
func runRecoverOwner(args []string) int {
	fs := flag.NewFlagSet("onemindd recover-owner", flag.ContinueOnError)
	gateway := fs.String("gateway", env("ONEMIND_RECOVERY_GATEWAY", kitrecovery.DefaultGateway), "the gateway on this box (loopback)")
	keyFile := fs.String("key-file", env("ONEMIND_CONSOLE_KEY_FILE", kitrecovery.DefaultKeyFile), "the console key the gateway made")
	loop := fs.Bool("loop", false, "offer the menu again after each session (the tty3 unit)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	in := bufio.NewReader(os.Stdin)
	for {
		if *loop {
			fmt.Println("\nOneMind owner recovery. Lost every passkey? Have your printed emergency kit ready.")
			fmt.Print("Press Enter to start. ")
			if _, err := in.ReadString('\n'); err != nil {
				return 0
			}
		}
		c := &kitrecovery.Console{Gateway: *gateway, KeyFile: *keyFile, In: in, Out: os.Stdout}
		if term.IsTerminal(int(os.Stdin.Fd())) {
			c.ReadSecret = func() (string, error) {
				b, err := term.ReadPassword(int(os.Stdin.Fd()))
				return string(b), err
			}
		}
		err := c.Run(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, "onemindd recover-owner:", err)
		}
		if !*loop || ctx.Err() != nil {
			if err != nil {
				return 1
			}
			return 0
		}
	}
}
