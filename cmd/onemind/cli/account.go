// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind account`: your own sign-in, the CLI side of Settings > Account and security (UI parity M1, #1232).
// `show` reads GET /v1/auth/methods; `password` and `totp setup|confirm|disable` call POST /v1/auth/password and
// /v1/auth/totp/*. These change your own credentials, so the gateway accepts them only from a signed-in session
// (a bearer session from `POST /v1/auth/login` with client "cli"), never from an API token; it checks the current
// password and audits each change. The CLI adds no check of its own and never takes a password as a flag: it asks
// without echo, or reads --password-stdin. Passkeys cannot be added here: WebAuthn needs a browser or the phone.
// D-030: passkeys come first, new people are passkeys-only and an authenticator code is a fallback for people who
// already sign in with a password; `totp setup` says so before it prints a secret.

import (
	"bufio"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

type signInMethods struct {
	Password       bool `json:"password"`
	TOTP           bool `json:"totp"`
	Passkeys       int  `json:"passkeys"`
	PasskeysActive bool `json:"passkeys_active"`
}

type totpSetup struct {
	OneTime struct {
		Secret     string `json:"secret"`
		OtpauthURI string `json:"otpauth_uri"`
	} `json:"one_time"`
}

const totpFallbackNote = "Passkeys are the main way to sign in to OneMind; new people should use a passkey only.\n" +
	"An authenticator code is a fallback asked after your password, for people who already sign in with one."

func accountCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "account", Short: "Your own sign-in: password and authenticator code (GET /v1/auth/methods)"}
	g.AddCommand(accountShowCmd(a), accountPasswordCmd(a), accountTotpCmd(a))
	return []*cobra.Command{g}
}

// explainAccount adds what to do when the gateway refuses a credential change from a token.
func explainAccount(err error) error {
	var e *onemind.Error
	if errors.As(err, &e) && e.Reason == "session_required" {
		return fmt.Errorf("%w\nChanging your sign-in needs a signed-in session, not an API token. Do it in the dashboard (Settings > Account and security)", err)
	}
	return explainGateway(err)
}

func accountShowCmd(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "show",
		Short: "How you sign in: password, authenticator code, passkeys",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var m signInMethods
			raw, err := getBoth(a, "/v1/auth/methods", &m)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			onOff := func(b bool) string {
				if b {
					return "on"
				}
				return "off"
			}
			pw := "not set (you sign in with a passkey)"
			if m.Password {
				pw = "set"
			}
			fmt.Fprintf(a.Stdout, "Passkeys:           %d\n", m.Passkeys)
			fmt.Fprintf(a.Stdout, "Password:           %s\n", pw)
			fmt.Fprintf(a.Stdout, "Authenticator code: %s (a fallback for password sign-in)\n", onOff(m.TOTP))
			if m.Passkeys == 0 {
				fmt.Fprintln(a.Stdout, "Add a passkey in the dashboard or the phone app: it is the safest way to sign in.")
			}
			return nil
		},
	}
}

// secrets reads n secrets: one line each from stdin with --password-stdin, else asked without echo.
func (a *App) secrets(fromStdin bool, prompts ...string) ([]string, error) {
	out := make([]string, 0, len(prompts))
	if fromStdin {
		r := bufio.NewReader(a.Stdin)
		for _, p := range prompts {
			line, _ := r.ReadString('\n') // io.EOF with a last line and no newline is fine
			line = strings.TrimRight(line, "\r\n")
			if line == "" {
				return nil, exitWith(ExitUsage, "usage", fmt.Sprintf("--password-stdin: no line for %q", strings.ToLower(p)))
			}
			out = append(out, line)
		}
		return out, nil
	}
	f, ok := a.Stdin.(*os.File)
	if !ok || !a.Interactive() {
		return nil, exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --password-stdin (one line per answer)")
	}
	for _, p := range prompts {
		fmt.Fprintf(a.Stderr, "%s: ", p)
		raw, err := term.ReadPassword(int(f.Fd()))
		fmt.Fprintln(a.Stderr)
		if err != nil {
			return nil, err
		}
		out = append(out, string(raw))
	}
	return out, nil
}

func accountPasswordCmd(a *App) *cobra.Command {
	var fromStdin bool
	c := &cobra.Command{
		Use:   "password",
		Short: "Change your password (signs you out on every other device)",
		Long: "Asks for your current password and the new one twice, without echo. With --password-stdin it reads\n" +
			"two lines instead: the current password, then the new one. Needs a signed-in session, not an API token.",
		Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			prompts := []string{"Current password", "New password (at least 10 characters)", "New password again"}
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
			c, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]string{"current_password": got[0], "new_password": got[1]}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/password", body, nil); err != nil {
				return explainAccount(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.account/v1", "password_changed": true, "other_sessions_revoked": true})
			}
			fmt.Fprintln(a.Stdout, "Password changed. Your other devices were signed out.")
			return nil
		},
	}
	c.Flags().BoolVar(&fromStdin, "password-stdin", false, "read the current and the new password from stdin, one per line")
	return c
}

func accountTotpCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "totp", Short: "Authenticator code (TOTP): a fallback for password sign-in; passkeys come first"}
	g.AddCommand(&cobra.Command{
		Use:   "setup",
		Short: "Start setting up an authenticator code: prints the key once",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var s totpSetup
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/setup", nil, &s); err != nil {
				return explainAccount(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, s)
			}
			fmt.Fprintln(a.Stderr, totpFallbackNote)
			fmt.Fprintf(a.Stdout, "Key (shown once): %s\nLink for a QR code: %s\n", s.OneTime.Secret, s.OneTime.OtpauthURI)
			fmt.Fprintln(a.Stderr, "Add the key to your authenticator app, then run: onemind account totp confirm <6-digit code>")
			return nil
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "confirm CODE",
		Short: "Turn the authenticator code on with the 6 digits your app shows now",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			code := strings.TrimSpace(args[0])
			if len(code) != 6 || strings.Trim(code, "0123456789") != "" {
				return exitWith(ExitUsage, "usage", "the code is the 6 digits your authenticator app shows")
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/confirm", map[string]string{"code": code}, nil); err != nil {
				return explainAccount(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.account/v1", "totp": true})
			}
			fmt.Fprintln(a.Stdout, "Authenticator code on. The box asks for it after your password.")
			return nil
		},
	})
	var fromStdin bool
	disable := &cobra.Command{
		Use:   "disable",
		Short: "Turn the authenticator code off (asks for your password)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			got, err := a.secrets(fromStdin, "Your password")
			if err != nil {
				return err
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/totp/disable", map[string]string{"password": got[0]}, nil); err != nil {
				return explainAccount(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.account/v1", "totp": false})
			}
			fmt.Fprintln(a.Stdout, "Authenticator code off.")
			return nil
		},
	}
	disable.Flags().BoolVar(&fromStdin, "password-stdin", false, "read your password from stdin")
	g.AddCommand(disable)
	return g
}
