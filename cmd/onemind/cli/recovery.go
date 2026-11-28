// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
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
	Action  onemind.Action `json:"action"`
	Kit     kitState       `json:"kit"`
	OneTime struct {
		OwnerKey string `json:"owner_key"`
		DiskKey  string `json:"disk_recovery_key"`
		Text     string `json:"text"`
	} `json:"one_time"`
}

// kitReceipt names the filed request. It holds no secret: the page is released only to the signed-in owner
// session that approved the request (founder decision 2026-11-28, option A), never to whoever holds a receipt.
type kitReceipt struct {
	ActionID string `json:"action_id"`
	Key      string `json:"idempotency_key"`
}

func (r kitReceipt) headers() map[string]string {
	return map[string]string{"Idempotency-Key": r.Key}
}

// recoveryKitCommand is `onemind recovery kit`: the printed emergency kit (D-028). It is added to the one
// `onemind recovery` group built in recovery_contacts.go (train 2026-11-28 merge of #1323 and #1196). `status` shows where the kit
// stands and never a key. `issue` files a request (POST /v1/backups/kit/request) and saves a receipt. Only the
// signed-in owner session that approves the request can claim the page, once (POST /v1/backups/kit/{id}/claim):
// sign in with `onemind login`, approve it from that same session (`onemind actions approve ID`), then `collect`.
// An API token, an agent or another session is refused. The page
// holds the owner key and, when /data is encrypted and its key is still waiting, the disk recovery key; both
// are shown once, so the page goes to a new 0600 file or stdout. Confirming it in Backups activates the
// new console key.
func recoveryKitCommand(a *App) *cobra.Command {
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
	var receiptPath, out string
	issue := &cobra.Command{
		Use:   "issue",
		Short: "Request a new kit and save its private collection receipt",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			f, err := os.OpenFile(receiptPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
			if err != nil {
				return exitWith(ExitError, "write_failed", "nothing was requested: "+err.Error())
			}
			saved := false
			defer func() {
				f.Close()
				if !saved {
					os.Remove(receiptPath)
				}
			}()
			r := kitReceipt{Key: onemind.NewIdempotencyKey()}
			var pending onemind.Action
			if err := cl.DoOnceWithHeaders(bg(), http.MethodPost, "/v1/backups/kit/request", r.headers(), nil, &pending); err != nil {
				return err
			}
			if pending.Id == "" || pending.Type != "backup.kit.issue" || pending.State != "awaiting_approval" || pending.IdempotencyKey != r.Key {
				return exitWith(ExitError, "unexpected_response", "the hub did not return the pending kit request")
			}
			r.ActionID = pending.Id
			if err := json.NewEncoder(f).Encode(r); err != nil {
				return exitWith(ExitError, "write_failed", "the request was filed but its receipt could not be saved; file a new request")
			}
			if err := f.Close(); err != nil {
				return exitWith(ExitError, "write_failed", "the request was filed but its receipt could not be saved; file a new request")
			}
			saved = true
			if a.G.JSON {
				return printJSON(a.Stdout, pending)
			}
			fmt.Fprintf(a.Stdout, "Requested %s. Approve it from this signed-in session (onemind actions approve %s), then run onemind recovery kit collect with the receipt file. Only the session that approves it can collect the page.\n", sanitize(pending.Id), sanitize(pending.Id))
			return nil
		},
	}
	issue.Flags().StringVar(&receiptPath, "receipt", "", "save the receipt to this new file (mode 0600)")
	_ = issue.MarkFlagRequired("receipt")
	collect := &cobra.Command{
		Use:   "collect RECEIPT",
		Short: "Collect the recovery page once, from the signed-in session that approved the request",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			var r kitReceipt
			data, err := os.ReadFile(args[0])
			if err != nil {
				return err
			}
			if err := json.Unmarshal(data, &r); err != nil || r.ActionID == "" || r.Key == "" {
				return exitWith(ExitUsage, "usage", "invalid kit receipt")
			}
			action, err := cl.Actions.Get(bg(), r.ActionID)
			if err != nil {
				return err
			}
			if action.Type != "backup.kit.issue" || action.IdempotencyKey != r.Key {
				return exitWith(ExitUsage, "usage", "receipt does not match the kit request")
			}
			if action.State == "awaiting_approval" || action.State == "accepted" || action.State == "dispatched" {
				return exitWith(ExitPending, "pending", "the kit is waiting for owner approval or issuance")
			}
			if action.State != "succeeded" {
				return exitWith(ExitConflict, "conflict", "the kit was not issued; file a new request")
			}
			// Reserve the output path before consuming the one-time page.
			var f *os.File
			if out != "" {
				f, err = os.OpenFile(out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
				if err != nil {
					return exitWith(ExitError, "write_failed", "nothing was collected: "+out+" cannot be created ("+err.Error()+
						"); choose a new file name")
				}
			}
			var k kitIssued
			err = cl.DoOnceWithHeaders(bg(), http.MethodPost, "/v1/backups/kit/"+url.PathEscape(r.ActionID)+"/claim", nil, nil, &k)
			if err != nil || k.Action.Id != r.ActionID || k.OneTime.Text == "" {
				if f != nil {
					f.Close()
					os.Remove(out)
				}
				if err != nil {
					return err
				}
				return exitWith(ExitError, "unexpected_response", "the hub did not return the requested kit page")
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
				fmt.Fprintf(a.Stdout, "kit saved to %s (fingerprint %s). Print it, keep it offline and confirm it in Backups.\n", out, dash(deref(k.Kit.Fingerprint)))
				return nil
			}
			if a.G.JSON {
				return printJSON(a.Stdout, k)
			}
			_, err = fmt.Fprint(a.Stdout, k.OneTime.Text)
			return err
		},
	}
	collect.Flags().StringVar(&out, "out", "", "write the kit page to this new file (mode 0600) instead of the terminal")
	kit.AddCommand(issue, collect)
	return kit
}
