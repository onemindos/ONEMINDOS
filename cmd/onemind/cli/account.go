// SPDX-License-Identifier: Apache-2.0

package cli

import (
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
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/setup/finish", body, nil); err != nil {
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

func (a *App) familyInvite(path, op, target string, body map[string]any, stdin, atBox bool) (any, error) {
	c, err := a.selectedAccountClient(false)
	if err != nil {
		return nil, err
	}
	var out any
	var payload any
	if body != nil {
		payload = body
	}
	err = c.Do(bg(), http.MethodPost, path, payload, &out)
	var gatewayErr *onemind.Error
	if errors.As(err, &gatewayErr) && gatewayErr.Reason == "step_up_required" && (a.Interactive() || stdin) {
		grant, proofErr := a.accountTOTPProof(c, op, target, body, stdin, atBox)
		if proofErr != nil {
			return nil, proofErr
		}
		err = c.DoWithStepUp(bg(), http.MethodPost, path, grant, payload, &out)
	}
	return out, explainGateway(err)
}

func (a *App) accountTOTPProof(c *onemind.Client, op, target string, body map[string]any, stdin, atBox bool) (string, error) {
	var options struct {
		Challenge   string `json:"challenge"`
		BoxRequired bool   `json:"box_code_required"`
	}
	opts := map[string]any{"op": op, "target": target, "method": "password+totp", "at_box": atBox}
	if body != nil {
		opts["body"] = body
	}
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/step-up/options", opts, &options); err != nil {
		return "", explainGateway(err)
	}
	password, err := a.accountSecret("Password", stdin)
	if err != nil {
		return "", err
	}
	code, err := a.accountSecret("Authenticator code", stdin)
	if err != nil {
		return "", err
	}
	proof := map[string]any{"password_totp": map[string]string{"challenge": options.Challenge, "password": password, "totp": strings.TrimSpace(code)}}
	if options.BoxRequired {
		boxCode, err := a.accountSecret("Code on the box's screen", stdin)
		if err != nil {
			return "", err
		}
		proof["box_code"] = strings.TrimSpace(boxCode)
	}
	var grant struct {
		Value string `json:"step_up"`
	}
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/step-up", proof, &grant); err != nil {
		return "", err
	}
	if grant.Value == "" {
		return "", fmt.Errorf("the box returned an empty step-up proof")
	}
	return grant.Value, nil
}
