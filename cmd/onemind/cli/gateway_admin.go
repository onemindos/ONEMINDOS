// SPDX-License-Identifier: Apache-2.0

package cli

// Gateway CLI, part 2 (NATIVE-FEATURES-AUDIT 2c, lane W4): `onemind sessions`, `onemind shares`,
// `onemind tls` and `onemind network show`. Each one calls a route the gateway already has, so the
// CLI, the dashboard and the phone see the same box. Reads print a table or --json. Writes only
// request: turning a share on files a files.share.create action an owner approves (an AI agent may
// not ask for it); stopping a share and signing a session out are the owner-only calls the gateway
// already audits, and the gateway refuses them for anyone else.

import (
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
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

type gwSession struct {
	ID         string  `json:"id"`
	Principal  string  `json:"principal_id"`
	Client     string  `json:"client"`
	Transport  string  `json:"transport"`
	AuthMethod string  `json:"auth_method"`
	CreatedAt  string  `json:"created_at"`
	LastSeenAt *string `json:"last_seen_at"`
	ExpiresAt  string  `json:"expires_at"`
	Current    bool    `json:"current"`
}

type smbShare struct {
	ID         string `json:"id"`
	Kind       string `json:"kind"`
	PersonID   string `json:"person_id"`
	Name       string `json:"name"`
	QuotaBytes *int64 `json:"quota_bytes"`
	State      string `json:"state"`
	CreatedAt  string `json:"created_at"`
}

type smbView struct {
	Service struct {
		Available bool    `json:"available"`
		Reason    *string `json:"reason"`
		Message   *string `json:"message"`
	} `json:"service"`
	People []struct {
		PersonID string `json:"person_id"`
		Role     string `json:"role"`
		Home     bool   `json:"home"`
	} `json:"people"`
	Shares []smbShare `json:"shares"`
}

type netView struct {
	Available  bool    `json:"available"`
	Reason     *string `json:"reason"`
	Message    *string `json:"message"`
	Interfaces []struct {
		Name      string   `json:"name"`
		Kind      string   `json:"kind"`
		State     string   `json:"state"`
		MAC       *string  `json:"mac"`
		Addresses []string `json:"addresses"`
		Wifi      *struct {
			SignalDBM *int `json:"signal_dbm"`
		} `json:"wifi"`
	} `json:"interfaces"`
	Gateways []struct {
		Interface string `json:"interface"`
		Via       string `json:"via"`
		Family    string `json:"family"`
	} `json:"gateways"`
	DNS   []string `json:"dns"`
	Ports []struct {
		Proto string `json:"proto"`
		Addr  string `json:"addr"`
		Port  int    `json:"port"`
		Scope string `json:"scope"`
	} `json:"ports"`
}

// getBoth reads one route once and returns the untouched JSON (for --json) and the typed shape.
func getBoth(a *App, path string, typed any) (json.RawMessage, error) {
	c, _, err := a.client()
	if err != nil {
		return nil, err
	}
	var raw json.RawMessage
	if err := c.Do(bg(), http.MethodGet, path, nil, &raw); err != nil {
		return nil, err
	}
	if typed != nil {
		if err := json.Unmarshal(raw, typed); err != nil {
			return nil, exitWith(ExitError, "unexpected_response", "the box answered with an unexpected shape")
		}
	}
	return raw, nil
}

func printRawJSON(a *App, raw json.RawMessage) error {
	var v any
	_ = json.Unmarshal(raw, &v)
	return printJSON(a.Stdout, v)
}

func gatewayAdminCommands(a *App) []*cobra.Command {
	return []*cobra.Command{sessionsCmd(a), sharesCmd(a), tlsCmd(a)} // `network show` lives in the network group (network.go)
}

func sessionsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "sessions", Short: "Who is signed in: list sessions, sign one out (GET/DELETE /v1/auth/sessions)"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your sessions (an owner sees everyone's)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			list := []gwSession{}
			if err := c.Do(bg(), http.MethodGet, "/v1/auth/sessions", nil, &list); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, list)
			}
			now := time.Now()
			var rows [][]string
			for _, s := range list {
				here := ""
				if s.Current {
					here = "this one"
				}
				seen := "never"
				if s.LastSeenAt != nil {
					seen = age(*s.LastSeenAt, now)
				}
				rows = append(rows, []string{s.ID, sanitize(s.Principal), sanitize(s.Client), s.AuthMethod, seen, in(s.ExpiresAt, now), here})
			}
			return table(a.Stdout, "ID\tPERSON\tCLIENT\tSIGNED IN WITH\tLAST SEEN\tEXPIRES\t", rows)
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "revoke SESSION_ID",
		Short: "Sign a session out now (yours, or anyone's as an owner)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodDelete, "/v1/auth/sessions/"+url.PathEscape(args[0]), nil, nil); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.sessions/v1", "revoked": args[0]})
			}
			fmt.Fprintf(a.Stdout, "session %s signed out\n", sanitize(args[0]))
			return nil
		},
	})
	return g
}

func sharesCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "shares", Short: "Network shares (SMB) and file links: list, request, stop, revoke"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Whether the box can share over SMB, and the shares that exist (GET /v1/shares/smb)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var v smbView
			raw, err := getBoth(a, "/v1/shares/smb", &v)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			if !v.Service.Available {
				fmt.Fprintf(a.Stderr, "onemind: file sharing is not available: %s\n", sanitize(deref(v.Service.Message)))
			}
			var rows [][]string
			for _, s := range v.Shares {
				quota := "-"
				if s.QuotaBytes != nil {
					quota = human(uint64(*s.QuotaBytes))
				}
				rows = append(rows, []string{s.ID, sanitize(s.Name), s.Kind, sanitize(s.PersonID), quota, s.State})
			}
			return table(a.Stdout, "ID\tNAME\tKIND\tPERSON\tLIMIT\tSTATE", rows)
		},
	})
	var kind string
	var quotaGiB int64
	var reason string
	add := &cobra.Command{
		Use:   "add PERSON_ID",
		Short: "Ask to share a person's home (or a Time Machine folder); an owner approves it with a passkey",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if kind != "home" && kind != "timemachine" {
				return exitWith(ExitUsage, "usage", "--kind must be home or timemachine")
			}
			if kind == "timemachine" && quotaGiB < 1 {
				return exitWith(ExitUsage, "usage", "a Time Machine share needs --quota-gib (at least 1)")
			}
			if kind == "home" && quotaGiB != 0 {
				return exitWith(ExitUsage, "usage", "--quota-gib is only for --kind timemachine")
			}
			params := map[string]any{"person_id": args[0], "kind": kind}
			if kind == "timemachine" {
				params["quota_bytes"] = quotaGiB << 30
			}
			return a.fileAction("files.share.create", params, reason, "Sharing "+kind+" for "+sanitize(args[0]))
		},
	}
	add.Flags().StringVar(&kind, "kind", "home", "home or timemachine")
	add.Flags().Int64Var(&quotaGiB, "quota-gib", 0, "Time Machine size limit in GiB (required for timemachine)")
	add.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	g.AddCommand(add)
	g.AddCommand(&cobra.Command{
		Use:   "stop SHARE_ID",
		Short: "Stop an SMB share now (owner; taking exposure away needs no approval and is audited)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out any
			if err := c.Do(bg(), http.MethodPost, "/v1/shares/smb/"+url.PathEscape(args[0])+"/stop", map[string]any{}, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.shares/v1", "stopped": args[0], "result": out})
			}
			fmt.Fprintf(a.Stdout, "share %s stopped\n", sanitize(args[0]))
			return nil
		},
	})

	links := &cobra.Command{Use: "links", Short: "Links to files shared outside the household (GET/DELETE /v1/files/shares)"}
	links.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your links, without their secrets (an owner sees everyone's)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw any
			if err := c.Do(bg(), http.MethodGet, "/v1/files/shares", nil, &raw); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, raw)
			}
			items, _ := raw.([]any)
			if m, ok := raw.(map[string]any); ok {
				items, _ = m["items"].([]any)
			}
			var rows [][]string
			for _, it := range items {
				m, _ := it.(map[string]any)
				rows = append(rows, []string{fmt.Sprint(m["id"]), sanitize(fmt.Sprint(orEmpty(m["name"]))), fmt.Sprint(orEmpty(m["expires_at"]))})
			}
			return table(a.Stdout, "ID\tNAME\tEXPIRES", rows)
		},
	})
	links.AddCommand(&cobra.Command{
		Use:   "revoke LINK_ID",
		Short: "Request to end a link; an owner approves",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			out, err := a.gwDo(http.MethodDelete, "/v1/files/shares/"+url.PathEscape(args[0]), nil)
			if err != nil {
				return err
			}
			return a.printFileRequest("end share link "+sanitize(args[0]), out)
		},
	})
	g.AddCommand(links)
	return g
}

// fileAction files one action (POST /v1/actions) and prints its id. The CLI never approves it.
func (a *App) fileAction(typ string, params map[string]any, reason, what string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	if _, err := c.Instance.Get(bg()); err != nil { // learn the hub clock, so expires_at is on its time
		return err
	}
	body := map[string]any{
		"type": typ, "params": params,
		"idempotency_key": "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36),
		"expires_at":      c.HubNow().Add(24 * time.Hour).UTC().Format(time.RFC3339),
	}
	if reason != "" {
		body["reason"] = reason
	}
	var act map[string]any
	if err := c.Do(bg(), http.MethodPost, "/v1/actions", body, &act); err != nil {
		return err
	}
	if a.G.JSON {
		return printJSON(a.Stdout, act)
	}
	id, _ := act["id"].(string)
	if a.G.Quiet {
		fmt.Fprintln(a.Stdout, sanitize(id))
		return nil
	}
	fmt.Fprintf(a.Stdout, "%s requested. Approval id: %s\nAn owner approves it with a passkey (dashboard or phone app); follow it with: onemind actions info %s\n",
		what, sanitize(id), sanitize(id))
	return nil
}

func tlsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "tls", Short: "The box's certificate authority: show it, download it to trust the box"}
	g.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "The CA fingerprint, the names the HTTPS certificate covers and when it expires (GET /v1/tls)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw map[string]any
			if err := c.Do(bg(), http.MethodGet, "/v1/tls", nil, &raw); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, raw)
			}
			var names []string
			if l, ok := raw["names"].([]any); ok {
				for _, n := range l {
					names = append(names, sanitize(fmt.Sprint(n)))
				}
			}
			return kv(a.Stdout, [][2]string{
				{"CA sha256", sanitize(fmt.Sprint(orEmpty(raw["ca_sha256"])))},
				{"https", fmt.Sprint(raw["https"])},
				{"names", strings.Join(names, ", ")},
				{"expires", fmt.Sprint(orEmpty(raw["not_after"]))},
			})
		},
	})
	var der bool
	var out, pin string
	ca := &cobra.Command{
		Use:   "ca",
		Short: "Download the box CA certificate (PEM by default). It is public; check its fingerprint with --pin",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			t, err := a.resolve()
			if err != nil {
				return err
			}
			format := "pem"
			if der {
				format = "der"
			}
			cl := &http.Client{Timeout: a.G.Timeout}
			resp, err := cl.Get(strings.TrimRight(t.hub, "/") + "/v1/tls/ca.crt?format=" + format)
			if err != nil {
				return exitWith(ExitUnreachable, "network", sanitize(err.Error()))
			}
			defer resp.Body.Close()
			raw, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			if err != nil {
				return exitWith(ExitUnreachable, "network", sanitize(err.Error()))
			}
			if resp.StatusCode != http.StatusOK {
				return exitWith(ExitError, "error", fmt.Sprintf("the box answered %d", resp.StatusCode))
			}
			derBytes := raw
			if !der {
				blk, _ := pem.Decode(raw)
				if blk == nil || blk.Type != "CERTIFICATE" {
					return exitWith(ExitError, "unexpected_response", "the box did not send a PEM certificate")
				}
				derBytes = blk.Bytes
			}
			if _, err := x509.ParseCertificate(derBytes); err != nil {
				return exitWith(ExitError, "unexpected_response", "the box did not send a certificate")
			}
			sum := sha256.Sum256(derBytes)
			fp := hex.EncodeToString(sum[:])
			if pin != "" && !strings.EqualFold(strings.ReplaceAll(pin, ":", ""), fp) {
				return exitWith(ExitError, "fingerprint_mismatch", "the certificate's sha256 is "+fp+", not the pinned "+sanitize(pin)+": not saved")
			}
			if out != "" {
				if err := os.WriteFile(out, raw, 0o644); err != nil {
					return err
				}
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.tls/v1", "format": format, "sha256": fp, "saved_to": out})
			}
			if out == "" {
				if der {
					return exitWith(ExitUsage, "usage", "--der writes binary: add -o FILE")
				}
				_, _ = a.Stdout.Write(raw)
				fmt.Fprintln(a.Stderr, "sha256:", fp)
				return nil
			}
			fmt.Fprintf(a.Stdout, "saved %s\nsha256: %s\nCompare it with the fingerprint in the pairing QR or `onemind tls show` before you trust it.\n", out, fp)
			return nil
		},
	}
	ca.Flags().BoolVar(&der, "der", false, "binary DER instead of PEM (needs -o)")
	ca.Flags().StringVarP(&out, "output", "o", "", "write the certificate to this file")
	ca.Flags().StringVar(&pin, "pin", "", "refuse unless the certificate has this sha256 fingerprint")
	g.AddCommand(ca)
	return g
}

// networkShowCmd is `onemind network show`; networkCommands (network.go) puts it beside set, dhcp and confirm.
func networkShowCmd(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "show",
		Short: "Interfaces, addresses, gateway, DNS and listening ports (owner; GET /v1/network)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var v netView
			raw, err := getBoth(a, "/v1/network", &v)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			if !v.Available {
				return exitWith(ExitError, "unavailable", "the box's network cannot be read: "+sanitize(deref(v.Message)))
			}
			var rows [][]string
			for _, i := range v.Interfaces {
				sig := ""
				if i.Wifi != nil && i.Wifi.SignalDBM != nil {
					sig = strconv.Itoa(*i.Wifi.SignalDBM) + " dBm"
				}
				rows = append(rows, []string{sanitize(i.Name), i.Kind, i.State, dash(strings.Join(i.Addresses, ", ")), sig})
			}
			if err := table(a.Stdout, "INTERFACE\tKIND\tSTATE\tADDRESSES\tWI-FI", rows); err != nil {
				return err
			}
			for _, gw := range v.Gateways {
				fmt.Fprintf(a.Stdout, "gateway (%s): %s via %s\n", gw.Family, sanitize(gw.Via), sanitize(gw.Interface))
			}
			fmt.Fprintf(a.Stdout, "dns: %s\n", dash(sanitize(strings.Join(v.DNS, ", "))))
			rows = nil
			for _, p := range v.Ports {
				rows = append(rows, []string{p.Proto, sanitize(p.Addr), strconv.Itoa(p.Port), p.Scope})
			}
			return table(a.Stdout, "PROTO\tADDRESS\tPORT\tREACH", rows)
		},
	}
}
