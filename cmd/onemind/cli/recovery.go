// SPDX-License-Identifier: Apache-2.0

package cli

// onemind recovery kit issue: make the printed emergency kit from a terminal (design 25a, D-020, D-028). Ported from
// #1124 onto the #1191 kit (POST /v1/backups/kit). The state of the kit stays `onemind backup kit`.

import (
	"errors"
	"fmt"
	"net/http"
	"os"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
)

// kitIssued is the part of the POST /v1/backups/kit answer (core/onemind_core/routers/backups.py) the CLI uses.
type kitIssued struct {
	Kit struct {
		State       string  `json:"state"`
		Fingerprint *string `json:"fingerprint"`
	} `json:"kit"`
	OneTime struct {
		OwnerKey     string  `json:"owner_key"`
		DiskKey      *string `json:"disk_key"`
		DiskKeyState string  `json:"disk_key_state"`
		Text         string  `json:"text"`
	} `json:"one_time"`
}

// recoveryCommands is `onemind recovery kit issue [--out FILE]`. The page holds the owner key and, when /data is
// encrypted and its key is still waiting, the disk recovery key; both are shown once and the box keeps neither, so
// the page goes to a new file (0600, created before anything is issued, never overwritten) or to stdout.
// Once an owner passkey exists the gateway needs it to approve the kit, which a terminal cannot give: the command
// stops there and nothing is issued (AI and the CLI only request; a person approves, D-027).
func recoveryCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "recovery", Short: "Getting back in: the printed emergency kit"}
	kit := &cobra.Command{Use: "kit", Short: "The printed emergency kit (its state: onemind backup kit)"}
	var out string
	issue := &cobra.Command{
		Use:   "issue",
		Short: "Make a new kit; the page is shown once (needs no backup destination) (POST /v1/backups/kit)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			// Open the file first: a new kit replaces the console fingerprint and uses up the one-time disk key, so
			// nothing may be issued unless the page has somewhere to go. An existing file stops us before the POST.
			var f *os.File
			if out != "" {
				f, err = os.OpenFile(out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
				if err != nil {
					return exitWith(ExitError, "write_failed", "nothing was issued: "+out+" cannot be created ("+err.Error()+
						"); choose a new file name")
				}
			}
			var k kitIssued
			if err := cl.Do(bg(), http.MethodPost, "/v1/backups/kit", map[string]any{}, &k); err != nil {
				if f != nil { // nothing was issued: leave no empty file behind
					f.Close()
					os.Remove(out)
				}
				return explainKitIssue(err)
			}
			if f != nil {
				_, werr := f.WriteString(k.OneTime.Text)
				if cerr := f.Close(); werr == nil {
					werr = cerr
				}
				if werr != nil {
					return exitWith(ExitError, "write_failed", "the kit was issued but could not be saved; issue another kit")
				}
				if a.G.JSON {
					return printJSON(a.Stdout, map[string]any{"kit": k.Kit, "disk_key_state": k.OneTime.DiskKeyState, "saved_to": out})
				}
				fmt.Fprintf(a.Stdout, "kit saved to %s (fingerprint %s). Print it and keep it offline.\n", out, dash(deref(k.Kit.Fingerprint)))
				return nil
			}
			if a.G.JSON {
				return printJSON(a.Stdout, k)
			}
			_, err = fmt.Fprint(a.Stdout, k.OneTime.Text)
			return err
		},
	}
	issue.Flags().StringVar(&out, "out", "", "write the kit page to this new file (mode 0600) instead of the terminal")
	kit.AddCommand(issue)
	g.AddCommand(kit)
	return []*cobra.Command{g}
}

// explainKitIssue says where to go when the kit needs the owner's passkey. The request the gateway filed stays
// pending for 10 minutes and cannot be approved in Approvals (it would show nobody the kit), so point at the kit screen.
func explainKitIssue(err error) error {
	var e *onemind.Error
	if errors.As(err, &e) && e.Reason == "step_up_required" {
		return fmt.Errorf("%w\nNothing was issued. This box has an owner passkey, which the CLI cannot use: make the kit in the "+
			"dashboard (Backups, Emergency Kit), where your passkey approves it and the page is shown once", err)
	}
	return err
}
