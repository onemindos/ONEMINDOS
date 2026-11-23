// SPDX-License-Identifier: Apache-2.0

package cli

// onemind ext: host extensions, plugin socket E3 (issue #186). The owner, as root on the box, stages
// a signed system extension (files under /usr) or configuration extension (files under /etc). Only
// a raw verity-signed disk image signed by a OneMind key and built for this box's extension level
// is installed; anything else is refused before it reaches /var/lib/extensions. It talks to no
// gateway: like `onemind kiosk`, it is the owner's own action on the box (internal/hostext).

import (
	"errors"
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/hostext"
)

// newHostext is replaced in tests (fake systemd tools and release reader).
var newHostext = hostext.New

func extCommands(a *App) []*cobra.Command {
	var c hostext.Config
	var keyDir, osRelease string
	mgr := func() *hostext.Manager {
		cfg := c
		if keyDir != "" {
			cfg.KeyDirs = []string{keyDir}
		}
		if osRelease != "" {
			cfg.OSRelease = []string{osRelease}
		}
		return newHostext(cfg)
	}
	kind := func(confext bool) hostext.Kind {
		if confext {
			return hostext.Confext
		}
		return hostext.Sysext
	}
	e := &cobra.Command{Use: "ext", Short: "Host extensions: signed sysext/confext images (run on the box, as root)"}
	pf := e.PersistentFlags()
	pf.StringVar(&c.Quarantine, "quarantine", "", "staging folder on /data (default /data/onemind/hostext/quarantine)")
	pf.StringVar(&c.SysextDir, "sysext-dir", "", "system extensions folder (default /var/lib/extensions)")
	pf.StringVar(&c.ConfextDir, "confext-dir", "", "configuration extensions folder (default /var/lib/confexts)")
	pf.StringVar(&keyDir, "keys", "", "folder of trusted signing certificates (default /usr/lib/verity.d, in the read-only image)")
	pf.StringVar(&osRelease, "os-release", "", "host os-release file (default /etc/os-release)")
	_ = pf.MarkHidden("keys")
	_ = pf.MarkHidden("os-release")

	var stageConf bool
	stage := &cobra.Command{
		Use:   "stage IMAGE.raw",
		Short: "Verify a signed extension image and install it (refused: unsigned, wrong key, wrong level, directories)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			x, err := mgr().Stage(cmd.Context(), args[0], kind(stageConf))
			if err != nil {
				return extErr("ext stage", err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.ext/v1", "extension": x})
			}
			fmt.Fprintf(a.Stdout, "installed %s %s (root hash %s…, key %s…); systemd-%s refreshed\n",
				x.Kind, x.Name, x.RootHash[:12], x.Fingerprint[:12], x.Kind)
			return nil
		},
	}
	stage.Flags().BoolVar(&stageConf, "confext", false, "the image is a configuration extension (/etc)")

	list := &cobra.Command{
		Use:   "list",
		Short: "List installed extensions, checking each signature again",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			xs, err := mgr().List(cmd.Context())
			if err != nil {
				return extErr("ext list", err)
			}
			if a.G.JSON {
				if xs == nil {
					xs = []hostext.Extension{}
				}
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.ext/v1", "extensions": xs})
			}
			if len(xs) == 0 {
				fmt.Fprintln(a.Stdout, "no host extensions installed")
				return nil
			}
			rows := make([][]string, 0, len(xs))
			for _, x := range xs {
				rows = append(rows, []string{string(x.Kind), sanitize(x.Name), human(uint64(x.Size)), sanitize(x.Status)})
			}
			return table(a.Stdout, "KIND\tNAME\tSIZE\tSTATUS", rows)
		},
	}

	var rmConf bool
	remove := &cobra.Command{
		Use:   "remove NAME",
		Short: "Remove an installed extension and refresh, so nothing it added stays in /usr or /etc",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			k := kind(rmConf)
			if err := mgr().Remove(cmd.Context(), args[0], k); err != nil {
				return extErr("ext remove", err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.ext/v1", "removed": strings.TrimSuffix(args[0], ".raw"), "kind": k})
			}
			fmt.Fprintf(a.Stdout, "removed %s %s; systemd-%s refreshed\n", k, strings.TrimSuffix(args[0], ".raw"), k)
			return nil
		},
	}
	remove.Flags().BoolVar(&rmConf, "confext", false, "remove a configuration extension")

	e.AddCommand(stage, list, remove)
	return []*cobra.Command{e}
}

// extErr maps hostext errors to the CLI exit codes (CLI.md §4.2).
func extErr(what string, err error) error {
	var r *hostext.RefusedError
	switch {
	case errors.As(err, &r):
		switch r.Code {
		case "unsigned", "untrusted_key", "bad_signature":
			return exitWith(ExitVerifyFailed, "verify_failed", what+": "+err.Error())
		}
		return exitWith(ExitRefused, "refused", what+": "+err.Error())
	case errors.Is(err, hostext.ErrExists):
		return exitWith(ExitConflict, "conflict", what+": "+err.Error())
	case errors.Is(err, hostext.ErrNotFound):
		return exitWith(ExitNotFound, "not_found", what+": "+err.Error())
	}
	return fmt.Errorf("%s: %w (run on the box, as root)", what, err)
}
