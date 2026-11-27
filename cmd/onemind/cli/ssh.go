// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// sshCommands are `onemind ssh-key add|list|rm` and `onemind ssh on|off|status` (P-06, D-027/D-028).
//
// SSH is the owner's everyday shell, so a change is an owner action: the CLI only files a request
// (POST /v1/ssh/keys, DELETE /v1/ssh/keys/{id}, PUT /v1/ssh) and prints the approval id. An owner
// approves it in the dashboard or the phone app, with a passkey when adding a key or switching SSH on.
// The CLI never approves, and the gateway refuses these requests from an agent's token. A public key is
// read from a file or stdin; it holds no secret. (On the box itself, as root, `onemind-owner` does the same
// without the gateway: it is the recovery path when the web UI is down.)
func sshCommands(a *App) []*cobra.Command {
	var label, reason string
	keys := &cobra.Command{Use: "ssh-key", Short: "The SSH keys that may log in as admin on this box (owner)"}
	keys.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The authorised keys: id, type, size, fingerprint, comment",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out struct {
				Keys []map[string]any `json:"keys"`
			}
			if err := c.Do(bg(), http.MethodGet, "/v1/ssh/keys", nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			if len(out.Keys) == 0 {
				fmt.Fprintln(a.Stdout, "No SSH keys. Add one with: onemind ssh-key add ~/.ssh/id_ed25519.pub")
				return nil
			}
			rows := [][]string{}
			for _, k := range out.Keys {
				rows = append(rows, []string{sshStr(k["id"]), sshStr(k["type"]), sshStr(k["bits"]), sshStr(k["fingerprint"]), sshStr(k["comment"])})
			}
			return table(a.Stdout, "ID\tTYPE\tBITS\tFINGERPRINT\tCOMMENT", rows)
		},
	})
	add := &cobra.Command{
		Use:   "add FILE|-",
		Short: "Ask to let a public key log in as admin; prints the approval id an owner approves with a passkey",
		Long:  "Reads one public key line from FILE (a .pub file) or from stdin with -. Nothing changes until an owner approves the request.",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			line, err := a.readPublicKey(args[0])
			if err != nil {
				return err
			}
			body := map[string]any{"public_key": line, "idempotency_key": cliKey()}
			if label != "" {
				body["label"] = label
			}
			if reason != "" {
				body["reason"] = reason
			}
			return a.fileSSH(http.MethodPost, "/v1/ssh/keys", body, "SSH key add")
		},
	}
	add.Flags().StringVar(&label, "label", "", "a name for the key (default: the key's own comment)")
	add.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	rm := &cobra.Command{
		Use:   "rm ID|FINGERPRINT",
		Short: "Ask to remove a key (its id or SHA256 fingerprint from `ssh-key list`); prints the approval id",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			// A DELETE has no body, so the idempotency key goes in the header: a retry files one removal, not two.
			return a.fileSSH(http.MethodDelete, "/v1/ssh/keys/"+url.PathEscape(sshKeyID(args[0])), nil, "SSH key removal")
		},
	}
	keys.AddCommand(add, rm)

	ssh := &cobra.Command{Use: "ssh", Short: "Turn SSH on or off on this box (owner approves)"}
	ssh.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Whether SSH is on, whether it listens, and the rules it runs under",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var v struct {
				Service map[string]any   `json:"service"`
				Keys    []map[string]any `json:"keys"`
			}
			if err := c.Do(bg(), http.MethodGet, "/v1/ssh", nil, &v); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			s := v.Service
			state := map[string]string{
				"on": "on and listening", "off": "off (also after a reboot)", "waiting_for_key": "on, waiting for the first key",
				"starting": "on, starting", "unavailable": "not available: " + sshStr(s["message"]),
			}[sshStr(s["state"])]
			if state == "" {
				state = sshStr(s["state"])
			}
			return kv(a.Stdout, [][2]string{{"ssh", state}, {"keys", strconv.Itoa(len(v.Keys))},
				{"login", "public key only, as " + sshStr(s["user"]) + ", port " + sshStr(s["port"])},
				{"reach", "LAN and mesh (also the internet on a cloud box); " + sshStr(s["rate_limit"])}})
		},
	})
	for _, on := range []bool{true, false} {
		word := map[bool]string{true: "on", false: "off"}[on]
		short := map[bool]string{true: "Ask to switch SSH on (needs an owner's passkey to approve)", false: "Ask to switch SSH off, also after a reboot"}[on]
		ssh.AddCommand(&cobra.Command{
			Use:   word,
			Short: short,
			Args:  cobra.NoArgs,
			RunE: func(*cobra.Command, []string) error {
				return a.fileSSH(http.MethodPut, "/v1/ssh", map[string]any{"enabled": on, "idempotency_key": cliKey()}, "SSH "+word)
			},
		})
	}
	return []*cobra.Command{keys, ssh}
}

func cliKey() string { return "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36) }

func sshStr(v any) string {
	switch t := v.(type) {
	case nil:
		return ""
	case string:
		return t
	case float64:
		return strconv.FormatFloat(t, 'f', -1, 64)
	}
	return fmt.Sprint(v)
}

// sshKeyID turns a SHA256:... fingerprint into the URL-safe id the gateway routes by (+ is -, / is _).
func sshKeyID(s string) string {
	s = strings.TrimPrefix(strings.TrimSpace(s), "SHA256:")
	return strings.NewReplacer("+", "-", "/", "_").Replace(s)
}

// readPublicKey reads one line from a file or stdin. A private key is refused before it goes anywhere.
func (a *App) readPublicKey(src string) (string, error) {
	var r io.Reader
	if src == "-" {
		if a.G.TokenStdin {
			return "", exitWith(ExitUsage, "usage", "ssh-key add - and --token-stdin both read stdin: set ONEMIND_TOKEN instead")
		}
		r = a.Stdin
	} else {
		f, err := os.Open(src)
		if err != nil {
			return "", exitWith(ExitUsage, "usage", "cannot read "+src+": "+err.Error())
		}
		defer f.Close()
		r = io.LimitReader(f, 64<<10)
	}
	sc := bufio.NewScanner(io.LimitReader(r, 64<<10))
	sc.Buffer(make([]byte, 16<<10), 64<<10)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "-----BEGIN") {
			return "", exitWith(ExitUsage, "usage", "that is a private key; give the public one (the .pub file). Never send a private key anywhere")
		}
		if line != "" && !strings.HasPrefix(line, "#") {
			return line, nil
		}
	}
	return "", exitWith(ExitUsage, "usage", "no public key found in "+src)
}

// fileSSH sends one request and prints the approval id. The request waits for an owner.
func (a *App) fileSSH(method, path string, body map[string]any, what string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	var in any
	if body != nil {
		in = body
	}
	var act map[string]any
	if method == http.MethodDelete {
		err = c.DoIdempotent(bg(), method, path, cliKey(), in, &act)
	} else {
		err = c.Do(bg(), method, path, in, &act)
	}
	if err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, act)
	}
	id := sanitize(sshStr(act["id"]))
	if a.G.Quiet {
		fmt.Fprintln(a.Stdout, id)
		return nil
	}
	fmt.Fprintf(a.Stdout, "%s requested. Approval id: %s\nAn owner approves it in the dashboard or the phone app (a passkey is needed to let a key in or switch SSH on); follow it with: onemind actions info %s\n",
		what, id, id)
	return nil
}
