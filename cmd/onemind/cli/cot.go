// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"time"

	"github.com/onemindos/onemindos/internal/cot"
	"github.com/spf13/cobra"
)

func cotCommands(a *App) []*cobra.Command {
	group := &cobra.Command{Use: "cot", Short: "Work with Cursor on Target events"}
	group.AddCommand(&cobra.Command{
		Use:   "validate",
		Short: "Validate one recorded CoT XML event from standard input",
		Long:  "Validate one recorded CoT XML event from standard input without checking it against the local clock.",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			data, err := io.ReadAll(io.LimitReader(cmd.InOrStdin(), cot.MaxEventBytes+1))
			if err != nil {
				return fmt.Errorf("read CoT event: %w", err)
			}
			// A recorded event can be checked independently of the local clock.
			if _, err := cot.Decode(data, time.Time{}); err != nil {
				return exitWith(ExitVerifyFailed, "cot_invalid", err.Error())
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]bool{"valid": true})
			}
			_, err = fmt.Fprintln(a.Stdout, "Valid CoT XML event")
			return err
		},
	})
	return []*cobra.Command{group}
}
