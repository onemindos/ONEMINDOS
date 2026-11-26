// SPDX-License-Identifier: Apache-2.0

package cli

// onemind recovery kit: recover owner access with the printed emergency kit, at the box (gateway permissions
// design 25c). It runs only on the box itself, as root: it reads the console key the gateway made and talks to the
// gateway on loopback, the same as the tty2 console menu (onemindd recover-owner). From any other computer it
// cannot work, by design: the kit path is in person.

import (
	"context"
	"os"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/onemindos/onemindos/internal/kitrecovery"
)

func recoveryCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "recovery", Short: "Get owner access back (at the box, with the printed emergency kit)"}
	var gateway, keyFile string
	kit := &cobra.Command{
		Use:   "kit",
		Short: "At the box, as root: type the kit key to set a new password, remove lost passkeys, add a new one",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c := &kitrecovery.Console{Gateway: gateway, KeyFile: keyFile, In: a.Stdin, Out: a.Stdout}
			if f, ok := a.Stdin.(*os.File); ok && a.Interactive() {
				c.ReadSecret = func() (string, error) {
					b, err := term.ReadPassword(int(f.Fd()))
					return string(b), err
				}
			}
			if err := c.Run(context.Background()); err != nil {
				return exitWith(ExitError, "recovery", err.Error())
			}
			return nil
		},
	}
	kit.Flags().StringVar(&gateway, "gateway", kitrecovery.DefaultGateway, "the gateway on this box (loopback)")
	kit.Flags().StringVar(&keyFile, "key-file", kitrecovery.DefaultKeyFile, "the console key the gateway made")
	root.AddCommand(kit)
	return []*cobra.Command{root}
}
