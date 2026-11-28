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
	password := &cobra.Command{Use: "password", Short: "Change your password and end your other sessions",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			current, err := a.accountSecret("Current password", *stdin)
			if err != nil {
				return err
			}
			newPassword, err := a.accountSecret("New password (at least 12 characters)", *stdin)
			if err != nil {
				return err
			}
			body := map[string]string{"current_password": current, "new_password": newPassword}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/password", body, nil); err != nil {
				return err
			}
			return a.accountResult("Password changed.", map[string]bool{"changed": true})
		}}
	totp := &cobra.Command{Use: "totp", Short: "Manage your authenticator app"}
	totp.AddCommand(&cobra.Command{Use: "setup", Short: "Get the address to add to your authenticator app",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/setup", nil, &out); err != nil {
				return err
			}
			address := str(obj(obj(out)["one_time"])["otpauth_uri"])
			if address == "" {
				return fmt.Errorf("the box returned no authenticator address")
			}
			return a.accountResult("Add this address in your authenticator app, then run onemind account totp confirm.\n"+address, out)
		}})
	for _, command := range []struct{ name, description, path, field, prompt, result string }{
		{"confirm", "Confirm the authenticator app with a fresh code", "/v1/auth/totp/confirm", "code", "Authenticator code", "Authenticator enabled."},
		{"disable", "Turn off your authenticator app", "/v1/auth/totp/disable", "password", "Password", "Authenticator disabled."},
	} {
		totp.AddCommand(&cobra.Command{Use: command.name, Short: command.description,
			Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
				c, err := a.selectedAccountClient(false)
				if err != nil {
					return err
				}
				secret, err := a.accountSecret(command.prompt, *stdin)
				if err != nil {
					return err
				}
				if command.field == "code" {
					secret = strings.TrimSpace(secret)
				}
				if err := c.Do(bg(), http.MethodPost, command.path, map[string]string{command.field: secret}, nil); err != nil {
					return err
				}
				return a.accountResult(command.result, map[string]bool{"enabled": command.name == "confirm"})
			}})
	}
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
	return []*cobra.Command{email, verifyEmail, password, totp, passkeys, a.remoteAccountRecovery(stdin)}
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
