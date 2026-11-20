// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/spf13/cobra"
)

func pluginInspectCommand(a *App) *cobra.Command {
	var digest string
	command := &cobra.Command{Use: "inspect <layout>", Short: "Inspect pinned local plugin content (not publisher trust)", Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
		bundle, err := artifact.Open(args[0], digest)
		if err != nil {
			return exitWith(ExitVerifyFailed, "artifact_invalid", err.Error())
		}
		defer bundle.Close()
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"id": bundle.ID, "version": bundle.Version, "digest": bundle.Digest, "integrity": true, "verified": false})
		}
		fmt.Fprintf(a.Stdout, "%s %s\n%s\nContent integrity checked; publisher trust, scans and approval remain required.\n", bundle.ID, bundle.Version, bundle.Digest)
		return nil
	}}
	command.Flags().StringVar(&digest, "digest", "", "exact immutable sha256 artifact digest (required)")
	_ = command.MarkFlagRequired("digest")
	return command
}
