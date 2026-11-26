// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// keyboardCommands is `onemind keyboard` (P-11): the layout of the text console (tty1-tty6, the tty2 login) and the
// box's own screen. `show` reads GET /v1/system/keyboard (owner only). `set` files a system.set_keymap action
// (POST /v1/system/keyboard) and prints its id: an owner approves it in the dashboard (Approvals) or the phone app, then
// the box writes the layout to /data (it survives reboots and updates) and loads it. The CLI never approves it, so an
// agent's token can ask but not change anything.
func keyboardCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "keyboard", Short: "The keyboard layout of the box's text console and screen (owner)"}
	var layouts bool
	show := &cobra.Command{
		Use:   "show",
		Short: "The layout chosen now; --layouts lists every layout this image offers (GET /v1/system/keyboard)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			v, err := cl.Keyboard.Get(bg())
			if err != nil {
				return err
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, v); err != nil {
					return err
				}
			}
			if !v.Available || v.Current == nil {
				return exitWith(ExitUnreachable, "host_unavailable", "keyboard: "+sanitize(deref(v.Message)))
			}
			if a.G.JSON {
				return nil
			}
			if layouts {
				return table(a.Stdout, "LAYOUT\tNAME\tVARIANTS", KeyboardRows(v))
			}
			c := v.Current
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, sanitize(keyboardLabel(c.Layout, c.Variant)))
				return nil
			}
			fmt.Fprintf(a.Stdout, "Keyboard layout: %s%s\n", sanitize(keyboardLabel(c.Layout, c.Variant)), layoutName(v, c.Layout, c.Variant))
			if v.Seeded != nil && *v.Seeded {
				fmt.Fprintln(a.Stdout, "Nothing is chosen yet: the box uses the US layout. Choose one with: onemind keyboard set LAYOUT")
			}
			if c.Options != "" {
				fmt.Fprintf(a.Stdout, "Options: %s\n", sanitize(c.Options))
			}
			return nil
		},
	}
	show.Flags().BoolVar(&layouts, "layouts", false, "list every layout and variant this image offers instead")

	var reason string
	set := &cobra.Command{
		Use:   "set LAYOUT [VARIANT]",
		Short: "Ask to change the layout (for example de, or de nodeadkeys); prints the approval id an owner approves",
		Args:  cobra.RangeArgs(1, 2),
		RunE: func(_ *cobra.Command, args []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			req := onemind.KeyboardRequest{Layout: args[0], Reason: reason, IdempotencyKey: "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
			if len(args) == 2 {
				req.Variant = args[1]
			}
			act, err := cl.Keyboard.Set(bg(), req)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, act)
			}
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, sanitize(act.Id))
				return nil
			}
			fmt.Fprintf(a.Stdout, "Keyboard layout %s requested. Approval id: %s\nAn owner approves it in the dashboard (Approvals) or the phone app; follow it with: onemind actions info %s\n",
				sanitize(keyboardLabel(req.Layout, req.Variant)), sanitize(act.Id), sanitize(act.Id))
			return nil
		},
	}
	set.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	g.AddCommand(show, set)
	return []*cobra.Command{g}
}

func keyboardLabel(layout, variant string) string {
	if variant == "" {
		return layout
	}
	return layout + " (" + variant + ")"
}

// layoutName is " - German" after the layout, when the image's list names it.
func layoutName(v *onemind.KeyboardView, layout, variant string) string {
	if v.Layouts == nil {
		return ""
	}
	for _, l := range *v.Layouts {
		if l.Id != layout {
			continue
		}
		for _, x := range l.Variants {
			if variant != "" && x.Id == variant {
				return " - " + sanitize(x.Name)
			}
		}
		return " - " + sanitize(l.Name)
	}
	return ""
}

// KeyboardRows is the `--layouts` table: layout id, its name, and its variant ids.
func KeyboardRows(v *onemind.KeyboardView) [][]string {
	var rows [][]string
	if v.Layouts == nil {
		return rows
	}
	for _, l := range *v.Layouts {
		ids := make([]string, 0, len(l.Variants))
		for _, x := range l.Variants {
			ids = append(ids, sanitize(x.Id))
		}
		rows = append(rows, []string{sanitize(l.Id), sanitize(l.Name), strings.Join(ids, " ")})
	}
	return rows
}
