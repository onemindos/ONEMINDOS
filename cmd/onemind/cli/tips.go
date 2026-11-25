// SPDX-License-Identifier: Apache-2.0

package cli

import (
	_ "embed"
	"os/exec"

	"github.com/spf13/cobra"
)

//go:embed tips_author.py
var tipsAuthor string

func tipsCommands(a *App) []*cobra.Command {
	group := &cobra.Command{Use: "tips", Short: "Write, check, and preview the tips pack in a OneMind checkout"}
	var root, assets string
	group.PersistentFlags().StringVar(&root, "root", "", "OneMind source checkout (defaults to the current checkout)")
	group.PersistentFlags().StringVar(&assets, "assets", "", "staged release assets, grouped by release tag")
	for _, item := range []struct{ name, help string }{
		{"check", "Check the tips, deep links, and release assets"},
		{"new", "Write a tip using the available collections and screens"},
		{"preview", "Write a static HTML preview to standard output"},
	} {
		group.AddCommand(&cobra.Command{
			Use: item.name, Short: item.help, Args: cobra.NoArgs,
			RunE: func(cmd *cobra.Command, _ []string) error {
				args := []string{"-I", "-c", tipsAuthor, cmd.Name()}
				if root != "" {
					args = append(args, "--root", root)
				}
				if assets != "" {
					args = append(args, "--assets", assets)
				}
				author := exec.CommandContext(cmd.Context(), "python3", args...)
				author.Stdin, author.Stdout, author.Stderr = a.Stdin, a.Stdout, a.Stderr
				return author.Run()
			},
		})
	}
	return []*cobra.Command{group}
}
