// SPDX-License-Identifier: Apache-2.0

package cli

// onemind kiosk: the owner turns the box's own screen from the text screen into the full-screen
// dashboard (UX-07, #242 part 2). It is a local, root-on-the-box action: it creates or removes the
// flag file that onemind-kiosk.service and onemind-screen.service test (ConditionPathExists). First boot
// switches it on once on the boards made for a monitor (founder decision 2026-11-28); after that the choice
// is the owner's and first boot never changes it back. It talks to no gateway and holds no token. An owner without a shell on the box does the same over
// the API (PUT /v1/instance/kiosk): the root account is locked and the monitor boards ship no SSH.

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/spf13/cobra"
)

// kioskFlag is the file the two units test. Keep in step with os/rootfs/layers/onemind/usr/lib/systemd/system.
const kioskFlag = "/data/onemind/kiosk/enabled"

const kioskApply = "The screen switches within a few seconds (onemind-kiosk.path); or: systemctl restart onemind-screen onemind-kiosk."

func kioskCommands(a *App) []*cobra.Command {
	var flag string
	k := &cobra.Command{Use: "kiosk", Short: "Show the dashboard full screen on this box's monitor (run on the box, as root)"}
	k.PersistentFlags().StringVar(&flag, "flag-file", kioskFlag, "the flag file the screen units test")
	k.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Say whether kiosk mode is on",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			on := kioskOn(flag)
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.kiosk/v1", "enabled": on})
			}
			if on {
				fmt.Fprintln(a.Stdout, "kiosk: on (the monitor shows the dashboard)")
			} else {
				fmt.Fprintln(a.Stdout, "kiosk: off (the monitor shows the text screen)")
			}
			return nil
		},
	})
	k.AddCommand(&cobra.Command{
		Use:   "enable",
		Short: "Turn kiosk mode on: the monitor shows the dashboard (the launcher keeps no token; a session signed in at the box locks when idle)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			if err := os.MkdirAll(filepath.Dir(flag), 0o755); err != nil {
				return fmt.Errorf("kiosk enable: %w (run on the box, as root)", err)
			}
			if err := os.WriteFile(flag, []byte("on\n"), 0o644); err != nil {
				return fmt.Errorf("kiosk enable: %w (run on the box, as root)", err)
			}
			fmt.Fprintln(a.Stdout, "kiosk: on. "+kioskApply)
			return nil
		},
	})
	k.AddCommand(&cobra.Command{
		Use:   "disable",
		Short: "Turn kiosk mode off: the monitor shows the text screen again",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			if err := os.Remove(flag); err != nil && !os.IsNotExist(err) {
				return fmt.Errorf("kiosk disable: %w (run on the box, as root)", err)
			}
			fmt.Fprintln(a.Stdout, "kiosk: off. "+kioskApply)
			return nil
		},
	})
	return []*cobra.Command{k}
}

func kioskOn(flag string) bool {
	_, err := os.Stat(flag)
	return err == nil
}
