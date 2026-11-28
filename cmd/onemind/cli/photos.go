// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"net/http"

	"github.com/spf13/cobra"
)

// photosView is GET /v1/settings/photos: is Photos on, and why not.
type photosView struct {
	Enabled         bool    `json:"enabled"`
	OwnerSwitchOn   bool    `json:"owner_switch_on"`
	OperatorOff     bool    `json:"operator_off"`
	CanChange       bool    `json:"can_change"`
	PendingActionID *string `json:"pending_action_id"`
}

// photosSettingsCommand is `onemind photos settings [--on|--off]`, a subcommand of the `photos` group in
// photos_onboarding.go: Photos is built in and on by default.
// With no flag it shows the switch (GET /v1/settings/photos). --on or --off files app.enable or
// app.disable through PUT /v1/settings/photos; it waits in Approvals and nothing changes until an
// owner approves it through the separate approval flow. Photos data is kept.
func photosSettingsCommand(a *App) *cobra.Command {
	var on, off bool
	settings := &cobra.Command{
		Use:   "settings [--on|--off]",
		Short: "Show or change the Photos switch: on by default; changing it is an owner approval",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			if on && off {
				return exitWith(ExitUsage, "usage", "photos settings: --on and --off together")
			}
			if !on && !off {
				c, _, err := a.client()
				if err != nil {
					return err
				}
				var v photosView
				if err := c.Do(bg(), http.MethodGet, "/v1/settings/photos", nil, &v); err != nil {
					return err
				}
				if a.G.JSON {
					return printJSON(a.Stdout, v)
				}
				return printPhotos(a.Stdout, v)
			}
			word := "off"
			if on {
				word = "on"
			}
			return a.requestWrite("switch Photos "+word, http.MethodPut, "/v1/settings/photos", map[string]bool{"enabled": on})
		},
	}
	settings.Flags().BoolVar(&on, "on", false, "ask to switch Photos on (owners approve)")
	settings.Flags().BoolVar(&off, "off", false, "ask to switch Photos off; its photos are kept (owners approve)")
	settings.Flags().Bool("no-approve", false, "only file the request (the default)")
	_ = settings.Flags().MarkHidden("no-approve")
	return settings
}

func printPhotos(out io.Writer, v photosView) error {
	state := "off"
	if v.Enabled {
		state = "on"
	}
	fmt.Fprintf(out, "photos: %s\n", state)
	if v.OperatorOff {
		fmt.Fprintln(out, "switched off in the box's configuration (ONEMIND_PHOTOS_ENABLED=0); an operator has to change that")
	} else if !v.OwnerSwitchOn {
		fmt.Fprintln(out, "switched off by the owner; `onemind photos settings --on` asks to switch it back on")
	}
	if v.PendingActionID != nil {
		fmt.Fprintf(out, "waiting for an owner: onemind actions approve %s\n", *v.PendingActionID)
	}
	return nil
}
