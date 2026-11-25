// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"path/filepath"

	"github.com/onemindos/onemindos/internal/plugin/scaffold"
	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/spf13/cobra"
)

func appNewCommand(a *App) *cobra.Command {
	var id, template, source, image string
	command := &cobra.Command{
		Use: "new <directory>", Short: "Scaffold local app sources", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if id == "" {
				id = filepath.Base(filepath.Clean(args[0]))
			}
			if err := scaffold.CreateApp(args[0], id, template, source, image); err != nil {
				return exitWith(ExitUsage, "scaffold_failed", err.Error())
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"created": true, "id": id, "template": template})
			}
			_, err := fmt.Fprintf(a.Stdout, "Created %s (%s). Run onemind app check in the new directory.\n", id, template)
			return err
		},
	}
	command.Flags().StringVar(&id, "id", "", "app DNS-label id (default: directory name)")
	command.Flags().StringVar(&template, "template", "declarative", "template: declarative, telemetry, container")
	command.Flags().StringVar(&source, "source", "", "HTTPS source repository URL (required)")
	command.Flags().StringVar(&image, "image", "", "digest-pinned workload image (required for container)")
	_ = command.MarkFlagRequired("source")
	return command
}

func appCheckCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use: "check [dir]", Short: "Check local source conformance and report which rating evidence is missing",
		Args: cobra.MaximumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			dir := "."
			if len(args) == 1 {
				dir = args[0]
			}

			const evidence = "A live app gate run supplies the scan, upstream, smoke and signature evidence for Bronze, Silver and Gold."
			err := validate.Directory(dir)
			if a.G.JSON {
				result := map[string]any{"valid": err == nil, "tier": "none", "missing_evidence": []string{evidence}}
				if err != nil {
					result["validation_error"] = err.Error()
				}
				if printErr := printJSON(a.Stdout, result); printErr != nil {
					return printErr
				}
			} else {
				if err == nil {
					fmt.Fprintln(a.Stdout, "Source conformance passed.")
				}
				fmt.Fprintln(a.Stdout, "Market quality: unrated.")
				fmt.Fprintln(a.Stdout, evidence)
			}
			if err != nil {
				return exitWith(ExitVerifyFailed, "validation_failed", err.Error())
			}
			return nil
		},
	}
}
