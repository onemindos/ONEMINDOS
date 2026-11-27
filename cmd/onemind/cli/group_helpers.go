// SPDX-License-Identifier: Apache-2.0

package cli

// Small helpers shared by the command groups that wrap one gateway route each (tokens, secrets,
// family, plugins, files, photos, automation, alerts, ...). Nothing here approves anything: a write
// either FILES a request that an owner approves (printRequested) or is a direct call the gateway
// already restricts to the right person and audits, so the CLI holds no power of its own.

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// dayAhead is how long a filed request stays open: a day, as the dashboard files them.
const dayAhead = 24 * time.Hour

func expiry() string { return time.Now().UTC().Add(dayAhead).Format(time.RFC3339) }

// pathID escapes one id for a URL path.
func pathID(s string) string { return url.PathEscape(s) }

// query builds a "?a=b&c=d" string from non-empty pairs ("" when none).
func query(pairs ...string) string {
	q := url.Values{}
	for i := 0; i+1 < len(pairs); i += 2 {
		if pairs[i+1] != "" {
			q.Set(pairs[i], pairs[i+1])
		}
	}
	if len(q) == 0 {
		return ""
	}
	return "?" + q.Encode()
}

// readJSONInput reads a JSON object from a file, or from stdin when path is "-".
func (a *App) readJSONInput(cmd *cobra.Command, path string) (map[string]any, error) {
	if path == "" {
		return nil, usageErr(cmd, "--file is required (a JSON file, or - for standard input)")
	}
	var raw []byte
	var err error
	if path == "-" {
		raw, err = io.ReadAll(io.LimitReader(a.Stdin, 1<<20))
	} else {
		raw, err = os.ReadFile(path)
	}
	if err != nil {
		return nil, exitWith(ExitUsage, "usage", "cannot read "+path+": "+err.Error())
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil || m == nil {
		return nil, exitWith(ExitUsage, "usage", "the input is not a JSON object")
	}
	return m, nil
}

// printDone prints the gateway's JSON for --json, else the one-line message.
func (a *App) printDone(v any, format string, args ...any) error {
	if a.G.JSON {
		return printJSON(a.Stdout, v)
	}
	if !a.G.Quiet {
		fmt.Fprintf(a.Stdout, format+"\n", args...)
	}
	return nil
}

// requireYes refuses a removal that was not confirmed.
func requireYes(cmd *cobra.Command, yes bool, what string) error {
	if yes {
		return nil
	}
	return usageErr(cmd, what+": repeat with --yes to confirm")
}

// joinStrs renders a JSON array of strings as "a, b" ("-" when empty).
func joinStrs(v any, max int) string {
	var out []string
	for _, x := range list(v) {
		out = append(out, str(x))
	}
	s := strings.Join(out, ", ")
	if max > 0 && len(s) > max {
		s = s[:max-1] + "…"
	}
	return dash(s)
}

// num renders a JSON number as a plain integer ("-" when absent).
func jnum(v any) string {
	f, ok := v.(float64)
	if !ok {
		return "-"
	}
	return fmt.Sprintf("%d", int64(f))
}

// getTable is the common read: GET path, then --json prints the gateway's JSON, else a table.
func (a *App) getTable(path, header string, row func(m map[string]any) []string) error {
	return a.read(path, func(w io.Writer, v any) error {
		var rows [][]string
		for _, x := range list(v) {
			rows = append(rows, row(obj(x)))
		}
		if len(rows) == 0 {
			fmt.Fprintln(w, "Nothing here yet.")
			return nil
		}
		return table(w, header, rows)
	})
}

// requestWrite files a request through a route that answers 202 with the waiting action.
func (a *App) requestWrite(what, method, path string, body any) error {
	v, err := a.gwDoKeyed(method, path, freshKey(), body)
	if err != nil {
		return err
	}
	return a.printRequested(what, v)
}

var _ = http.MethodGet
