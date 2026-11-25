// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/spf13/cobra"
)

type kitState struct {
	State           string  `json:"state"`
	IssuedAt        *string `json:"issued_at"`
	ConfirmedAt     *string `json:"confirmed_at"`
	Fingerprint     *string `json:"fingerprint"`
	DiskKeyIncluded bool    `json:"disk_key_included"`
	DiskKeyKit      *struct {
		Fingerprint string `json:"fingerprint"`
		IssuedAt    string `json:"issued_at"`
	} `json:"disk_key_kit"`
	UncoveredDestination []string `json:"uncovered_destinations"`
}

type kitIssued struct {
	Kit     kitState `json:"kit"`
	OneTime struct {
		OwnerKey string `json:"owner_key"`
		DiskKey  string `json:"disk_recovery_key"`
		Text     string `json:"text"`
	} `json:"one_time"`
}

// recoveryCommands is `onemind recovery kit`: the printed emergency kit (D-028). `status` shows where the kit
// stands and never a key. `issue` asks the gateway for a new kit, which needs no backup destination. The page
// holds the owner key and, when /data is encrypted and its key is still waiting, the disk recovery key; both
// are shown once and the box keeps neither, so the page goes to a file (0600, created before anything is issued, never overwritten) or stdout.
// With an owner passkey on the box the gateway asks for it, and this command stops there (AI and the CLI only
// request; a person approves).
func recoveryCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "recovery", Short: "Getting back in: the printed emergency kit"}
	kit := &cobra.Command{Use: "kit", Short: "The printed emergency kit (GET/POST /v1/backups/kit)"}
	kit.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Whether a kit exists, its fingerprint, whether it holds the disk key, destinations it does not cover",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			var k kitState
			if err := cl.Do(bg(), http.MethodGet, "/v1/backups/kit", nil, &k); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, k)
			}
			fmt.Fprintf(a.Stdout, "kit: %s\nfingerprint: %s\ndisk key in kit: %v\n", k.State, dash(deref(k.Fingerprint)), k.DiskKeyIncluded)
			if k.DiskKeyKit != nil && !k.DiskKeyIncluded {
				fmt.Fprintf(a.Stdout, "the disk key is on the kit issued %s (fingerprint %s): keep that page\n", k.DiskKeyKit.IssuedAt, k.DiskKeyKit.Fingerprint)
			}
			if len(k.UncoveredDestination) > 0 {
				fmt.Fprintf(a.Stdout, "not covered by this kit (issue a new kit): %s\n", strings.Join(k.UncoveredDestination, ", "))
			}
			return nil
		},
	})
	var out string
	issue := &cobra.Command{
		Use:   "issue",
		Short: "Make a new kit; the page is shown once (needs no backup destination)",
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
				return err
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
					return printJSON(a.Stdout, map[string]any{"kit": k.Kit, "saved_to": out})
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
