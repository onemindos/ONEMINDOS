// SPDX-License-Identifier: Apache-2.0

package cli

// Sign-in keys and verification levels (D-028; gateway permissions design 3.11, PR 11):
// `onemind keys list|remove`, `onemind keys models list|add|remove` and
// `onemind permissions verify get|set`. Reads print a table or --json. Writes only request: changing
// the verification table files verification.requirement.set and trusting a key model files
// authenticator.allowlist.add; an owner approves each in the dashboard or phone app with a key at the
// level the table asks for (L2 by default). Removing a key or a trusted model only takes power away,
// so those are direct owner calls the gateway audits. Adding a key needs a browser or the phone app
// (WebAuthn), so there is no `keys add` here.

import (
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type signInKey struct {
	ID          string  `json:"credential_id"`
	Label       string  `json:"label"`
	CreatedAt   string  `json:"created_at"`
	LastUsedAt  *string `json:"last_used_at"`
	Level       string  `json:"level"`
	LevelReason string  `json:"level_reason"`
	Explanation string  `json:"explanation"`
	Model       *string `json:"model"`
	DeviceBound *bool   `json:"device_bound"`
}

type trustedModel struct {
	AAGUID     string   `json:"aaguid"`
	Name       string   `json:"name"`
	UV         []string `json:"user_verification"`
	Biometric  bool     `json:"biometric"`
	Source     string   `json:"source"`
	RootsCount int      `json:"roots"`
}

type verificationTable struct {
	Rows []struct {
		Key     string `json:"key"`
		Label   string `json:"label"`
		Default string `json:"default"`
		Current string `json:"current"`
		Minimum string `json:"minimum"`
		Maximum string `json:"maximum"`
	} `json:"rows"`
	Types []struct {
		Key     string `json:"key"`
		Current string `json:"current"`
	} `json:"types"`
	HouseholdLevel *string `json:"household_level"`
	Grace          bool    `json:"grace"`
}

var levelNames = map[string]string{"L0": "Signed in", "L1": "Device check", "L2": "Proven key", "L3": "Biometric-only key"}

func keysCommands(a *App) []*cobra.Command {
	return []*cobra.Command{keysCmd(a), permissionsCmd(a)}
}

func keysCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "keys", Short: "Your sign-in keys (passkeys) and their verification levels"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your keys: level, model, synced or device-bound (GET /v1/auth/passkeys)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var list []signInKey
			raw, err := getBoth(a, "/v1/auth/passkeys", &list)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			now := time.Now()
			var rows [][]string
			for _, k := range list {
				model, kind, used := "-", "-", "never"
				if k.Model != nil {
					model = sanitize(*k.Model)
				}
				if k.DeviceBound != nil {
					kind = map[bool]string{true: "device-bound", false: "synced"}[*k.DeviceBound]
				}
				if k.LastUsedAt != nil {
					used = age(*k.LastUsedAt, now)
				}
				rows = append(rows, []string{sanitize(k.Label), k.Level + " " + levelNames[k.Level], model, kind, age(k.CreatedAt, now), used})
			}
			if err := table(a.Stdout, "KEY\tLEVEL\tMODEL\tKIND\tADDED\tLAST USED", rows); err != nil {
				return err
			}
			for _, k := range list {
				if k.Level != "L2" && k.Level != "L3" && k.Explanation != "" {
					fmt.Fprintf(a.Stdout, "%s: %s\n", sanitize(k.Label), sanitize(k.Explanation))
				}
			}
			return nil
		},
	})
	g.AddCommand(&cobra.Command{
		Use:   "remove CREDENTIAL_ID",
		Short: "Remove one of your keys (needs a recent passkey sign-in; the last owner key stays)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodDelete, "/v1/auth/passkeys/"+url.PathEscape(args[0]), nil, nil); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.keys/v1", "removed": args[0]})
			}
			fmt.Fprintf(a.Stdout, "key %s removed\n", sanitize(args[0]))
			return nil
		},
	})
	g.AddCommand(modelsCmd(a))
	return g
}

func modelsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "models", Short: "Trusted key models: which security keys can be proven keys (L2)"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The trusted models, shipped with the OS or added by an owner (GET /v1/auth/authenticator-allowlist)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var list []trustedModel
			raw, err := getBoth(a, "/v1/auth/authenticator-allowlist", &list)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			var rows [][]string
			for _, m := range list {
				bio := "no"
				if m.Biometric {
					bio = "yes"
				}
				rows = append(rows, []string{sanitize(m.Name), m.AAGUID, bio, m.Source})
			}
			return table(a.Stdout, "MODEL\tAAGUID\tFINGERPRINT/FACE\tFROM", rows)
		},
	})
	var name, reason string
	var roots, uv []string
	add := &cobra.Command{
		Use:   "add AAGUID",
		Short: "Ask to trust a key model; an owner approves it with a proven key",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if name == "" || len(roots) == 0 || len(uv) == 0 {
				return exitWith(ExitUsage, "usage", "--name, --root and --uv are required")
			}
			var pems []string
			for _, f := range roots {
				b, err := os.ReadFile(f)
				if err != nil {
					return exitWith(ExitUsage, "usage", "cannot read "+f)
				}
				pems = append(pems, string(b))
			}
			params := map[string]any{"aaguid": args[0], "name": name, "roots": pems, "user_verification": uv}
			return a.fileAction("authenticator.allowlist.add", params, reason, "Trusting "+sanitize(name))
		},
	}
	add.Flags().StringVar(&name, "name", "", "the model's name, e.g. from FIDO MDS")
	add.Flags().StringArrayVar(&roots, "root", nil, "a PEM file holding the model's attestation root (repeatable)")
	add.Flags().StringSliceVar(&uv, "uv", nil, "user verification methods from FIDO MDS, e.g. fingerprint_internal,passcode_internal")
	add.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	g.AddCommand(add)
	g.AddCommand(&cobra.Command{
		Use:   "remove AAGUID",
		Short: "Stop trusting a model you added; its keys drop to Device check (L1) at once",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if err := c.Do(bg(), http.MethodDelete, "/v1/auth/authenticator-allowlist/"+url.PathEscape(args[0]), nil, nil); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.keys/v1", "untrusted": args[0]})
			}
			fmt.Fprintf(a.Stdout, "model %s is no longer trusted\n", sanitize(args[0]))
			return nil
		},
	})
	return g
}

func permissionsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "permissions", Short: "How approvals are checked"}
	v := &cobra.Command{Use: "verify", Short: "The verification table: which key level each kind of approval needs"}
	v.AddCommand(&cobra.Command{
		Use:   "get",
		Short: "Each row's level now, its default and the lowest it may go (GET /v1/verification-requirements)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var t verificationTable
			raw, err := getBoth(a, "/v1/verification-requirements", &t)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printRawJSON(a, raw)
			}
			var rows [][]string
			for _, r := range t.Rows {
				rows = append(rows, []string{r.Key, r.Current, r.Default, r.Minimum, r.Maximum, sanitize(r.Label)})
			}
			for _, r := range t.Types {
				rows = append(rows, []string{r.Key, r.Current, "-", "L1", "L3", "opt-in for this action type"})
			}
			if err := table(a.Stdout, "ROW\tNOW\tDEFAULT\tLOWEST\tHIGHEST\tWHAT", rows); err != nil {
				return err
			}
			if t.Grace {
				fmt.Fprintln(a.Stdout, "No owner has a proven key yet: L2 rows accept a Device check key, except physical actions and the motion lockout.")
			}
			return nil
		},
	})
	var reason string
	set := &cobra.Command{
		Use:   "set ROW LEVEL",
		Short: "Ask to change a row (or type:<action type>) to L1, L2 or L3; an owner approves it with a proven key",
		Args:  cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			level := strings.ToUpper(args[1])
			if _, ok := levelNames[level]; !ok {
				return exitWith(ExitUsage, "usage", "LEVEL must be L0, L1, L2 or L3")
			}
			params := map[string]any{"key": args[0], "level": level}
			return a.fileAction("verification.requirement.set", params, reason, sanitize(args[0])+" at "+level)
		},
	}
	set.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	v.AddCommand(set)
	g.AddCommand(v)
	return g
}
