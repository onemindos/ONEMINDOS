// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/spf13/cobra"
)

func appTestCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "test",
		Short: "Prove that the local gateway refuses forbidden app requests",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			const harness = "sdk/tools/app-refusals"
			for _, file := range []string{harness, "core/pyproject.toml"} {
				info, err := os.Lstat(file)
				if err != nil || !info.Mode().IsRegular() {
					return exitWith(ExitUsage, "checkout_required", "run this command from the OneMind source checkout root")
				}
			}
			child := exec.CommandContext(cmd.Context(), "python3", "-I", filepath.FromSlash(harness))
			child.Stdout, child.Stderr = a.Stdout, a.Stderr
			if err := child.Run(); err != nil {
				return exitWith(ExitVerifyFailed, "refusals_failed", fmt.Sprintf("app refusal harness: %v", err))
			}
			return nil
		},
	}
}
