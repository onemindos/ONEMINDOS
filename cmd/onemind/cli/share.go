// SPDX-License-Identifier: Apache-2.0

package cli

// onemind share: the "Send to" list and handing one object to one app (/v1/share/*). `types` and `targets` only read.
// `send` hands over a reference to an object, never its content; the gateway refuses an app that does not accept the
// type, is off, or lacks the data grant it needs, and only an owner or an adult may send. Not to be confused with
// `onemind shares`, which is about network shares (SMB) and file links.

import (
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
)

func shareCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "share", Short: "Send an object (a file, note, place...) to an app that accepts it"}
	root.AddCommand(&cobra.Command{
		Use:   "types",
		Short: "What can be sent, and the data grant a receiving app needs (GET /v1/share/types)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/share/types", func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, t := range list(obj(v)["types"]) {
					m := obj(t)
					rows = append(rows, []string{str(m["name"]), str(m["title"]), str(m["data_class"]), str(m["ref"])})
				}
				return table(w, "TYPE\tTITLE\tGRANT\tREF IS", rows)
			})
		},
	})
	root.AddCommand(&cobra.Command{
		Use:   "targets TYPE",
		Short: "The apps that accept this type: the Send to list (GET /v1/share/targets)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/share/targets?"+url.Values{"type": {args[0]}}.Encode(), func(w io.Writer, v any) error {
				rows := [][]string{}
				for _, t := range list(obj(v)["targets"]) {
					m := obj(t)
					verbs := []string{}
					for _, x := range list(m["verbs"]) {
						verbs = append(verbs, str(x))
					}
					rows = append(rows, []string{str(m["app_id"]), str(m["name"]), strings.Join(verbs, ", ")})
				}
				return table(w, "APP\tNAME\tVERBS", rows)
			})
		},
	})
	var to, typ, ref, source, verb string
	send := &cobra.Command{
		Use:   "send --to APP --type TYPE --ref REF [--verb open|add]",
		Short: "Hand one object to one app (POST /v1/share): a reference, never the content",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if to == "" || typ == "" || ref == "" {
				return usageErr(cmd, "--to, --type and --ref are required (see `onemind share targets TYPE`)")
			}
			if verb != "open" && verb != "add" {
				return usageErr(cmd, "--verb must be open or add")
			}
			object := map[string]any{"type": typ, "ref": ref}
			if source != "" {
				object["source"] = source
			}
			// Stable per (app, verb, type, ref, day): sending the same thing twice replays the first share.
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/share", idemKey("cli-share-", to, verb, typ, ref), map[string]any{"to": to, "verb": verb, "object": object})
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				m := obj(v)
				return kv(w, [][2]string{{"sent to", sanitize(str(m["to"]))}, {"as", sanitize(str(m["verb"]))}, {"link", sanitize(str(m["link"]))}})
			})
		},
	}
	send.Flags().StringVar(&to, "to", "", "the receiving app's id")
	send.Flags().StringVar(&typ, "type", "", "note, task, event, person, file, place, track, alert or clip")
	send.Flags().StringVar(&ref, "ref", "", "what names the object (for a file: ROOT:PATH, for example home:alex:/notes.txt)")
	send.Flags().StringVar(&source, "source", "", "the app the object comes from (optional)")
	send.Flags().StringVar(&verb, "verb", "open", "open or add")
	root.AddCommand(send)
	return []*cobra.Command{root}
}
