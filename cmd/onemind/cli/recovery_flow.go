// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

var recoveryIDRe = regexp.MustCompile(`^rr_[0-9A-Z]{26}$`)

type recoveryCredential struct {
	Hub   string `json:"hub"`
	Path  string `json:"path"`
	Token string `json:"token"`
}

// recoveryFlowCommands is the locked-out side of `onemind recovery` (gateway permissions design 25e,
// D-028): start a recovery, type the code a contact reads to you, follow it, cancel it, finish it.
// `start` keeps the request's own token (omr_) in a 0600 file next to the CLI config, so the later
// commands can use it; it reaches only that request. An owner who is signed in sees every running
// recovery with `onemind recovery status` and stops one with `onemind recovery cancel <id>`.
func recoveryFlowCommands(a *App) []*cobra.Command {
	tokenFile := func(id string) (string, error) {
		if !recoveryIDRe.MatchString(id) {
			return "", exitWith(ExitUsage, "usage", "a recovery id looks like rr_ and 26 letters or digits")
		}
		p, err := configPath(a.G.ConfigFile)
		if err != nil {
			return "", err
		}
		return filepath.Join(filepath.Dir(p), "recovery", id+".token"), nil
	}
	gateway := func(hub string) string { return strings.TrimRight(strings.TrimSpace(hub), "/") }
	noRedirect := onemind.WithHTTPClient(&http.Client{
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	})
	starter := func(id string) (*onemind.Client, recoveryCredential, error) {
		var saved recoveryCredential
		path, err := tokenFile(id)
		if err != nil {
			return nil, saved, err
		}
		raw, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			return nil, saved, exitWith(ExitNotFound, "not_found", "this computer did not start recovery "+id+" (no saved request token)")
		}
		if err != nil {
			return nil, saved, err
		}
		if err := json.Unmarshal(raw, &saved); err != nil || saved.Hub == "" || !strings.HasPrefix(saved.Token, "omr_") {
			return nil, saved, exitWith(ExitUsage, "usage", "this saved recovery token has no verified gateway; use your owner session to cancel the request")
		}
		t, err := a.resolveHubOnly()
		if err != nil {
			return nil, saved, err
		}
		if gateway(t.hub) != saved.Hub {
			return nil, saved, exitWith(ExitUsage, "usage", "this recovery belongs to a different gateway; select the gateway that started it")
		}
		t.token = saved.Token
		c, err := a.clientFor(t, noRedirect)
		return c, saved, err
	}
	show := func(r map[string]any) error {
		if a.G.JSON {
			return printJSON(a.Stdout, r)
		}
		pairs := [][2]string{{"id", str(r["id"])}, {"path", str(r["path"])}, {"state", str(r["state"])}}
		if n := str(r["matching_number"]); n != "" {
			pairs = append(pairs, [2]string{"matching number", n + " (your contact picks this number in their app)"})
		}
		if c := str(r["request_code"]); c != "" {
			pairs = append(pairs, [2]string{"request code", c + " (read it to your contact if their app cannot reach the box)"})
		}
		if nb := str(r["not_before"]); nb != "" {
			pairs = append(pairs, [2]string{"can finish after", nb})
		}
		if e := str(r["end_reason"]); e != "" {
			pairs = append(pairs, [2]string{"ended", e})
		}
		return kv(a.Stdout, pairs)
	}

	var path, user, totp string
	var passwordStdin bool
	start := &cobra.Command{Use: "start", Short: "Start a recovery: --path contact (a recovery contact confirms) or remote (password, code and a wait)",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if path != "contact" && path != "remote" {
				return usageErr(cmd, "--path is contact or remote")
			}
			if user == "" {
				return usageErr(cmd, "--user <your username>")
			}
			body := map[string]any{"path": path, "username": user}
			if path == "remote" {
				if !passwordStdin || totp == "" {
					return usageErr(cmd, "a remote recovery needs your password (--password-stdin) and your authenticator code (--totp); a password alone never starts one")
				}
				pw, err := readSecretLine(a.Stdin)
				if err != nil {
					return err
				}
				body["password"], body["totp"] = pw, totp
			}
			t, err := a.resolveHubOnly()
			if err != nil {
				return err
			}
			c, err := a.clientFor(t, noRedirect)
			if err != nil {
				return err
			}
			var r map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/recovery", body, &r); err != nil {
				return err
			}
			one, _ := r["one_time"].(map[string]any)
			file, err := tokenFile(str(r["id"]))
			if err != nil {
				return err
			}
			if err := os.MkdirAll(filepath.Dir(file), 0o700); err != nil {
				return err
			}
			saved, err := json.Marshal(recoveryCredential{Hub: gateway(t.hub), Path: path, Token: str(one["request_token"])})
			if err != nil {
				return err
			}
			if err := writeFile0600(file, saved); err != nil {
				return err
			}
			delete(r, "one_time")
			if !a.G.JSON {
				fmt.Fprintln(a.Stdout, "Recovery started. Every owner and recovery contact is told.")
			}
			return show(r)
		}}
	start.Flags().StringVar(&path, "path", "contact", "contact or remote")
	start.Flags().StringVar(&user, "user", "", "your username")
	start.Flags().BoolVar(&passwordStdin, "password-stdin", false, "remote: read your password from stdin")
	start.Flags().StringVar(&totp, "totp", "", "remote: your authenticator code")

	status := &cobra.Command{Use: "status [<recovery-id>]", Short: "Follow your recovery, or (signed-in owner) list every running one",
		Args: cobra.MaximumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if len(args) == 1 {
				c, _, err := starter(args[0])
				if err != nil {
					return err
				}
				var r map[string]any
				if err := c.Do(bg(), http.MethodGet, "/v1/auth/recovery/requests/"+url.PathEscape(args[0]), nil, &r); err != nil {
					return err
				}
				return show(r)
			}
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var rows []map[string]any
			if err := c.Do(bg(), http.MethodGet, "/v1/auth/recovery", nil, &rows); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, rows)
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No recovery is running.")
				return nil
			}
			out := make([][]string, 0, len(rows))
			for _, r := range rows {
				out = append(out, []string{str(r["id"]), str(r["path"]), str(r["state"]), dash(str(r["not_before"])), str(r["source"])})
			}
			fmt.Fprintln(a.Stdout, "If one of these is not you or someone you know, stop it: onemind recovery cancel <id>")
			return table(a.Stdout, "ID\tPATH\tSTATE\tCAN FINISH AFTER\tFROM", out)
		}}

	code := &cobra.Command{Use: "code <recovery-id> <8 digits>", Short: "Type the code your recovery contact read to you", Args: cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := starter(args[0])
			if err != nil {
				return err
			}
			var r map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/recovery/requests/"+url.PathEscape(args[0])+"/code",
				map[string]any{"code": args[1]}, &r); err != nil {
				return err
			}
			return show(r)
		}}

	cancel := &cobra.Command{Use: "cancel <recovery-id>", Short: "Stop a recovery (the computer that started it, or any owner)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := starter(args[0])
			var ee *exitError
			if errors.As(err, &ee) && ee.code == ExitNotFound {
				c, _, err = a.client() // not ours: cancel as the signed-in owner
			}
			if err != nil {
				return err
			}
			var r map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/recovery/requests/"+url.PathEscape(args[0])+"/cancel", nil, &r); err != nil {
				return err
			}
			return show(r)
		}}

	var newPassword, currentPassword bool
	complete := &cobra.Command{Use: "complete <recovery-id>", Short: "After the contact wait: prove your current password and set a new one",
		Long: "Complete contact-assisted recovery with a password change. Passkey enrollment and remote recovery completion require a WebAuthn client using the gateway API. The dashboard sign-in page does not provide that flow yet.",
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, saved, err := starter(args[0])
			if err != nil {
				return err
			}
			if saved.Path == "remote" {
				return usageErr(cmd, "remote recovery completion requires passkey enrollment through a WebAuthn client using the gateway API")
			}
			if !currentPassword || !newPassword {
				return usageErr(cmd, "pass --current-password-stdin and --new-password-stdin; give the current password on the first line and the new password on the second")
			}
			current, err := a.readLine()
			if err != nil || strings.TrimSpace(current) == "" {
				return usageErr(cmd, "give the current password on the first line")
			}
			current = strings.TrimSuffix(strings.TrimSuffix(current, "\n"), "\r")
			pw, err := readSecretLine(a.in)
			if err != nil {
				return err
			}
			var r map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/auth/recovery/requests/"+url.PathEscape(args[0])+"/complete",
				map[string]any{"current_password": current, "new_password": pw, "client": "cli"}, &r); err != nil {
				return err
			}
			if file, err := tokenFile(args[0]); err == nil {
				_ = os.Remove(file)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"completed": true, "session": r["session"]})
			}
			fmt.Fprintln(a.Stdout, "Recovered. Your new password works now; sign in with `onemind login` and add a passkey.")
			return nil
		}}
	complete.Flags().BoolVar(&currentPassword, "current-password-stdin", false, "read the current password from the first stdin line")
	complete.Flags().BoolVar(&newPassword, "new-password-stdin", false, "read the new password from the second stdin line")
	return []*cobra.Command{start, status, code, cancel, complete}
}

// resolveHubOnly is resolve() for calls that must not send a saved token (a locked-out person's).
func (a *App) resolveHubOnly() (*target, error) {
	t, err := a.resolve()
	if err != nil {
		return nil, err
	}
	t.token = ""
	return t, nil
}
