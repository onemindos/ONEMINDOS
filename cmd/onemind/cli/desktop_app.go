// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// desktopAppCommands are `onemind desktop-app list|search|install|update|remove|launch` (issue #1097, D-026, D-027):
// desktop apps from Flathub, each in its own sandbox, shown in a browser tab by the streaming runtime.
//
// install, update and remove only file a request (POST /v1/actions) and print its id: an owner approves it in the
// dashboard or the phone app, so a script or an agent's token can ask but never run it. list, search and launch are
// owner reads and one audited start; they change nothing on the box beyond starting an installed app.
func desktopAppCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "desktop-app", Short: "Desktop apps from Flathub: search, install, update, remove, launch"}
	g.AddCommand(&cobra.Command{
		Use: "list", Short: "Installed desktop apps and whether the box can run them (owner)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			var v desktopView
			if err := a.desktopGet("/v1/desktop-apps", &v); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			if !v.Service.Available {
				fmt.Fprintln(a.Stdout, "Desktop apps are not available on this box:", sanitize(v.Service.Message))
				return nil
			}
			rows := [][]string{}
			for _, x := range v.Installed {
				up := ""
				if x.UpdateAvailable {
					up = "update waiting"
				}
				rows = append(rows, []string{x.ID, x.Name, x.Version, up, x.Folder})
			}
			return table(a.Stdout, "APP\tNAME\tVERSION\tUPDATE\tFOLDER", rows)
		},
	})
	g.AddCommand(&cobra.Command{
		Use: "search TEXT", Short: "Search Flathub by name, summary or app id (owner)", Args: cobra.MinimumNArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			var v struct {
				Results []desktopApp `json:"results"`
			}
			if err := a.desktopGet("/v1/desktop-apps/search?q="+url.QueryEscape(strings.Join(args, " ")), &v); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			rows := [][]string{}
			for _, x := range v.Results {
				have := ""
				if x.Installed {
					have = "installed"
				}
				rows = append(rows, []string{x.ID, x.Name, x.Version, have, x.Summary})
			}
			return table(a.Stdout, "APP\tNAME\tVERSION\tSTATE\tSUMMARY", rows)
		},
	})
	for _, k := range []struct{ verb, short string }{
		{"install", "Ask to install an app from Flathub; an owner approves (prints the approval id)"},
		{"update", "Ask to update an installed app; an owner approves"},
		{"remove", "Ask to remove an installed app (its folder of files stays); an owner approves"},
	} {
		k := k
		g.AddCommand(&cobra.Command{
			Use: k.verb + " APP_ID", Short: k.short, Args: cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error { return a.desktopRequest(k.verb, args[0]) },
		})
	}
	g.AddCommand(&cobra.Command{
		Use: "launch APP_ID", Short: "Start an installed app in the streaming session (owner)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var out map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/desktop-apps/"+url.PathEscape(args[0])+"/launch", nil, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			fmt.Fprintf(a.Stdout, "%s is starting. Open it in the dashboard under Desktop apps.\n", sanitize(args[0]))
			return nil
		},
	})
	return []*cobra.Command{g}
}

type desktopApp struct {
	ID              string `json:"app_id"`
	Name            string `json:"name"`
	Summary         string `json:"summary"`
	Version         string `json:"version"`
	Installed       bool   `json:"installed"`
	UpdateAvailable bool   `json:"update_available"`
	Folder          string `json:"folder"`
}

type desktopView struct {
	Service struct {
		Available bool   `json:"available"`
		Message   string `json:"message"`
	} `json:"service"`
	Installed []desktopApp `json:"installed"`
}

func (a *App) desktopGet(path string, out any) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	return c.Do(bg(), http.MethodGet, path, nil, out)
}

// desktopRequest files desktop.app.<verb> and prints the approval id. It never approves.
func (a *App) desktopRequest(verb, appID string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	if _, err := c.Instance.Get(bg()); err != nil { // learn the hub clock first, as Actions.Request does
		return err
	}
	body := map[string]any{"type": "desktop.app." + verb, "params": map[string]string{"app_id": appID},
		"idempotency_key": "cli-" + verb + "-" + fmt.Sprint(time.Now().UnixNano()),
		"expires_at":      c.HubNow().Add(24 * time.Hour).UTC().Format(time.RFC3339)}
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
	fmt.Fprintf(a.Stdout, "Request to %s %s filed. Approval id: %s\nAn owner approves it in the dashboard or the phone app; follow it with: onemind actions info %s\n",
		verb, sanitize(appID), sanitize(id), sanitize(id))
	return nil
}
