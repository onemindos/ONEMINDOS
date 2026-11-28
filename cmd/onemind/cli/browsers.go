// SPDX-License-Identifier: Apache-2.0

package cli

// onemind browsers: your own private browser window on the box (POST /v1/browsers/{app}/session,
// .../session/close, .../profile/reset). Only a signed-in person may use these routes: the gateway
// refuses every API token, so a script or an AI agent cannot open a person's browser. Erasing the
// profile only FILES a request that an owner approves.
//
// That also means the usual CLI credential does NOT work here: `onemind login` saves an API token
// (om_...), and the gateway answers 403 to it. Only a sign-in session (the dashboard or the phone app)
// opens a browser. The commands stay so a session token works, and a 403 is explained in plain words.

import (
	"errors"
	"fmt"
	"net/http"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
)

// browserSignInHint is printed under the gateway's 403 on a browsers route.
const browserSignInHint = "The box opens your own browser only for a person signed in through the dashboard or the phone app.\n" +
	"The token `onemind login` saved is an API token, and the box refuses every API token here, so a script or an\n" +
	"AI agent can never open a person's browser. Open the browser app from the dashboard instead.\n" +
	"(Already signed in there and still refused? This app's browser is limited to people with a higher role.)"

// explainBrowser adds browserSignInHint to a 403 from a browsers route.
func explainBrowser(err error) error {
	var e *onemind.Error
	if errors.As(err, &e) && e.Status == http.StatusForbidden {
		return fmt.Errorf("%w\n%s", err, browserSignInHint)
	}
	return err
}

func browsersCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "browsers", Short: "Your own browser window on the box (needs a dashboard or phone sign-in; an API token is refused)"}
	root.AddCommand(&cobra.Command{
		Use:   "open APP_ID",
		Short: "Start your browser and print its address (POST /v1/browsers/ID/session)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodPost, "/v1/browsers/"+pathID(args[0])+"/session", nil)
			if err != nil {
				return explainBrowser(err)
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			m := obj(v)
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, str(m["url"]))
				return nil
			}
			fmt.Fprintf(a.Stdout, "Your browser is %s.\nOpen: %s\n", str(m["state"]), str(m["url"]))
			if pw := str(m["password"]); pw != "" {
				fmt.Fprintf(a.Stdout, "Its own sign-in password, shown now: %s\n", pw)
			}
			return nil
		},
	})
	root.AddCommand(&cobra.Command{
		Use:   "close APP_ID",
		Short: "Stop your browser; your profile is kept (POST /v1/browsers/ID/session/close)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodPost, "/v1/browsers/"+pathID(args[0])+"/session/close", nil)
			if err != nil {
				return explainBrowser(err)
			}
			return a.printDone(v, "Your browser in %s is stopped. Your profile is kept.", args[0])
		},
	})
	root.AddCommand(&cobra.Command{
		Use:   "reset-profile APP_ID",
		Short: "Request erasing your browser profile (POST /v1/browsers/ID/profile/reset); an owner approves",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return explainBrowser(a.requestWrite("erasing your browser profile in "+args[0], http.MethodPost, "/v1/browsers/"+pathID(args[0])+"/profile/reset", nil))
		},
	})
	return []*cobra.Command{root}
}

func init() { groups = append(groups, browsersCommands) }
