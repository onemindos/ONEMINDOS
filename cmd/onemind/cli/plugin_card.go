// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"io"
	"os"

	"github.com/onemindos/onemindos/sdk/schema"
	"github.com/spf13/cobra"
)

// pluginCardCommand is `onemind plugin card validate FILE...` (issue #727): offline checks of device
// capability cards against sdk/schema/onemind.device-card.schema.json and the shared rules.
func pluginCardCommand(a *App) *cobra.Command {
	card := &cobra.Command{Use: "card", Short: "Device capability cards (local, offline checks)"}
	card.AddCommand(&cobra.Command{
		Use: "validate FILE...", Short: "Validate device capability cards (safety class, limits, units, no credentials)",
		Args: cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			results := []map[string]any{}
			failed := false
			for _, path := range args {
				data, err := readCard(path)
				if err == nil {
					err = schema.ValidateDeviceCard(data)
				}
				res := map[string]any{"file": path, "valid": err == nil}
				var ce *schema.CardError
				switch {
				case errors.As(err, &ce):
					res["problems"] = ce.Problems
				case err != nil:
					res["problems"] = []schema.CardProblem{{Rule: "read", Path: "/", Message: err.Error()}}
				}
				failed = failed || err != nil
				results = append(results, res)
				if !a.G.JSON {
					if err == nil {
						fmt.Fprintf(a.Stdout, "%s: valid\n", path)
					} else {
						fmt.Fprintf(a.Stdout, "%s: %v\n", path, err)
					}
				}
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, map[string]any{"valid": !failed, "cards": results}); err != nil {
					return err
				}
			}
			if failed {
				return exitWith(ExitVerifyFailed, "validation_failed", "one or more device cards are invalid")
			}
			return nil
		},
	})
	return card
}

func readCard(path string) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("a card must be a regular file")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return io.ReadAll(io.LimitReader(f, schema.MaxDeviceCardBytes+1))
}
