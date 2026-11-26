// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind my-devices` (UI parity M4, #1232): the CLI side of Settings > Account and security > My devices.
// `list` is GET /v1/me/devices; `remove` is DELETE /v1/me/devices/{id} (Lost this device). Both need a person's
// own signed-in session (a bearer session from `POST /v1/auth/login` with client "cli"), never an API token. Once
// the box has passkeys, `remove` also needs a fresh passkey sign-in, which a terminal cannot give (WebAuthn needs
// a browser or the phone), so the gateway refuses it here with step_up_required and the CLI says to use the
// dashboard or the phone. The CLI adds no check of its own: the gateway decides and audits.

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

type myDevice struct {
	ID          string  `json:"id"`
	Label       string  `json:"label"`
	Kind        string  `json:"kind"`
	Current     bool    `json:"current"`
	LastSeenAt  *string `json:"last_seen_at"`
	Credentials []struct {
		Source string `json:"source"`
		ID     string `json:"id"`
	} `json:"credentials"`
}

type myDevicesView struct {
	Devices []myDevice `json:"devices"`
}

type myDeviceRemoved struct {
	ID      string         `json:"id"`
	Removed bool           `json:"removed"`
	Revoked map[string]int `json:"revoked"`
}

var credWords = map[string][2]string{
	"sessions":      {"sign-in", "sign-ins"},
	"passkeys":      {"passkey", "passkeys"},
	"approver_keys": {"approver key", "approver keys"},
	"push":          {"push registration", "push registrations"},
}

// holdsText says what a device holds: "2 sign-ins, 1 passkey".
func holdsText(d myDevice) string {
	n := map[string]int{}
	var order []string
	for _, c := range d.Credentials {
		if n[c.Source] == 0 {
			order = append(order, c.Source)
		}
		n[c.Source]++
	}
	var parts []string
	for _, k := range order {
		w, ok := credWords[k]
		word := k
		if ok {
			word = w[0]
			if n[k] != 1 {
				word = w[1]
			}
		}
		parts = append(parts, fmt.Sprintf("%d %s", n[k], word))
	}
	if len(parts) == 0 {
		return "nothing"
	}
	return strings.Join(parts, ", ")
}

// explainDevices adds what to do when the gateway wants a session or a fresh passkey. The gateway sends
// reason=session_required; an older one sent a bare 403, which on these commands means the same thing.
func explainDevices(err error) error {
	var e *onemind.Error
	if errors.As(err, &e) && e.Status == 403 && (e.Reason == "session_required" || e.Reason == "") {
		return fmt.Errorf("%w\nMy devices needs your own signed-in session, not an API token. Use the dashboard (Settings > Account and security) or the phone app", err)
	}
	if errors.As(err, &e) && e.Reason == "current_device" {
		return fmt.Errorf("%w\nTo stop this device, sign it out instead", err)
	}
	return explainGateway(err)
}

func myDevicesCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "my-devices", Short: "Phones, browsers and apps signed in as you; remove a lost one (GET /v1/me/devices)"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your devices, what each holds and when it was last seen",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var v myDevicesView
			raw, err := getBoth(a, "/v1/me/devices", &v)
			if err != nil {
				return explainDevices(err)
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			sort.SliceStable(v.Devices, func(i, j int) bool { return v.Devices[i].Current && !v.Devices[j].Current })
			now := time.Now()
			var rows [][]string
			for _, d := range v.Devices {
				seen := "unknown"
				if d.LastSeenAt != nil {
					seen = age(*d.LastSeenAt, now)
				}
				here := ""
				if d.Current {
					here = "this one"
				}
				rows = append(rows, []string{d.ID, sanitize(d.Label), d.Kind, seen, holdsText(d), here})
			}
			if len(rows) == 0 {
				fmt.Fprintln(a.Stdout, "No devices are signed in as you.")
				return nil
			}
			return table(a.Stdout, "ID\tDEVICE\tKIND\tLAST SEEN\tHOLDS\t\t", rows)
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "remove DEVICE_ID",
		Short: "Lost this device: revoke every sign-in, passkey, approver key and push registration it holds",
		Long: "Revokes everything the device holds in one step; it has to sign in again to come back. Refused for the\n" +
			"device you are using and for the box's last owner passkey. Once the box has passkeys the gateway asks for\n" +
			"a fresh passkey sign-in, which the CLI cannot do: use the dashboard or the phone app then.",
		Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var r myDeviceRemoved
			if err := c.Do(bg(), http.MethodDelete, "/v1/me/devices/"+url.PathEscape(args[0]), nil, &r); err != nil {
				return explainDevices(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, r)
			}
			if !r.Removed {
				fmt.Fprintf(a.Stdout, "%s was already removed; nothing was left to revoke\n", sanitize(args[0]))
				return nil
			}
			total := 0
			for _, n := range r.Revoked {
				total += n
			}
			fmt.Fprintf(a.Stdout, "%s removed: %d credentials revoked. It has to sign in again to use this box.\n", sanitize(r.ID), total)
			return nil
		},
	})
	return []*cobra.Command{g}
}
