// SPDX-License-Identifier: Apache-2.0

package cli

// onemind files: your files and who else may reach them (GET /v1/files/*, PUT /v1/files/quotas/{id},
// POST /v1/files/grants, POST /v1/files/trash/empty, DELETE /v1/files/grants/{id}). Browsing is
// read-only. Folder grants, permanent trash deletion, person-initiated renames and share-link
// changes file requests for an owner to approve in the Files dashboard. Agents can rename inside
// an owner-approved read-write folder grant.

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/spf13/cobra"
)

func filesCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "files", Short: "Your files: browse, quotas, folder grants for apps and agents (changes wait for an owner)"}

	root.AddCommand(&cobra.Command{
		Use:   "roots",
		Short: "The spaces you can open: your files, shared, and what you were given (GET /v1/files/roots)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/files/roots", "ROOT\tNAME\tACCESS\tUSED\tLIMIT\tFREE", func(m map[string]any) []string {
				return []string{str(m["root"]), str(m["name"]), str(m["access"]), jbytes(m["used_bytes"]), jbytes(m["quota_bytes"]), jbytes(m["free_bytes"])}
			})
		},
	})

	var rootID string
	var limit int
	ls := &cobra.Command{
		Use:   "list [PATH] --root ROOT",
		Short: "What is in a folder (GET /v1/files/list); ROOT comes from `onemind files roots`",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if rootID == "" {
				return usageErr(cmd, "--root is required: see `onemind files roots`")
			}
			p := "/"
			if len(args) == 1 {
				p = args[0]
			}
			return a.getTable("/v1/files/list"+query("root", rootID, "path", p, "limit", strconv.Itoa(limit)), "NAME\tTYPE\tSIZE\tMODIFIED", func(m map[string]any) []string {
				return []string{str(m["name"]), str(m["type"]), jbytes(m["size"]), dash(str(m["mtime"]))}
			})
		},
	}
	ls.Flags().StringVar(&rootID, "root", "", "the space to look in")
	ls.Flags().IntVar(&limit, "limit", 100, "entries per page (1 to 500); every page is fetched")

	var sRoot string
	stat := &cobra.Command{
		Use:   "stat PATH --root ROOT",
		Short: "One file or folder (GET /v1/files/stat)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if sRoot == "" {
				return usageErr(cmd, "--root is required: see `onemind files roots`")
			}
			return a.read("/v1/files/stat"+query("root", sRoot, "path", args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				return kv(w, [][2]string{{"path", str(m["path"])}, {"type", str(m["type"])}, {"size", jbytes(m["size"])}, {"modified", dash(str(m["mtime"]))}, {"kind", dash(str(m["mime"]))}})
			})
		},
	}
	stat.Flags().StringVar(&sRoot, "root", "", "the space the path is in")

	trash := &cobra.Command{Use: "trash", Short: "The trash: what is in it, request emptying it"}
	var which string
	trash.PersistentFlags().StringVar(&which, "trash", "home", "home or shared")
	trash.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "What is in the trash and when it is gone for good (GET /v1/files/trash)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/files/trash"+query("trash", which), "ID\tNAME\tSIZE\tTRASHED\tGONE ON", func(m map[string]any) []string {
				return []string{str(m["id"]), str(m["name"]), jbytes(m["size"]), str(m["trashed_at"]), str(m["purge_at"])}
			})
		},
	})
	var tReason string
	empty := &cobra.Command{
		Use:   "empty",
		Short: "Request emptying the trash for good (POST /v1/files/trash/empty); an owner approves",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			body := map[string]any{"trash": which}
			if tReason != "" {
				body["reason"] = tReason
			}
			return a.requestFiles("emptying the "+which+" trash", "/v1/files/trash/empty", body)
		},
	}
	empty.Flags().StringVar(&tReason, "reason", "", "why, shown to the owner")
	trash.AddCommand(empty)

	quotas := &cobra.Command{Use: "quotas", Short: "How much space each person may use (owner only)"}
	quotas.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Each person's limit and use (GET /v1/files/quotas)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/files/quotas", "PERSON\tROOT\tUSED\tLIMIT", func(m map[string]any) []string {
				who := str(m["person_id"])
				if who == "" {
					who = "(shared)"
				}
				lim := "no limit"
				if m["limit_bytes"] != nil {
					lim = jbytes(m["limit_bytes"])
				}
				return []string{who, str(m["root"]), jbytes(m["used_bytes"]), lim}
			})
		},
	})
	var gb float64
	var unlimited bool
	qset := &cobra.Command{
		Use:   "set PERSON_ID (--gb N | --unlimited)",
		Short: "Set a person's space limit (PUT /v1/files/quotas/ID); owner only",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if unlimited == (gb > 0) {
				return usageErr(cmd, "give exactly one of --gb N (more than 0) or --unlimited")
			}
			var lim any
			if !unlimited {
				lim = int64(gb * 1e9)
			}
			v, err := a.gwDo(http.MethodPut, "/v1/files/quotas/"+pathID(args[0]), map[string]any{"limit_bytes": lim})
			if err != nil {
				return err
			}
			return a.printDone(v, "Saved the space limit for %s.", args[0])
		},
	}
	qset.Flags().Float64Var(&gb, "gb", 0, "limit in gigabytes")
	qset.Flags().BoolVar(&unlimited, "unlimited", false, "remove the limit")
	quotas.AddCommand(qset)

	var rnRoot string
	rename := &cobra.Command{
		Use:   "rename PATH NEW_NAME --root ROOT",
		Short: "Request a new name for a file or folder (POST /v1/files/ops)",
		Args:  cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			if rnRoot == "" {
				return usageErr(cmd, "--root is required: see `onemind files roots`")
			}
			if strings.TrimSpace(args[1]) == "" {
				return usageErr(cmd, "NEW_NAME must not be empty")
			}
			if strings.Contains(args[1], "/") {
				return usageErr(cmd, "NEW_NAME is a name, not a path: use no \"/\"")
			}
			v, err := a.gwDo(http.MethodPost, "/v1/files/ops", map[string]any{"op": "rename", "root": rnRoot, "path": args[0], "name": args[1]})
			if err != nil {
				return err
			}
			if str(obj(v)["state"]) == "awaiting_approval" {
				return a.printFileRequest("rename "+args[0], v)
			}
			return a.printDone(v, "Renamed %s to %s.", args[0], args[1])
		},
	}
	rename.Flags().StringVar(&rnRoot, "root", "", "the space the path is in")

	root.AddCommand(ls, stat, rename, trash, quotas, filesGrantsCmd(a), filesRequestsCmd(a), filesShareCmd(a))
	return []*cobra.Command{root}
}

// The gateway accepts a share expiry 5m to 720h ahead of its own clock; the CLI keeps one minute off
// each end so latency and a skewed clock never turn a valid choice into a 422.
const (
	shareMinTTL = 6 * time.Minute
	shareMaxTTL = 719 * time.Hour
)

func filesShareCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "share", Short: "Links that let someone without an account download your files"}
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your share links, without their secrets (GET /v1/files/shares); an owner sees everyone's",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/files/shares", "ID\tNAME\tSTATE\tITEMS\tOPENED\tEXPIRES", func(m map[string]any) []string {
				return []string{str(m["id"]), str(m["name"]), str(m["state"]), strconv.Itoa(len(list(m["items"]))), fmt.Sprint(m["opened_count"]), str(m["expires_at"])}
			})
		},
	})
	var root, name string
	var fromStdin bool
	var expires time.Duration
	create := &cobra.Command{
		Use:   "create PATH... --root ROOT [--expires-in 168h] [--name NAME] [--password-stdin]",
		Short: "Request a link to files (POST /v1/files/shares); the secret link is shown once",
		Args:  cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if root == "" {
				return usageErr(cmd, "--root is required: see `onemind files roots`")
			}
			// The gateway wants 5m to 720h counted from ITS clock when the call arrives, so keep a margin
			// at both ends for latency and clock skew.
			if expires < shareMinTTL || expires > shareMaxTTL {
				return usageErr(cmd, "--expires-in must be between 6m and 719h")
			}
			items := make([]any, 0, len(args))
			for _, p := range args {
				items = append(items, map[string]any{"root": root, "path": p})
			}
			body := map[string]any{"items": items, "expires_at": time.Now().UTC().Add(expires).Format(time.RFC3339)}
			if name != "" {
				body["name"] = name
			}
			if fromStdin {
				got, err := a.secrets(true, "Link password")
				if err != nil {
					return err
				}
				if n := utf8.RuneCountInString(got[0]); n < 8 || n > 200 { // characters, as the gateway counts them
					return usageErr(cmd, "the link password needs 8 to 200 characters")
				}
				body["password"] = got[0]
			}
			// No Idempotency-Key and no retry: a retry could file a second request.
			v, err := a.gwDo(http.MethodPost, "/v1/files/shares", body)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			url := str(obj(obj(v)["one_time"])["url"])
			if a.G.Quiet {
				fmt.Fprintln(a.Stdout, url)
				return nil
			}
			fmt.Fprintf(a.Stdout, "Request %s is waiting for owner approval in the Files dashboard (Sharing).\nLink (shown only now): %s\nRecipients use an API client. Protected links require the OneMind-Share-Password header.\n", str(obj(v)["id"]), url)
			return nil
		},
	}
	create.Flags().StringVar(&root, "root", "", "the space the paths are in")
	create.Flags().DurationVar(&expires, "expires-in", 7*24*time.Hour, "how long the link works (6m to 719h)")
	create.Flags().StringVar(&name, "name", "", "a label for the link")
	create.Flags().BoolVar(&fromStdin, "password-stdin", false, "ask for a password on the link, read from the first line of stdin (at least 8 characters)")
	var yes bool
	rev := &cobra.Command{
		Use:   "revoke SHARE_ID --yes",
		Short: "Request to end a link (DELETE /v1/files/shares/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, yes, "the link stops working for everyone after the owner approves"); err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodDelete, "/v1/files/shares/"+pathID(args[0]), nil)
			if err != nil {
				return err
			}
			return a.printFileRequest("end share link "+args[0], v)
		},
	}
	rev.Flags().BoolVar(&yes, "yes", false, "confirm")
	g.AddCommand(create, rev)
	return g
}

func filesGrantsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "grants", Short: "Folders an app or an AI agent was given"}
	var revoked bool
	g.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Who may reach which folder (GET /v1/files/grants)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			path := "/v1/files/grants"
			if revoked {
				path += "?include_revoked=true"
			}
			return a.getTable(path, "ID\tWHO\tFOLDER\tACCESS\tSTATE", func(m map[string]any) []string {
				s := obj(m["subject"])
				state := "active"
				if str(m["revoked_at"]) != "" {
					state = "revoked"
				}
				return []string{str(m["id"]), str(s["kind"]) + ":" + str(s["id"]), str(m["root"]) + str(m["path"]), str(m["access"]), state}
			})
		},
	})
	g.Commands()[0].Flags().BoolVar(&revoked, "all", false, "include revoked grants")

	var kind, subject, root, path, access, reason string
	req := &cobra.Command{
		Use:   "request --for app|agent:ID --root ROOT --path /folder --access r|rw",
		Short: "Request giving an app or agent a folder (POST /v1/files/grants); an owner approves",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if subject == "" || root == "" || path == "" || (access != "r" && access != "rw") {
				return usageErr(cmd, "--for, --root, --path and --access (r or rw) are required")
			}
			kind = "app"
			id := subject
			if len(subject) > 6 && subject[:6] == "agent:" {
				kind, id = "agent", subject
			}
			body := map[string]any{"subject": map[string]any{"kind": kind, "id": id}, "root": root, "path": path, "access": access}
			if reason != "" {
				body["reason"] = reason
			}
			return a.requestFiles("folder access for "+subject, "/v1/files/grants", body)
		},
	}
	req.Flags().StringVar(&subject, "for", "", "an app id, or agent:NAME")
	req.Flags().StringVar(&root, "root", "", "the space (see `onemind files roots`)")
	req.Flags().StringVar(&path, "path", "", "the folder")
	req.Flags().StringVar(&access, "access", "", "r (read) or rw (read and write)")
	req.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")

	var yes bool
	rev := &cobra.Command{
		Use:   "revoke GRANT_ID --yes",
		Short: "Take a folder back now (DELETE /v1/files/grants/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := requireYes(cmd, yes, "revoking "+args[0]+" stops that access to the folder"); err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodDelete, "/v1/files/grants/"+pathID(args[0]), nil)
			if err != nil {
				return err
			}
			return a.printDone(v, "Revoked %s.", args[0])
		},
	}
	rev.Flags().BoolVar(&yes, "yes", false, "confirm")
	g.AddCommand(req, rev)
	return g
}

func filesRequestsCmd(a *App) *cobra.Command {
	g := &cobra.Command{Use: "requests", Short: "Folder and trash requests waiting for, or past, an owner's decision"}
	var state string
	lst := &cobra.Command{
		Use:   "list",
		Short: "Requests (GET /v1/files/requests); an owner sees everyone's",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.getTable("/v1/files/requests"+query("state", state), "ID\tTYPE\tSTATE\tBY\tEXPIRES", func(m map[string]any) []string {
				return []string{str(m["id"]), str(m["type"]), str(m["state"]), dash(str(m["requested_by"])), dash(str(m["expires_at"]))}
			})
		},
	}
	lst.Flags().StringVar(&state, "state", "", "only these states, comma separated")
	g.AddCommand(lst, &cobra.Command{
		Use:   "show REQUEST_ID",
		Short: "One request and its plan (GET /v1/files/requests/ID)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/files/requests/"+pathID(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				if err := kv(w, [][2]string{{"id", str(m["id"])}, {"type", str(m["type"])}, {"state", str(m["state"])}, {"risk", dash(str(m["risk"]))},
					{"requested by", dash(str(m["requested_by"]))}, {"reason", dash(str(m["reason"]))}, {"expires", dash(str(m["expires_at"]))}}); err != nil {
					return err
				}
				fmt.Fprintln(w, "\nAn owner decides this in the dashboard (Files, Requests).")
				return nil
			})
		},
	})
	return g
}

// requestFiles files a request that lives in the Files area (not the action queue): an owner decides it
// in the dashboard's Files requests, so the hint names that place and not `onemind actions`. The key is
// stable for the same ask on the same day, so asking twice replays the waiting request.
func (a *App) requestFiles(what, path string, body map[string]any) error {
	raw, _ := json.Marshal(body)
	v, err := a.gwDoKeyed(http.MethodPost, path, idemKey("cli-files-", path, string(raw)), body)
	if err != nil {
		return err
	}
	return a.printFileRequest(what, v)
}

func (a *App) printFileRequest(what string, v any) error {
	id := str(obj(v)["id"])
	state := str(obj(v)["state"])
	if a.G.JSON {
		if err := printJSON(a.Stdout, v); err != nil {
			return err
		}
	} else if a.G.Quiet {
		fmt.Fprintln(a.Stdout, id)
	}
	// A keyed request can replay an earlier decision, without filing a new request.
	if state != "" && state != "awaiting_approval" {
		return exitWith(ExitConflict, "conflict", fmt.Sprintf("%s: already %s today, nothing new filed (%s). Ask again tomorrow, or see `onemind files requests show %s`", what, state, id, id))
	}
	if a.G.JSON || a.G.Quiet {
		return nil
	}
	fmt.Fprintf(a.Stdout, "Requested %s (%s, %s). An owner decides it in the dashboard (Files → Sharing → Requests); see it with: onemind files requests show %s\n",
		what, id, dash(state), id)
	return nil
}

func init() { groups = append(groups, filesCommands) }
