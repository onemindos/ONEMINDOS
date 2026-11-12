// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/mcpbridge"
)

// mcpCommands is `onemind mcp` (docs/leap/dev/MCP.md §7): the stdio bridge Claude Code, Claude
// Desktop and other MCP hosts start, plus login, doctor and config helpers.
func mcpCommands(a *App) []*cobra.Command {
	mcp := &cobra.Command{
		Use:   "mcp",
		Short: "Stdio MCP server that bridges to the box's /mcp with an agent token",
		Long: "Reads JSON-RPC lines on stdin, forwards each to POST <hub>/mcp with the agent token of the context\n" +
			"(or ONEMIND_TOKEN), and writes answers on stdout. All checks stay in the gateway: an agent can read\n" +
			"and request, never approve. Logs go to stderr without the token or message bodies.",
		Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			t, err := a.resolve()
			if err != nil {
				return err
			}
			ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
			defer stop()
			b := mcpbridge.New(mcpbridge.Config{Hub: t.hub, Token: t.token, Log: func(f string, args ...any) {
				if a.G.Verbose || strings.Contains(f, "onemind mcp doctor") {
					fmt.Fprintf(a.Stderr, f+"\n", args...)
				}
			}})
			if err := b.Run(ctx, a.Stdin, a.Stdout); err != nil && ctx.Err() == nil {
				return err
			}
			return nil
		},
	}
	var name string
	login := &cobra.Command{
		Use:   "login",
		Short: "Save an agent token (personal agent, F-15) as a context, after checking it is an agent's",
		Args:  cobra.NoArgs,
		RunE:  func(*cobra.Command, []string) error { return a.login(name, "", true) },
	}
	login.Flags().StringVar(&name, "name", "", "context name (default: from the hub's host name)")
	doctor := &cobra.Command{
		Use:   "doctor",
		Short: "Check reachability, the agent token, the MCP revision and the tool list",
		Args:  cobra.NoArgs,
		RunE:  func(*cobra.Command, []string) error { return a.mcpDoctor() },
	}
	config := &cobra.Command{
		Use:       "config claude-code|claude-desktop|hermes",
		Short:     "Print a ready-to-paste client config (no secret in it)",
		Args:      cobra.ExactArgs(1),
		ValidArgs: []string{"claude-code", "claude-desktop", "hermes"},
		RunE: func(_ *cobra.Command, args []string) error {
			t, err := a.resolve()
			if err != nil {
				return err
			}
			cmdArgs := []string{"mcp"}
			if t.name != "" {
				cmdArgs = append(cmdArgs, "--context", t.name)
			} else {
				cmdArgs = append(cmdArgs, "--hub", t.hub)
			}
			switch args[0] {
			case "claude-code":
				fmt.Fprintf(a.Stdout, "claude mcp add onemind -- onemind %s\n", strings.Join(cmdArgs, " "))
			case "claude-desktop":
				return printJSON(a.Stdout, map[string]any{"mcpServers": map[string]any{"onemind": map[string]any{"command": "onemind", "args": cmdArgs}}})
			case "hermes":
				fmt.Fprintf(a.Stdout, "mcp_servers:\n  onemind:\n    command: onemind\n    args: [%s]\n", strings.Join(cmdArgs, ", "))
			default:
				return exitWith(ExitUsage, "usage", "one of claude-code, claude-desktop, hermes")
			}
			return nil
		},
	}
	mcp.AddCommand(login, doctor, config)
	return []*cobra.Command{mcp}
}

func mcpPost(t *target, msg string, timeout time.Duration) (int, []byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(t.hub, "/")+"/mcp", bytes.NewReader([]byte(msg)))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	req.Header.Set("Authorization", "Bearer "+t.token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return 0, nil, exitWith(ExitUnreachable, "network", "cannot reach the hub")
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	return resp.StatusCode, body, err
}

func checkAgentToken(a *App, t *target) error {
	status, _, err := mcpPost(t, `{"jsonrpc":"2.0","id":1,"method":"ping"}`, a.G.Timeout)
	if err != nil {
		return err
	}
	switch status {
	case http.StatusOK:
		return nil
	case http.StatusUnauthorized:
		return exitWith(ExitUnauthenticated, "unauthenticated", "the hub does not know this token")
	case http.StatusForbidden:
		return exitWith(ExitPermissionDenied, "permission_denied", "this is not an agent token (people use `onemind login`)")
	}
	return exitWith(ExitError, "error", fmt.Sprintf("/mcp answered HTTP %d", status))
}

func (a *App) mcpDoctor() error {
	t, err := a.resolve()
	if err != nil {
		return err
	}
	report := map[string]any{"schema": "onemind.cli.mcp_doctor/v1", "hub": t.hub}
	fail := func(step string, err error) error {
		report["result"], report["failed"] = "FAIL", step
		if a.G.JSON {
			_ = printJSON(a.Stdout, report)
		} else {
			fmt.Fprintf(a.Stdout, "hub        %s\nresult     FAIL at %s\n", t.hub, step)
		}
		return err
	}
	if err := checkAgentToken(a, t); err != nil {
		return fail("agent token", err)
	}
	st, body, err := mcpPost(t, `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"onemind-doctor","version":"0"}}}`, a.G.Timeout)
	if err != nil || st != http.StatusOK {
		return fail("initialize", exitWith(ExitError, "error", fmt.Sprintf("initialize: HTTP %d %v", st, err)))
	}
	var init struct {
		Result struct {
			ProtocolVersion string                   `json:"protocolVersion"`
			ServerInfo      struct{ Version string } `json:"serverInfo"`
		} `json:"result"`
	}
	_ = json.Unmarshal(body, &init)
	_, body, err = mcpPost(t, `{"jsonrpc":"2.0","id":2,"method":"tools/list"}`, a.G.Timeout)
	if err != nil {
		return fail("tools/list", err)
	}
	var tl struct {
		Result struct {
			Tools []struct{ Name string } `json:"tools"`
		} `json:"result"`
	}
	_ = json.Unmarshal(body, &tl)
	var names []string
	for _, x := range tl.Result.Tools {
		names = append(names, x.Name)
		if strings.Contains(x.Name, "approve") {
			return fail("tool list", exitWith(ExitError, "error", "the hub offers an approve tool: refuse to use it"))
		}
	}
	sum := sha256.Sum256(body)
	report["revision"], report["tools"], report["tools_sha256"], report["result"] = init.Result.ProtocolVersion, names, hex.EncodeToString(sum[:8]), "OK"
	if a.G.JSON {
		return printJSON(a.Stdout, report)
	}
	return kv(a.Stdout, [][2]string{
		{"hub", t.hub}, {"principal", "agent token accepted"},
		{"revision", fmt.Sprintf("%s (gateway %s)", init.Result.ProtocolVersion, init.Result.ServerInfo.Version)},
		{fmt.Sprintf("tools (%d)", len(names)), strings.Join(names, " ")},
		{"tools sha256", hex.EncodeToString(sum[:8])}, {"result", "OK"},
	})
}
