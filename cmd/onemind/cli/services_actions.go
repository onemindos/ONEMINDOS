// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
)

// serviceActionCommands are `onemind services logs` and `onemind services restart` (#636).
//
// logs reads GET /v1/system/services/{unit}/logs: the gateway redacts every line before it leaves the
// box, and this side strips terminal control characters. restart files a service.restart action
// (POST /v1/system/services/{unit}/restart) and prints its id: an owner approves it with a passkey in the
// dashboard or the phone app. The CLI never approves it, so an agent's token can ask but not run it.
func serviceActionCommands(a *App) []*cobra.Command {
	var follow bool
	var tail int
	logs := &cobra.Command{
		Use:   "logs UNIT",
		Short: "A service's journal, redacted by the hub; -f follows new lines (owner)",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			if tail < 1 || tail > 2000 {
				return exitWith(ExitUsage, "usage", "--tail must be 1-2000")
			}
			return a.serviceLogs(args[0], tail, follow)
		},
	}
	logs.Flags().BoolVarP(&follow, "follow", "f", false, "keep printing new lines (at most 15 minutes; Ctrl-C stops)")
	logs.Flags().IntVarP(&tail, "tail", "n", 200, "how many recent lines (1-2000)")

	var reason string
	restart := &cobra.Command{
		Use:   "restart UNIT",
		Short: "Ask for a service restart; prints the approval id an owner approves with a passkey",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			body := map[string]any{"idempotency_key": "cli-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
			if reason != "" {
				body["reason"] = reason
			}
			var act map[string]any
			if err := c.Do(bg(), http.MethodPost, "/v1/system/services/"+url.PathEscape(args[0])+"/restart", body, &act); err != nil {
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
			fmt.Fprintf(a.Stdout, "Restart of %s requested. Approval id: %s\nAn owner approves it with a passkey (dashboard or phone app); follow it with: onemind actions info %s\n",
				sanitize(args[0]), sanitize(id), sanitize(id))
			return nil
		},
	}
	restart.Flags().StringVar(&reason, "reason", "", "why, shown to the owner on the approval card")
	return []*cobra.Command{logs, restart}
}

// serviceLogs streams the logs to stdout. Follow reads the hub's server-sent events (data: lines).
func (a *App) serviceLogs(unit string, tail int, follow bool) error {
	q := url.Values{"tail": {strconv.Itoa(tail)}}
	return a.streamLogs("/v1/system/services/"+url.PathEscape(unit)+"/logs", q, "services logs", follow)
}

// streamLogs prints a hub log endpoint (plain text, or server-sent events with follow) to stdout, with
// terminal control characters removed. Shared by `services logs` and `logs` (P-07).
func (a *App) streamLogs(path string, q url.Values, what string, follow bool) error {
	t, err := a.resolve()
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if !follow {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, a.G.Timeout+30*time.Second)
		defer cancel()
	}
	if follow {
		q.Set("follow", "true")
	}
	u := strings.TrimRight(t.hub, "/") + path + "?" + q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return exitWith(ExitUsage, "usage", err.Error())
	}
	if t.token != "" {
		req.Header.Set("Authorization", "Bearer "+t.token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil // Ctrl-C
		}
		return exitWith(ExitUnreachable, "network", "the hub could not be reached")
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return logsError(resp, what)
	}
	sc := bufio.NewScanner(resp.Body)
	sc.Buffer(make([]byte, 64<<10), 64<<10)
	for sc.Scan() {
		line := sc.Text()
		if follow {
			if strings.HasPrefix(line, "event: end") {
				break
			}
			var ok bool
			if line, ok = strings.CutPrefix(line, "data: "); !ok {
				continue
			}
		}
		fmt.Fprintln(a.Stdout, sanitize(line))
	}
	if err := sc.Err(); err != nil && ctx.Err() == nil {
		return exitWith(ExitUnreachable, "network", "the log stream broke off")
	}
	return nil
}

func logsError(resp *http.Response, what string) error {
	var ge struct{ Error, Message, Reason string }
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 16<<10))
	_ = json.Unmarshal(raw, &ge)
	msg := sanitize(ge.Message)
	if msg == "" {
		msg = fmt.Sprintf("the hub answered HTTP %d", resp.StatusCode)
	}
	code := map[int]int{401: ExitUnauthenticated, 403: ExitPermissionDenied, 404: ExitNotFound, 409: ExitConflict,
		429: ExitTooManyRequests}[resp.StatusCode]
	if code == 0 {
		code = ExitError
	}
	name := ge.Error
	if name == "" {
		name = "error"
	}
	return exitWith(code, name, what+": "+msg)
}
