// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"
)

// notifyChannel is the part of a channel (GET /v1/notifications/channels) the CLI prints. The
// gateway never returns a channel's credential, only "provided".
type notifyChannel struct {
	ID           string         `json:"id"`
	Kind         string         `json:"kind"`
	Label        string         `json:"label"`
	ContentLevel string         `json:"content_level"`
	Config       map[string]any `json:"config"`
	Verified     bool           `json:"verified"`
	State        string         `json:"state"`
	Secret       *string        `json:"secret"`
}

type notifyTestResult struct {
	Delivered bool           `json:"delivered"`
	LatencyMS int            `json:"latency_ms"`
	Error     string         `json:"error,omitempty"`
	Receipt   map[string]any `json:"receipt,omitempty"`
}

// notifyCommands is `onemind notify`: the caller's own alert channels (contract §12.14). It covers
// the SMS channel of issue #869: add one (`notify channel add sms`), list them, and send a test
// (`notify test sms`). The provider credential is typed by the person, read without echo or from
// stdin, and sent once to the gateway, which seals it; it is never a flag (shell history).
func notifyCommands(a *App) []*cobra.Command {
	g := &cobra.Command{Use: "notify", Short: "Your alerts: channels (add SMS, list, test), delivery settings, and which senders to mute"}
	ch := &cobra.Command{Use: "channel", Short: "Your alert channels (GET/POST /v1/notifications/channels)"}
	ch.AddCommand(&cobra.Command{
		Use:   "list",
		Short: "Your channels: id, kind, label, state, daily cap",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			list, err := listChannels(a)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, list)
			}
			return table(a.Stdout, "ID\tKIND\tLABEL\tSTATE\tVERIFIED\tDAILY CAP", ChannelRows(list))
		},
	})
	ch.AddCommand(addSmsCommand(a))
	g.AddCommand(ch, notifyPrefsCmd(a), notifySourcesCmd(a))

	var channelID string
	test := &cobra.Command{
		Use:   "test sms",
		Short: "Send one labelled test text and show the provider's receipt or its error",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if args[0] != "sms" {
				return exitWith(ExitUsage, "usage", fmt.Sprintf("unknown channel kind %q (only sms)", args[0]))
			}
			id := channelID
			if id == "" {
				list, err := listChannels(a)
				if err != nil {
					return err
				}
				var sms []string
				for _, c := range list {
					if c.Kind == "sms" {
						sms = append(sms, c.ID)
					}
				}
				switch len(sms) {
				case 0:
					return exitWith(ExitNotFound, "not_found", "no SMS channel: add one with `onemind notify channel add sms`")
				case 1:
					id = sms[0]
				default:
					return exitWith(ExitUsage, "usage", "you have several SMS channels: pass --channel ID")
				}
			}
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			var res notifyTestResult
			if err := cl.Do(bg(), http.MethodPost, "/v1/notifications/channels/"+url.PathEscape(id)+"/test", map[string]any{}, &res); err != nil {
				return err
			}
			if a.G.JSON {
				if err := printJSON(a.Stdout, res); err != nil {
					return err
				}
			} else if res.Delivered {
				fmt.Fprintf(a.Stdout, "sent: provider answered %v, receipt %s (%d ms)\n",
					res.Receipt["status"], dash(fmt.Sprint(orEmpty(res.Receipt["provider_id"]))), res.LatencyMS)
			}
			if !res.Delivered {
				return exitWith(ExitError, "delivery_failed", "test text not sent: "+sanitize(res.Error))
			}
			return nil
		},
	}
	test.Flags().StringVar(&channelID, "channel", "", "channel id, when you have more than one SMS channel")
	g.AddCommand(test)
	return []*cobra.Command{g}
}

func addSmsCommand(a *App) *cobra.Command {
	var label, to, provider, from, format, auth, username, minSeverity string
	var dailyCap, perHour int
	var secretStdin bool
	c := &cobra.Command{
		Use:   "add sms",
		Short: "Add an SMS channel: your number and your provider's HTTPS send URL",
		Long: "Adds an SMS alert channel through the provider-neutral HTTPS adapter. The text carries only the\n" +
			"alert's title and a short hint; the gateway counts a daily cap (default 20) and an hourly limit.\n" +
			"The provider token is asked for without echo, or read from stdin with --secret-stdin.",
		Example: "  onemind notify channel add sms --to +15550100123 --provider-url https://sms.example/v1/messages\n" +
			"  onemind notify channel add sms --to +15550100123 --provider-url URL --format form --auth basic --username ACCOUNT --field to=To --field text=Body",
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if args[0] != "sms" {
				return exitWith(ExitUsage, "usage", fmt.Sprintf("unknown channel kind %q (only sms)", args[0]))
			}
			if to == "" || provider == "" {
				return exitWith(ExitUsage, "usage", "--to and --provider-url are required")
			}
			fields, _ := cmd.Flags().GetStringToString("field")
			cfg := map[string]any{"url": provider, "to": to, "format": format, "auth": auth, "min_severity": minSeverity}
			if from != "" {
				cfg["from"] = from
			}
			if username != "" {
				cfg["username"] = username
			}
			if len(fields) > 0 {
				cfg["fields"] = fields
			}
			if dailyCap > 0 {
				cfg["daily_cap"] = dailyCap
			}
			if perHour > 0 {
				cfg["per_hour"] = perHour
			}
			body := map[string]any{"kind": "sms", "label": label, "config": cfg}
			if auth != "none" {
				secret, err := readProviderSecret(a, secretStdin)
				if err != nil {
					return err
				}
				if secret != "" {
					body["secret"] = secret
				}
			}
			cl, _, err := a.client()
			if err != nil {
				return err
			}
			var out notifyChannel
			if err := cl.Do(bg(), http.MethodPost, "/v1/notifications/channels", body, &out); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, out)
			}
			fmt.Fprintf(a.Stdout, "added %s (%s), daily cap %s; send a test with `onemind notify test sms`\n",
				out.ID, sanitize(out.Label), capOf(out))
			return nil
		},
	}
	f := c.Flags()
	f.StringVar(&label, "label", "SMS", "a name for this channel")
	f.StringVar(&to, "to", "", "your phone number in international form (+ and country code)")
	f.StringVar(&provider, "provider-url", "", "the provider's HTTPS send URL")
	f.StringVar(&from, "from", "", "sender number or name, when the provider needs one")
	f.StringVar(&format, "format", "json", "request body: json or form")
	f.StringVar(&auth, "auth", "bearer", "how the token is sent: bearer, basic or none")
	f.StringVar(&username, "username", "", "account name for --auth basic")
	f.StringToString("field", nil, "provider field names, like to=To,from=From,text=Body")
	f.IntVar(&dailyCap, "daily-cap", 0, "most texts in 24 hours, 1 to 500 (default 20)")
	f.IntVar(&perHour, "per-hour", 0, "most texts per hour before they are held and summarised (default 5)")
	f.StringVar(&minSeverity, "min-severity", "warning", "send alerts at this severity or above: info, warning, critical")
	f.BoolVar(&secretStdin, "secret-stdin", false, "read the provider token from stdin")
	return c
}

// readProviderSecret asks for the provider token without echo (a terminal) or reads one line
// from stdin (--secret-stdin). It is never printed.
func readProviderSecret(a *App, fromStdin bool) (string, error) {
	if fromStdin {
		if a.G.TokenStdin {
			return "", exitWith(ExitUsage, "usage", "--secret-stdin and --token-stdin both read stdin: set ONEMIND_TOKEN instead")
		}
		line, err := bufio.NewReader(a.Stdin).ReadString('\n')
		if err != nil && err != io.EOF {
			return "", err
		}
		if s := strings.TrimSpace(line); s != "" {
			return s, nil
		}
		return "", exitWith(ExitUsage, "usage", "--secret-stdin: nothing on stdin")
	}
	f, ok := a.Stdin.(*os.File)
	if !ok || !a.Interactive() {
		return "", exitWith(ExitUsage, "usage", "stdin is not a terminal: pass --secret-stdin, or --auth none")
	}
	fmt.Fprint(a.Stderr, "Provider token: ")
	raw, err := term.ReadPassword(int(f.Fd()))
	fmt.Fprintln(a.Stderr)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(raw)), nil
}

func listChannels(a *App) ([]notifyChannel, error) {
	cl, _, err := a.client()
	if err != nil {
		return nil, err
	}
	var list []notifyChannel
	if err := cl.Do(bg(), http.MethodGet, "/v1/notifications/channels", nil, &list); err != nil {
		return nil, err
	}
	return list, nil
}

// ChannelRows is the `notify channel list` table. Only per-channel caps show; "-" for kinds without one.
func ChannelRows(list []notifyChannel) [][]string {
	rows := [][]string{}
	for _, c := range list {
		verified := "no"
		if c.Verified {
			verified = "yes"
		}
		rows = append(rows, []string{c.ID, c.Kind, sanitize(c.Label), dash(c.State), verified, capOf(c)})
	}
	return rows
}

func capOf(c notifyChannel) string {
	if v, ok := c.Config["daily_cap"].(float64); ok {
		return strconv.Itoa(int(v)) + "/day"
	}
	return "-"
}

func orEmpty(v any) any {
	if v == nil {
		return ""
	}
	return v
}
