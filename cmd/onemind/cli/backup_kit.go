// SPDX-License-Identifier: Apache-2.0

package cli

// onemind backup kit: the emergency kit's state, and attaching the printed owner key to backup
// destinations added after the kit was made (design 25a). The key is read from stdin, sent once over
// the gateway connection and never printed or saved. Issuing a kit is the dashboard (which shows the key
// once and has the owner type two groups back) or `onemind recovery kit issue` (recovery.go).

import (
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"

	"github.com/spf13/cobra"
)

// kitGroup is one 4-letter group of the printed key (base32: A-Z and 2-7).
var kitGroup = regexp.MustCompile(`\b[A-Z2-7]{4}\b`)

func backupKitCommand(a *App) *cobra.Command {
	kit := &cobra.Command{
		Use:   "kit",
		Short: "The emergency kit: is it made, confirmed, on every destination, with the disk key? (GET /v1/backups/kit)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/backups/kit", func(w io.Writer, v any) error {
				m := obj(v)
				var missing []string
				for _, d := range list(m["missing_on"]) {
					missing = append(missing, str(d))
				}
				return kv(w, [][2]string{
					{"state", str(m["state"])},
					{"issued", dash(str(m["issued_at"]))},
					{"confirmed", dash(str(m["confirmed_at"]))},
					{"fingerprint", dash(str(m["fingerprint"]))},
					{"disk key", dash(str(m["disk_key"]))},
					{"not on", dash(strings.Join(missing, ", "))},
				})
			})
		},
	}
	kit.AddCommand(&cobra.Command{
		Use:   "attach",
		Short: "Add the printed owner key (on stdin: 13 groups, then the check group) to destinations added after the kit",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if a.G.TokenStdin {
				return usageErr(cmd, "the key is read from stdin: set ONEMIND_TOKEN instead of --token-stdin")
			}
			raw, err := io.ReadAll(io.LimitReader(a.Stdin, 4096))
			if err != nil {
				return err
			}
			groups := kitGroup.FindAllString(strings.ToUpper(string(raw)), -1)
			if len(groups) != 14 {
				return usageErr(cmd, fmt.Sprintf("expected the 13 key groups and the check group on stdin, found %d groups", len(groups)))
			}
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/backups/kit/attach", freshKey(),
				map[string]any{"groups": groups[:13], "check": groups[13]})
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				m := obj(v)
				if obj(m["action"])["id"] == nil {
					_, err := fmt.Fprintln(w, "every destination already holds the owner key")
					return err
				}
				act := obj(m["action"])
				_, err := fmt.Fprintf(w, "%s: %s\n", str(act["id"]), str(act["state"]))
				return err
			})
		},
	})
	return kit
}
