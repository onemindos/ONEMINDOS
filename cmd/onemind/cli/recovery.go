// SPDX-License-Identifier: Apache-2.0

package cli

// onemind recovery: getting back in with the printed emergency kit. Here `recovery kit` only groups `issue`
// (recovery_kit_issue.go). The stacked branch 25c makes `recovery kit` itself the at-the-box console and keeps
// `issue` under it: on that merge take 25c's recovery.go and add kit.AddCommand(kitIssueCommand(a)).

import "github.com/spf13/cobra"

func recoveryCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "recovery", Short: "Getting back in: the printed emergency kit"}
	kit := &cobra.Command{Use: "kit", Short: "The printed emergency kit (its state: onemind backup kit)"}
	kit.AddCommand(kitIssueCommand(a))
	root.AddCommand(kit)
	return []*cobra.Command{root}
}
