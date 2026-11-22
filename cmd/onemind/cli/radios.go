// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"

	"github.com/spf13/cobra"
)

// radioCard is one row of GET /v1/radios (core/onemind_core/apimodels.py RadioCard, #732).
type radioCard struct {
	NodeID     string  `json:"node_id"`
	Hostname   *string `json:"hostname"`
	NodeStatus string  `json:"node_status"`
	Kind       *string `json:"kind"`
	Model      *string `json:"model"`
	Match      *string `json:"match"`
	TTY        string  `json:"tty"`
	Device     *string `json:"device"`
	USBID      *string `json:"usb_id"`
	USBPort    *string `json:"usb_port"`
}

func radiosCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "radios",
		Short: "Radio dongles plugged into the machines (GET /v1/radios); unknown serial devices are listed, never named",
		Long: "Lists every USB serial line the machines report. A known Zigbee, Thread or LoRa dongle shows its\n" +
			"kind and its stable name under /dev/onemind; anything else shows kind \"unknown\" and no name, and\n" +
			"can never be granted to an app. A model marked \"(chip)\" was recognised only by its USB chip.",
		Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if a.G.JSON {
				var raw []any
				if err := c.Do(bg(), http.MethodGet, "/v1/radios", nil, &raw); err != nil {
					return err
				}
				return printJSON(a.Stdout, raw)
			}
			var cards []radioCard
			if err := c.Do(bg(), http.MethodGet, "/v1/radios", nil, &cards); err != nil {
				return err
			}
			rows := make([][]string, 0, len(cards))
			for _, r := range cards {
				model := strOr(r.Model, "-")
				if r.Match != nil && *r.Match == "chip" {
					model += " (chip)"
				}
				rows = append(rows, []string{r.NodeID, strOr(r.Hostname, "-"), strOr(r.Kind, "unknown"), model,
					strOr(r.USBPort, "-"), r.TTY, strOr(r.Device, "-"), r.NodeStatus})
			}
			return table(a.Stdout, "NODE_ID\tHOSTNAME\tKIND\tMODEL\tPORT\tTTY\tDEVICE\tNODE", rows)
		},
	}
}

func strOr(s *string, def string) string {
	if s == nil || *s == "" {
		return def
	}
	return *s
}
