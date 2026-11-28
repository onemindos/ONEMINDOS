// SPDX-License-Identifier: Apache-2.0

package cli

// onemind plugins: the plugins installed on this box, their settings, the host access they hold, and
// the keys that sign them (GET /v1/plugins, /v1/host-grants, /v1/plugin-trust/keys). `onemind plugin`
// (singular) is the developer's tool for a plugin folder; this is the owner's view of a box. Every
// change only FILES a request that an owner approves; taking a host grant back is the one direct
// write, and the gateway restricts it to an owner.

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/spf13/cobra"
)

func pluginsBoxCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "plugins", Short: "Plugins on this box: list, settings, host access and signing keys (changes wait for an owner)"}

	root.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "The installed plugins (GET /v1/plugins)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/plugins", "ID\tNAME\tVERSION\tSTATE\tPLACES", func(m map[string]any) []string {
				return []string{str(m["id"]), str(m["name"]), dash(str(m["installed_version"])), str(m["status"]), dash(strings.Join(declaredSlots(m), ","))}
			})
		},
	})
	root.AddCommand(&cobra.Command{
		Use:   "show PLUGIN_ID",
		Short: "One plugin (GET /v1/plugins/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/plugins/"+pathID(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				rows := [][2]string{{"id", str(m["id"])}, {"name", str(m["name"])}, {"version", dash(str(m["installed_version"]))}, {"state", str(m["status"])}}
				for _, sl := range slotList(m) {
					row := "not declared"
					if sl["declared"] == true {
						row = "declared"
						if names := strs(sl["names"]); len(names) > 0 {
							row += ": " + strings.Join(names, ", ")
						}
						if sl["approval"] == "each_time" {
							row += " (asks a person each time)"
						}
					}
					rows = append(rows, [2]string{"place " + str(sl["slot"]), row})
				}
				return kv(w, rows)
			})
		},
	})
	root.AddCommand(&cobra.Command{
		Use:   "tools PLUGIN_ID",
		Short: "The tools a plugin offers (GET /v1/plugins/ID/tools)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.getTable("/v1/plugins/"+pathID(args[0])+"/tools", "NAME\tEFFECT\tTITLE", func(m map[string]any) []string {
				return []string{str(m["name"]), str(m["effect"]), dash(str(m["title"]))}
			})
		},
	})

	settings := &cobra.Command{Use: "settings", Short: "A plugin's settings"}
	settings.AddCommand(&cobra.Command{
		Use:   "show PLUGIN_ID",
		Short: "Current settings and the bundle they belong to (GET /v1/plugins/ID/settings)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/plugins/"+pathID(args[0])+"/settings", func(w io.Writer, v any) error {
				m := obj(v)
				fmt.Fprintf(w, "bundle  %s\n", str(m["bundle_sha256"]))
				return printJSON(w, m["settings"])
			})
		},
	})
	var file string
	setSettings := &cobra.Command{
		Use:   "set PLUGIN_ID --file settings.json",
		Short: "Request new settings from a JSON file, or - for stdin (POST /v1/plugins/ID/settings); an owner approves",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			newSettings, err := a.readJSONInput(cmd, file)
			if err != nil {
				return err
			}
			// The request names the bundle the settings were read against, so a plugin updated in
			// between cannot receive settings written for another version.
			cur, err := a.gwDo(http.MethodGet, "/v1/plugins/"+pathID(args[0])+"/settings", nil)
			if err != nil {
				return err
			}
			key := freshKey()
			body := map[string]any{"settings": newSettings, "bundle_sha256": str(obj(cur)["bundle_sha256"]), "idempotency_key": key, "expires_at": expiry()}
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/plugins/"+pathID(args[0])+"/settings", key, body)
			if err != nil {
				return err
			}
			return a.printRequested("settings for plugin "+args[0], v)
		},
	}
	setSettings.Flags().StringVar(&file, "file", "", "the new settings, as a JSON object")
	settings.AddCommand(setSettings)
	root.AddCommand(settings)

	// Lifecycle: each only files a request. The owner decides in Approvals; the CLI never approves (D-027).
	for _, l := range []struct{ use, typ, short string }{
		{"restart", "app.restart", "Request a restart of a plugin that stopped responding"},
		{"disable", "app.stop", "Request that a plugin be stopped (its data is kept)"},
		{"enable", "app.start", "Request that a stopped plugin be started again"},
		{"update", "app.update", "Request the update the catalog offers; kept only if healthy, else the previous revision returns"},
	} {
		l := l
		root.AddCommand(&cobra.Command{
			Use:   l.use + " PLUGIN_ID",
			Short: l.short + " (POST /v1/actions " + l.typ + ")",
			Args:  cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				return a.fileAction(l.typ, map[string]any{"app_id": args[0]}, "", l.use+" plugin "+args[0])
			},
		})
	}

	root.AddCommand(pluginHostGrantsCmd(a), pluginKeysCmd(a))
	return []*cobra.Command{root}
}

func pluginHostGrantsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "host-grants", Short: "Access to the machine itself that an app was given: devices, GPU, network, real-time"}
	var app string
	lst := &cobra.Command{
		Use:   "list",
		Short: "What each app may use on the host (GET /v1/host-grants); an owner sees all",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/host-grants"+query("app_id", app), func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(obj(v)["grants"]) {
					m := obj(x)
					state := "active"
					if m["active"] != true {
						state = "revoked"
					}
					what := str(m["kind"])
					if p := str(m["path"]); p != "" {
						what += " " + p
					} else if c := str(m["device_class"]); c != "" {
						what += " " + c
					}
					rows = append(rows, []string{str(m["id"]), str(m["app_id"]), what, state, str(m["reason"])})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "No app has been given host access.")
					return nil
				}
				return table(w, "ID\tAPP\tACCESS\tSTATE\tWHY", rows)
			})
		},
	}
	lst.Flags().StringVar(&app, "app", "", "only this app")

	var rApp, kind, class, path, reason string
	req := &cobra.Command{
		Use:   "request --app APP --kind device|gpu|host-network|realtime --reason TEXT [--class usb-serial|usb|video] [--path /dev/...]",
		Short: "Request host access for an app (POST /v1/host-grants/requests); an owner approves",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if rApp == "" || kind == "" || reason == "" {
				return usageErr(cmd, "--app, --kind and --reason are required")
			}
			key := freshKey()
			body := map[string]any{"app_id": rApp, "kind": kind, "reason": reason, "idempotency_key": key, "expires_at": expiry()}
			if class != "" {
				body["device_class"] = class
			}
			if path != "" {
				body["path"] = path
			}
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/host-grants/requests", key, body)
			if err != nil {
				return err
			}
			return a.printRequested(kind+" access for "+rApp, v)
		},
	}
	req.Flags().StringVar(&rApp, "app", "", "the app")
	req.Flags().StringVar(&kind, "kind", "", "device, gpu, host-network or realtime")
	req.Flags().StringVar(&class, "class", "", "device class: usb-serial, usb or video")
	req.Flags().StringVar(&path, "path", "", "the device path")
	req.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")

	var yes bool
	rev := &cobra.Command{
		Use:   "revoke GRANT_ID --yes",
		Short: "Take the access back now (POST /v1/host-grants/ID/revoke); owner only",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, yes, "revoking "+args[0]+" stops the app using that part of the machine"); err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPost, "/v1/host-grants/"+pathID(args[0])+"/revoke", nil)
			if err != nil {
				return err
			}
			return a.printDone(v, "Revoked %s.", args[0])
		},
	}
	rev.Flags().BoolVar(&yes, "yes", false, "confirm")
	g.AddCommand(lst, req, rev)
	return g
}

func pluginKeysCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "keys", Short: "The keys whose signature this box trusts on plugins"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Trusted signing keys (GET /v1/plugin-trust/keys)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/plugin-trust/keys", func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(obj(v)["keys"]) {
					m := obj(x)
					state := "active"
					if m["active"] != true {
						state = "revoked"
					}
					rows = append(rows, []string{str(m["id"]), str(m["name"]), state, str(m["enrolled_at"])})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "No signing keys are trusted yet.")
					return nil
				}
				return table(w, "ID\tNAME\tSTATE\tENROLLED", rows)
			})
		},
	})
	var name, keyFile string
	enroll := &cobra.Command{
		Use:   "enroll --name NAME --key-file public.pem",
		Short: "Request trusting a new signing key (POST /v1/plugin-trust/keys/requests); an owner approves",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if name == "" || keyFile == "" {
				return usageErr(cmd, "--name and --key-file are required")
			}
			raw, err := os.ReadFile(keyFile)
			if err != nil {
				return exitWith(ExitUsage, "usage", "cannot read "+keyFile+": "+err.Error())
			}
			key := freshKey()
			body := map[string]any{"name": name, "public_key": strings.TrimSpace(string(raw)), "idempotency_key": key, "expires_at": expiry()}
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/plugin-trust/keys/requests", key, body)
			if err != nil {
				return err
			}
			return a.printRequested("trusting the signing key "+name, v)
		},
	}
	enroll.Flags().StringVar(&name, "name", "", "a name for the key")
	enroll.Flags().StringVar(&keyFile, "key-file", "", "the public key file")
	revoke := &cobra.Command{
		Use:   "revoke KEY_ID",
		Short: "Request no longer trusting a key (POST /v1/plugin-trust/keys/ID/revoke); an owner approves",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			key := freshKey()
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/plugin-trust/keys/"+pathID(args[0])+"/revoke", key, map[string]any{"idempotency_key": key, "expires_at": expiry()})
			if err != nil {
				return err
			}
			return a.printRequested("revoking the signing key "+args[0], v)
		},
	}
	g.AddCommand(enroll, revoke)
	return g
}

func init() { groups = append(groups, pluginsBoxCommands) }

// slotList is the plugin's five defined places as the gateway reports them (GET /v1/plugins).
func slotList(m map[string]any) []map[string]any {
	var out []map[string]any
	if raw, ok := m["slots"].([]any); ok {
		for _, x := range raw {
			if sl, ok := x.(map[string]any); ok {
				out = append(out, sl)
			}
		}
	}
	return out
}

func declaredSlots(m map[string]any) []string {
	var out []string
	for _, sl := range slotList(m) {
		if sl["declared"] == true {
			out = append(out, str(sl["slot"]))
		}
	}
	return out
}

func strs(v any) []string {
	var out []string
	if raw, ok := v.([]any); ok {
		for _, x := range raw {
			out = append(out, str(x))
		}
	}
	return out
}
