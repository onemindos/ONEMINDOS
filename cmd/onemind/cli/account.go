// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

type accountChallenge struct {
	ID string `json:"challenge_id"`
}

type accountRecoveryKit struct {
	Code    string `json:"recovery_code"`
	DiskKey string `json:"disk_recovery_key,omitempty"`
}

func (a *App) accountResult(message string, body any) error {
	if a.G.JSON {
		return printJSON(a.Stdout, body)
	}
	_, err := fmt.Fprintln(a.Stdout, message)
	return err
}

func (a *App) selectedAccountClient(anonymous bool) (*onemind.Client, error) {
	if anonymous && a.G.Hub != "" {
		return a.accountClient(&target{hub: a.G.Hub})
	}
	t, err := a.resolveTarget(!anonymous)
	if err != nil {
		return nil, err
	}
	return a.accountClient(t)
}

// writeAccountKit saves a new, private file and confirms it has been flushed before
// advancing setup. The caller opens the destination before any password reset.
func writeAccountKit(file *os.File, kit accountRecoveryKit) error {
	if kit.Code == "" {
		return fmt.Errorf("the box returned an empty recovery kit")
	}
	enc := json.NewEncoder(file)
	enc.SetIndent("", "  ")
	if err := enc.Encode(kit); err != nil {
		return err
	}
	if err := file.Sync(); err != nil {
		return err
	}
	if runtime.GOOS == "windows" {
		return nil // Opening a directory for fsync is not supported there.
	}
	dir, err := os.Open(filepath.Dir(file.Name()))
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}

func newAccountKitFile(path string) (*os.File, error) {
	if path == "" {
		return nil, exitWith(ExitUsage, "usage", "pass --kit PATH for a new private recovery kit file")
	}
	return os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
}

func (a *App) finishAccountSetup(c *onemind.Client, path string, yes bool) error {
	file, err := newAccountKitFile(path)
	var kit accountRecoveryKit
	if yes && errors.Is(err, os.ErrExist) {
		kit, err = readSavedAccountKit(path)
	} else if err == nil {
		err = saveSetupKit(c, file, &kit)
		if err != nil {
			os.Remove(path)
		}
	}
	if err != nil {
		return err
	}
	fmt.Fprintf(a.Stderr, "Recovery kit at %q. Keep a copy somewhere separate from the box. Without it you may lose access to your data.\n", path)
	if !yes {
		yes, err = a.confirm("Did you save the recovery kit somewhere safe?", "--yes")
		if err != nil {
			return err
		}
		if !yes {
			return exitWith(ExitConflict, "conflict", "setup is still pending. Run account setup-finish with the saved kit path and --yes when you are ready")
		}
	}
	body := map[string]any{"saved": true, "method": "download", "recovery_code": kit.Code}
	err = c.Do(bg(), http.MethodPost, "/v1/auth/setup/finish", body, nil)
	var gatewayErr *onemind.Error
	if kit.DiskKey != "" && errors.As(err, &gatewayErr) && gatewayErr.Reason == "disk_recovery_key_missing" {
		body["disk_recovery_key"] = kit.DiskKey
		err = c.Do(bg(), http.MethodPost, "/v1/auth/setup/finish", body, nil)
	}
	if err != nil {
		return err
	}
	return a.accountResult("Setup finished.", map[string]any{"setup_finished": true, "kit": path})
}

func saveSetupKit(c *onemind.Client, file *os.File, kit *accountRecoveryKit) error {
	defer file.Close()
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/setup/kit", nil, kit); err != nil {
		return err
	}
	return writeAccountKit(file, *kit)
}

func readSavedAccountKit(path string) (accountRecoveryKit, error) {
	var kit accountRecoveryKit
	info, err := os.Lstat(path)
	if err != nil {
		return kit, err
	}
	if !info.Mode().IsRegular() || (runtime.GOOS != "windows" && info.Mode().Perm()&0o077 != 0) {
		return kit, fmt.Errorf("use a private regular file for the recovery kit")
	}
	file, err := os.Open(path)
	if err != nil {
		return kit, err
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil {
		return kit, err
	}
	if !os.SameFile(info, opened) {
		return kit, fmt.Errorf("the recovery kit file changed while it was being opened")
	}
	if err := json.NewDecoder(io.LimitReader(file, 32*1024)).Decode(&kit); err != nil || kit.Code == "" {
		return kit, fmt.Errorf("the existing file does not contain a recovery kit")
	}
	return kit, nil
}

func accountCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "account", Short: "Set up, secure and recover a person’s sign-in"}
	var secretsStdin bool
	root.PersistentFlags().BoolVar(&secretsStdin, "secrets-stdin", false, "read requested secrets as separate lines from stdin")

	var displayName, email, setupContext string
	setup := &cobra.Command{Use: "setup USERNAME", Short: "Use the box’s screen code to start first setup",
		Args: cobra.ExactArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			c, err := a.selectedAccountClient(true)
			if err != nil {
				return err
			}
			var ch accountChallenge
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/setup/options", nil, &ch); err != nil {
				return err
			}
			code, err := a.accountSecret("Setup code on the box's screen", secretsStdin)
			if err != nil {
				return err
			}
			password, err := a.accountSecret("New password (at least 12 characters)", secretsStdin)
			if err != nil {
				return err
			}
			body := map[string]string{"challenge_id": ch.ID, "box_code": strings.TrimSpace(code),
				"username": args[0], "display_name": displayName, "password": password, "client": "cli"}
			if email != "" {
				body["email"] = email
			}
			var session accountSession
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/setup", body, &session); err != nil {
				return err
			}
			name, err := a.saveAccountSession(c.BaseURL(), setupContext, session)
			if err != nil {
				return err
			}
			return a.accountResult("Setup started. Run onemind account setup-finish --kit PATH to save the recovery kit and finish.",
				map[string]any{"context": name, "setup_finished": false})
		}}
	setup.Flags().StringVar(&displayName, "display-name", "", "name shown to other people")
	setup.Flags().StringVar(&email, "email", "", "optional address for notices")
	setup.Flags().StringVar(&setupContext, "name", "", "name for the saved box context")
	root.AddCommand(setup)

	var kitFile string
	var kitYes bool
	finish := &cobra.Command{Use: "setup-finish", Short: "Save the recovery kit privately and confirm first setup",
		Args: cobra.NoArgs, RunE: func(*cobra.Command, []string) error {
			c, err := a.selectedAccountClient(false)
			if err != nil {
				return err
			}
			return a.finishAccountSetup(c, kitFile, kitYes)
		}}
	finish.Flags().StringVar(&kitFile, "kit", "", "file to save the kit, or an already saved kit with --yes")
	finish.Flags().BoolVar(&kitYes, "yes", false, "confirm the saved recovery kit is in a safe place")
	root.AddCommand(finish)

	var enrolContext string
	enrol := &cobra.Command{Use: "enrol [USERNAME]", Short: "Redeem a family invitation and choose your password",
		Args: cobra.MaximumNArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			c, err := a.selectedAccountClient(true)
			if err != nil {
				return err
			}
			code, err := a.accountSecret("Invitation link or code", secretsStdin)
			if err != nil {
				return err
			}
			link := strings.TrimSpace(code)
			if u, err := url.Parse(link); err == nil && u.Host != "" {
				hub, err := url.Parse(c.BaseURL())
				if err != nil || u.User != nil || !strings.EqualFold(u.Host, hub.Host) || u.Scheme != hub.Scheme {
					return exitWith(ExitUsage, "usage", "the invitation is for a different box")
				}
				var ok bool
				link, ok = strings.CutPrefix(u.Fragment, "enrol=")
				if !ok || link == "" {
					return exitWith(ExitUsage, "usage", "the invitation link does not contain a sign-up code")
				}
			}
			password, err := a.accountSecret("New password (at least 12 characters)", secretsStdin)
			if err != nil {
				return err
			}
			body := map[string]string{"code": link, "password": password, "client": "cli"}
			if len(args) > 0 {
				body["username"] = args[0]
			}
			var session accountSession
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/enrol", body, &session); err != nil {
				return err
			}
			name, err := a.saveAccountSession(c.BaseURL(), enrolContext, session)
			if err != nil {
				return err
			}
			return a.accountResult("Invitation accepted. Saved context "+name+".", map[string]string{"context": name})
		}}
	enrol.Flags().StringVar(&enrolContext, "name", "", "name for the saved box context")
	root.AddCommand(enrol)

	var replacementFile string
	recover := &cobra.Command{Use: "recover USERNAME", Short: "Reset a password using the box’s screen and recovery kit",
		Args: cobra.ExactArgs(1), RunE: func(_ *cobra.Command, args []string) error {
			c, err := a.selectedAccountClient(true)
			if err != nil {
				return err
			}
			file, err := newAccountKitFile(replacementFile)
			if err != nil {
				return err
			}
			saved := false
			defer func() {
				file.Close()
				if !saved {
					os.Remove(replacementFile)
				}
			}()
			var ch accountChallenge
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/recovery/options", map[string]string{"username": args[0]}, &ch); err != nil {
				return err
			}
			body := map[string]string{"challenge_id": ch.ID}
			for _, field := range [][2]string{{"box_code", "Code on the box's screen"}, {"recovery_code", "Code from the recovery kit"}, {"new_password", "New password (at least 12 characters)"}} {
				body[field[0]], err = a.accountSecret(field[1], secretsStdin)
				if err != nil {
					return err
				}
				if field[0] != "new_password" {
					body[field[0]] = strings.TrimSpace(body[field[0]])
				}
			}
			var kit accountRecoveryKit
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/recovery/reset", body, &kit); err != nil {
				return err
			}
			if err := writeAccountKit(file, kit); err != nil {
				// The old code was consumed. Display the replacement only on a real terminal.
				if f, ok := a.Stderr.(*os.File); ok && term.IsTerminal(int(f.Fd())) {
					fmt.Fprintf(f, "Password reset succeeded. Save this new recovery code now: %s\n", kit.Code)
				}
				return fmt.Errorf("password reset succeeded, but writing the replacement recovery code failed: %w", err)
			}
			saved = true
			return a.accountResult("Password reset. Keep the new recovery code and your original disk recovery key somewhere safe.",
				map[string]string{"kit": replacementFile})
		}}
	recover.Flags().StringVar(&replacementFile, "kit", "", "new file for the replacement recovery code")
	root.AddCommand(recover)
	root.AddCommand(a.accountSecurityCommands(&secretsStdin)...)
	return []*cobra.Command{root}
}

// Sign-in methods, password and authenticator code (UI parity M1, #1232): `account show` reads GET /v1/auth/methods;
// `password` and `totp setup|confirm|disable` (account_security.go) call POST /v1/auth/password and /v1/auth/totp/*.
// These change your own credentials, so the gateway accepts them only from a signed-in session, never from an API
// token; it checks the current password and audits each change. The CLI never takes a password as a flag: it asks
// without echo, or reads --password-stdin / --secrets-stdin. D-034: passkeys are recommended and optional.

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

const totpFallbackNote = "Passkeys are recommended; a password alone, or with an authenticator code, also works (D-034).\n" +
	"The box asks for the code after your password. From outside your home, sign-in needs the code or a passkey."

// explainAccount adds what to do when the gateway refuses a credential change from a token. The gateway sends
// reason=session_required; an older one sent a bare 403, which on these commands means the same thing.
func explainAccount(err error) error {
	var e *onemind.Error
	if errors.As(err, &e) && e.Status == 403 && (e.Reason == "session_required" || e.Reason == "") {
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
		return nil, exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --password-stdin or --secrets-stdin (one line per answer)")
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
