// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
)

func (a *App) accountSecurityCommands(stdin *bool) []*cobra.Command {
	email := &cobra.Command{Use: "email [ADDRESS]", Short: "Set an optional email address, or clear it with no address",
		Args: cobra.MaximumNArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			var address any
			if len(args) > 0 {
				address = args[0]
			}
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodPatch, "/v1/me", map[string]any{"email": address}, &out); err != nil {
				return err
			}
			return a.accountResult("Email preference saved.", out)
		}}
	verifyEmail := &cobra.Command{Use: "verify-email", Short: "Verify your optional email using a code sent by the box",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			var challenge accountChallenge
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/email/options", nil, &challenge); err != nil {
				return err
			}
			code, err := a.accountSecret("Verification code from your email", *stdin)
			if err != nil {
				return err
			}
			body := map[string]string{"challenge_id": challenge.ID, "code": strings.TrimSpace(code)}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/email/verify", body, nil); err != nil {
				return err
			}
			return a.accountResult("Email verified.", map[string]bool{"email_verified": true})
		}}
	password := a.accountPasswordCmd(stdin)
	totp := a.accountTotpCmd(stdin)
	passkeys := &cobra.Command{Use: "passkeys", Short: "Manage your registered passkeys",
		Long: "List or revoke your passkeys. To add one, sign in in the dashboard and open Settings > Security > Sign-in keys."}
	passkeys.AddCommand(&cobra.Command{Use: "list", Short: "List your registered passkeys", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodGet, "/v1/auth/passkeys", nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			var rows [][]string
			for _, raw := range list(out) {
				key := obj(raw)
				rows = append(rows, []string{str(key["credential_id"]), sanitize(str(key["label"])), str(key["level"])})
			}
			return table(a.Stdout, "ID\tLABEL\tLEVEL", rows)
		}})
	passkeys.AddCommand(&cobra.Command{Use: "revoke ID", Short: "Revoke a registered passkey", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodDelete, "/v1/auth/passkeys/"+url.PathEscape(args[0]), nil, nil); err != nil {
				return explainGateway(err)
			}
			return a.accountResult("Passkey revoked.", map[string]bool{"revoked": true})
		}})
	return []*cobra.Command{accountShowCmd(a), email, verifyEmail, password, totp, passkeys, a.remoteAccountRecovery(stdin)}
}

// accountPasswordCmd changes your own password. Interactively it asks for the new one twice; with --password-stdin
// or --secrets-stdin it reads two lines: the current password, then the new one. The gateway needs a signed-in
// session, checks the current password and signs out your other sessions.
func (a *App) accountPasswordCmd(stdin *bool) *cobra.Command {
	var passwordStdin bool
	c := &cobra.Command{Use: "password", Short: "Change your password and end your other sessions",
		Long: "Asks for your current password and the new one twice, without echo. With --password-stdin (or --secrets-stdin)\n" +
			"it reads two lines instead: the current password, then the new one. Needs a signed-in session, not an API token.",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			fromStdin := passwordStdin || *stdin
			prompts := []string{"Current password", "New password (at least 12 characters)", "New password again"}
			if fromStdin {
				prompts = prompts[:2]
			}
			got, err := a.secrets(fromStdin, prompts...)
			if err != nil {
				return err
			}
			if !fromStdin && got[1] != got[2] {
				return exitWith(ExitUsage, "usage", "the two new passwords are not the same; nothing was changed")
			}
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			body := map[string]string{"current_password": got[0], "new_password": got[1]}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/password", body, nil); err != nil {
				return explainAccount(err)
			}
			return a.accountResult("Password changed. Your other devices were signed out.",
				map[string]any{"schema": "onemind.cli.account/v1", "password_changed": true, "other_sessions_revoked": true})
		}}
	c.Flags().BoolVar(&passwordStdin, "password-stdin", false, "read the current and the new password from stdin, one per line")
	return c
}

// accountTotpCmd manages the authenticator code (TOTP), asked after the password (D-034).
func (a *App) accountTotpCmd(stdin *bool) *cobra.Command {
	g := &cobra.Command{Use: "totp", Short: "Authenticator code (TOTP), asked after your password; passkeys are recommended"}
	g.AddCommand(&cobra.Command{Use: "setup", Short: "Start setting up an authenticator code: prints the key once",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			var s totpSetup
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/setup", nil, &s); err != nil {
				return explainAccount(err)
			}
			if s.OneTime.OtpauthURI == "" {
				return fmt.Errorf("the box returned no authenticator address")
			}
			if a.G.JSON {
				return printJSON(a.Stdout, s)
			}
			fmt.Fprintln(a.Stderr, totpFallbackNote)
			fmt.Fprintf(a.Stdout, "Key (shown once): %s\nLink for a QR code: %s\n", s.OneTime.Secret, s.OneTime.OtpauthURI)
			fmt.Fprintln(a.Stderr, "Add the key to your authenticator app, then run: onemind account totp confirm <6-digit code>")
			return nil
		}})
	g.AddCommand(&cobra.Command{Use: "confirm [CODE]", Short: "Turn the authenticator code on with the 6 digits your app shows now",
		Long: "Pass the code as an argument, or leave it out to be asked for it (or read it from stdin with --secrets-stdin).",
		Args: cobra.MaximumNArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			var code string
			if len(args) > 0 {
				code = args[0]
			} else {
				var err error
				if code, err = a.accountSecret("Authenticator code", *stdin); err != nil {
					return err
				}
			}
			code = strings.TrimSpace(code)
			if len(code) != 6 || strings.Trim(code, "0123456789") != "" {
				return exitWith(ExitUsage, "usage", "the code is the 6 digits your authenticator app shows")
			}
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/confirm", map[string]string{"code": code}, nil); err != nil {
				return explainAccount(err)
			}
			return a.accountResult("Authenticator code on. The box asks for it after your password.",
				map[string]any{"schema": "onemind.cli.account/v1", "totp": true})
		}})
	var passwordStdin bool
	disable := &cobra.Command{Use: "disable", Short: "Turn the authenticator code off (asks for your password)",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			got, err := a.secrets(passwordStdin || *stdin, "Your password")
			if err != nil {
				return err
			}
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/disable", map[string]string{"password": got[0]}, nil); err != nil {
				return explainAccount(err)
			}
			return a.accountResult("Authenticator code off.", map[string]any{"schema": "onemind.cli.account/v1", "totp": false})
		}}
	disable.Flags().BoolVar(&passwordStdin, "password-stdin", false, "read your password from stdin")
	g.AddCommand(disable)
	return g
}

func (a *App) remoteAccountRecovery(stdin *bool) *cobra.Command {
	const path = "/v1/auth/recovery/remote"
	root := &cobra.Command{Use: "remote-recovery", Short: "Manage delayed recovery of remote approval access"}
	var kitPath string
	kit := &cobra.Command{Use: "upgrade-kit", Short: "Save a recovery code for an existing headless owner account",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			file, err := newAccountKitFile(kitPath)
			if err != nil {
				return err
			}
			defer file.Close()
			var kit accountRecoveryKit
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/setup/kit?legacy_upgrade=true", nil, &kit); err != nil {
				os.Remove(kitPath)
				return err
			}
			if err := writeAccountKit(file, kit); err != nil {
				return err
			}
			return a.accountResult("Recovery code saved. Use it to start the 72-hour wait.", map[string]string{"kit": kitPath})
		}}
	kit.Flags().StringVar(&kitPath, "kit", "", "new file for the account recovery code")
	root.AddCommand(kit)
	root.AddCommand(&cobra.Command{Use: "status", Short: "Check the recovery waiting period",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodGet, path, nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			status := obj(out)
			return kv(a.Stdout, [][2]string{
				{"state", str(status["state"])},
				{"available at", dash(str(status["available_at"]))},
				{"expires at", dash(str(status["expires_at"]))},
			})
		}})
	root.AddCommand(&cobra.Command{Use: "start", Short: "Start the 72-hour wait with the recovery-kit code",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			code, err := a.accountSecret("Code from the recovery kit", *stdin)
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodPost, path, map[string]string{"recovery_code": strings.TrimSpace(code)}, &out); err != nil {
				var authErr *onemind.Error
				if errors.As(err, &authErr) && authErr.Reason == "step_up_required" {
					return fmt.Errorf("%w\nFor the CLI, sign in again with your password and authenticator code before starting recovery", err)
				}
				return err
			}
			return a.accountResult("Recovery requested. After the wait, enrol a proven key in the dashboard.", out)
		}})
	root.AddCommand(&cobra.Command{Use: "cancel", Short: "Cancel a remote approval recovery request",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodDelete, path, nil, nil); err != nil {
				return err
			}
			return a.accountResult("Remote approval recovery cancelled.", map[string]bool{"cancelled": true})
		}})
	return root
}
