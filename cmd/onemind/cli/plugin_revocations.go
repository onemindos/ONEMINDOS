// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"os"

	"github.com/onemindos/onemindos/internal/plugin/verify"
	"github.com/spf13/cobra"
)

func pluginRevocationsCommand(a *App) *cobra.Command {
	var root, metadataURL, targetsURL, state, id, version, digest string
	c := &cobra.Command{Use: "revocations", Short: "Check the TUF-authorized plugin revocation list", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, args []string) error {
		if (id != "" || version != "" || digest != "") && (id == "" || version == "" || digest == "") {
			return exitWith(ExitUsage, "revocation_options", "--id, --version and --digest must be supplied together")
		}
		f, err := os.Open(root)
		if err != nil {
			return exitWith(ExitVerifyFailed, "revocations_invalid", "cannot open trusted root")
		}
		trusted, err := io.ReadAll(io.LimitReader(f, 512001))
		f.Close()
		if err != nil {
			return exitWith(ExitVerifyFailed, "revocations_invalid", "cannot read trusted root")
		}
		r, err := verify.FetchRevocations(verify.RevocationConfig{TrustedRoot: trusted, MetadataURL: metadataURL, TargetsURL: targetsURL, StateDir: state})
		if err != nil {
			return exitWith(ExitVerifyFailed, "revocations_invalid", err.Error())
		}
		matches := []verify.Revocation{}
		if id != "" {
			matches, err = r.Match(id, version, digest)
			if err != nil {
				return exitWith(ExitVerifyFailed, "revocations_invalid", err.Error())
			}
			if matches == nil {
				matches = []verify.Revocation{}
			}
		}
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"revocations_verified": true, "version": r.Version, "expires": r.Expires, "valid_until": r.ValidUntil(), "entries": r.Entries, "matches": matches})
		}
		fmt.Fprintf(a.Stdout, "Verified revocation list %d; expires %s (%d entries).\n", r.Version, r.Expires.Format("2006-01-02T15:04:05Z07:00"), len(r.Entries))
		for _, e := range matches {
			fmt.Fprintf(a.Stdout, "%s: %s (%s)\n", e.ID, e.Action, e.Reason)
		}
		return nil
	}}
	c.Flags().StringVar(&root, "root", "", "operator-trusted TUF root file (never a publisher-supplied root)")
	c.Flags().StringVar(&metadataURL, "metadata-url", "", "HTTPS TUF metadata base URL")
	c.Flags().StringVar(&targetsURL, "targets-url", "", "HTTPS TUF targets base URL")
	c.Flags().StringVar(&state, "state", "", "persistent owner-owned plugin trust state directory")
	c.Flags().StringVar(&id, "id", "", "plugin id to match")
	c.Flags().StringVar(&version, "version", "", "plugin version to match")
	c.Flags().StringVar(&digest, "digest", "", "exact plugin digest to match")
	for _, name := range []string{"root", "metadata-url", "targets-url", "state"} {
		_ = c.MarkFlagRequired(name)
	}
	return c
}
