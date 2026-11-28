// SPDX-License-Identifier: Apache-2.0

package cli

// onemind photos and onemind onboarding.
//
// `photos` shows the library and the backup status of each phone (GET /v1/photos/library,
// /sources/{id}/coverage, /sources/{id}/receipts). Its settings command files owner approval requests.
// Registering a source and uploading are done by the phone app, which holds the originals.
//
// `onboarding` shows first-run progress and the first-run choices (GET /v1/onboarding/state,
// GET/PUT /v1/onboarding/settings). Saving the choices is an owner call the gateway audits.

import (
	"fmt"
	"io"
	"net/http"
	"strconv"

	"github.com/spf13/cobra"
)

func photosCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "photos", Short: "Your photo library, phone backup status and Photos settings"}
	var limit int
	var cursor string
	lib := &cobra.Command{
		Use:   "library",
		Short: "The photos and videos the box holds (GET /v1/photos/library)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/photos/library"+query("limit", strconv.Itoa(limit), "cursor", cursor), func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(obj(v)["items"]) {
					m := obj(x)
					rows = append(rows, []string{str(m["id"]), str(m["file_name"]), dash(str(m["taken_at"])), jbytes(m["size"]), photoLevel(str(m["level"]))})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "No photos on the box yet.")
					return nil
				}
				if err := table(w, "ID\tFILE\tTAKEN\tSIZE\tSAFETY", rows); err != nil {
					return err
				}
				if next := str(obj(v)["next_cursor"]); next != "" {
					fmt.Fprintf(w, "\nMore: onemind photos library --cursor %s\n", next)
				}
				return nil
			})
		},
	}
	lib.Flags().IntVar(&limit, "limit", 50, "at most this many photos")
	lib.Flags().StringVar(&cursor, "cursor", "", "continue from a previous page")

	root.AddCommand(lib, &cobra.Command{
		Use:   "coverage SOURCE_ID",
		Short: "How many of a phone's photos are on the box, in a backup, and in a verified backup (GET /v1/photos/sources/ID/coverage)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/photos/sources/"+pathID(args[0])+"/coverage", func(w io.Writer, v any) error {
				m := obj(v)
				return kv(w, [][2]string{{"photos in total", jnum(m["total"])}, {"on the box", jnum(m["on_box"])}, {"in a backup", jnum(m["backed_up"])},
					{"in a backup that was test-restored (safe to free on the phone)", jnum(m["verified"])}, {"as of", dash(str(m["as_of"]))}})
			})
		},
	})
	var rLimit int
	root.AddCommand(&cobra.Command{
		Use:   "receipts SOURCE_ID",
		Short: "What the box has received from a phone and how safe each is (GET /v1/photos/sources/ID/receipts)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/photos/sources/"+pathID(args[0])+"/receipts"+query("limit", strconv.Itoa(rLimit)), func(w io.Writer, v any) error {
				var rows [][]string
				for _, x := range list(obj(v)["items"]) {
					m := obj(x)
					rows = append(rows, []string{str(m["client_key"]), str(m["received_at"]), photoLevel(str(m["level"]))})
				}
				if len(rows) == 0 {
					fmt.Fprintln(w, "Nothing received from this source yet.")
					return nil
				}
				return table(w, "PHOTO\tRECEIVED\tSAFETY", rows)
			})
		},
	})
	root.Commands()[len(root.Commands())-1].Flags().IntVar(&rLimit, "limit", 50, "at most this many receipts")
	root.AddCommand(photosSettingsCommand(a))
	return []*cobra.Command{root}
}

// photoLevel says in words how safe one photo is.
func photoLevel(l string) string {
	switch l {
	case "on_box":
		return "on the box only"
	case "in_backup":
		return "in a backup"
	case "in_verified_backup":
		return "in a verified backup"
	}
	return dash(l)
}

func onboardingCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "onboarding", Short: "First-run set-up: what is done and the choices made (owner only)"}
	root.AddCommand(&cobra.Command{
		Use:   "state",
		Short: "How far first-run set-up got (GET /v1/onboarding/state)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/onboarding/state", func(w io.Writer, v any) error {
				m := obj(v)
				yes := func(b any) string {
					if b == true {
						return "yes"
					}
					return "no"
				}
				return kv(w, [][2]string{{"set-up complete", yes(m["complete"])}, {"choices saved", yes(m["settings_saved"])}, {"backups on", yes(m["backups_enabled"])},
					{"backup places", jnum(m["destinations"])}, {"emergency kit", dash(str(obj(m["kit"])["state"]))}})
			})
		},
	})
	settings := &cobra.Command{Use: "settings", Short: "The first-run choices: box name, time zone, backup place"}
	settings.AddCommand(&cobra.Command{
		Use:   "show",
		Short: "The saved choices (GET /v1/onboarding/settings)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/onboarding/settings", func(w io.Writer, v any) error {
				m := obj(v)
				saved := "no"
				if m["saved"] == true {
					saved = "yes"
				}
				return kv(w, [][2]string{{"saved", saved}, {"box name", dash(str(m["box_name"]))}, {"time zone", dash(str(m["time_zone"]))},
					{"backup choice", dash(str(m["backup_choice"]))}, {"backup place", dash(str(m["backup_destination_id"]))}})
			})
		},
	})
	var name, tz, choice, dest string
	save := &cobra.Command{
		Use:   "save --name NAME --time-zone ZONE --backup usb|peer|s3|later [--destination ID]",
		Short: "Save the first-run choices (PUT /v1/onboarding/settings); owner only",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if name == "" || tz == "" || choice == "" {
				return usageErr(cmd, "--name, --time-zone and --backup are required")
			}
			body := map[string]any{"box_name": name, "time_zone": tz, "backup_choice": choice}
			if dest != "" {
				body["backup_destination_id"] = dest
			}
			v, err := a.gwDo(http.MethodPut, "/v1/onboarding/settings", body)
			if err != nil {
				return err
			}
			return a.printDone(v, "Saved the first-run choices for %s.", name)
		},
	}
	save.Flags().StringVar(&name, "name", "", "the box's name: lower-case letters, digits and dashes")
	save.Flags().StringVar(&tz, "time-zone", "", "an IANA time zone, e.g. America/New_York")
	save.Flags().StringVar(&choice, "backup", "", "usb, peer, s3 or later")
	save.Flags().StringVar(&dest, "destination", "", "an existing backup place matching the choice")
	settings.AddCommand(save)
	root.AddCommand(settings)
	return []*cobra.Command{root}
}

func init() { groups = append(groups, photosCommands, onboardingCommands) }
