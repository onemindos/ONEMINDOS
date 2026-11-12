// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"fmt"
	"io"
	"regexp"
	"strings"
	"text/tabwriter"
	"time"
)

func dash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func printJSON(out io.Writer, v any) error {
	enc := json.NewEncoder(out)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

// printNDJSON prints one compact JSON object per line (watch, tail).
func printNDJSON(out io.Writer, v any) error {
	return json.NewEncoder(out).Encode(v)
}

func mustJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}

// Terminal control sequences, C0/C1 controls (except tab and newline) and bidi overrides: an
// agent-written string must not be able to hide text or rewrite the screen (CLI.md §6.4).
var unsafeText = regexp.MustCompile(`\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)?|[\x00-\x08\x0b-\x1f\x7f-\x{9f}\x{202a}-\x{202e}\x{2066}-\x{2069}\x{200e}\x{200f}\x{061c}]`)

func sanitize(s string) string { return unsafeText.ReplaceAllString(s, "") }

func table(out io.Writer, header string, rows [][]string) error {
	tw := tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	fmt.Fprintln(tw, header)
	for _, r := range rows {
		for i := range r {
			r[i] = sanitize(r[i])
		}
		fmt.Fprintln(tw, strings.Join(r, "\t"))
	}
	return tw.Flush()
}

func kv(out io.Writer, pairs [][2]string) error {
	tw := tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	for _, p := range pairs {
		fmt.Fprintf(tw, "%s\t%s\n", p[0], sanitize(p[1]))
	}
	return tw.Flush()
}

// untrustedBlock prints third-party text (an agent's reason) quoted and labelled.
func untrustedBlock(out io.Writer, label, text string) {
	fmt.Fprintf(out, "%s (untrusted, not checked by OneMind):\n", label)
	for _, line := range strings.Split(sanitize(text), "\n") {
		fmt.Fprintf(out, "  │ %s\n", line)
	}
}

// age renders "3m", "2h", "5d" since an RFC 3339 time; in renders "in 23h".
func age(ts string, now time.Time) string {
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return "-"
	}
	return short(now.Sub(t))
}

func in(ts string, now time.Time) string {
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return "-"
	}
	d := t.Sub(now)
	if d < 0 {
		return short(-d) + " ago"
	}
	return "in " + short(d)
}

func short(d time.Duration) string {
	switch {
	case d < time.Minute:
		return fmt.Sprintf("%ds", int(d.Seconds()))
	case d < time.Hour:
		return fmt.Sprintf("%dm", int(d.Minutes()))
	case d < 48*time.Hour:
		return fmt.Sprintf("%dh", int(d.Hours()))
	}
	return fmt.Sprintf("%dd", int(d.Hours()/24))
}
