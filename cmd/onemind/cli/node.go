// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"runtime"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
	onemind "github.com/onemindos/onemindos/sdk/go"
)

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func nodeCommands(a *App) []*cobra.Command {
	var root, arch, agentURL string
	var local bool
	info := &cobra.Command{
		Use:   "info",
		Short: "This machine's heartbeat (collected locally, or from a running onemindd with --agent)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			_ = local // today's `node info` is always local; --local is accepted for the CLI.md spelling
			return nodeInfo(root, arch, agentURL, a.Stdout)
		},
	}
	info.Flags().StringVar(&root, "root", "/", "filesystem root to inspect")
	info.Flags().StringVar(&arch, "arch", runtime.GOARCH, "architecture to report with --root")
	info.Flags().StringVar(&agentURL, "agent", "", "read from a running onemindd, e.g. http://127.0.0.1:7480")
	info.Flags().BoolVar(&local, "local", true, "this machine (the default)")
	node := &cobra.Command{Use: "node", Short: "This machine (local, no gateway)"}
	node.AddCommand(info)

	var status string
	list := func(*cobra.Command, []string) error { return a.nodesList(status) }
	nodes := &cobra.Command{
		Use:   "nodes",
		Short: "Machines in this OneMind (GET /v1/nodes)",
		Args:  cobra.NoArgs,
		RunE:  list,
	}
	nodes.Flags().StringVar(&status, "status", "", "only online, stale or offline")
	ls := &cobra.Command{Use: "list", Short: "List nodes", Args: cobra.NoArgs, RunE: list}
	ls.Flags().StringVar(&status, "status", "", "only online, stale or offline")
	get := &cobra.Command{
		Use:   "info NODE_ID",
		Short: "One node (GET /v1/nodes/{id})",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw any
			if err := c.Do(bg(), http.MethodGet, "/v1/nodes/"+url.PathEscape(args[0]), nil, &raw); err != nil {
				return err
			}
			return printJSON(a.Stdout, raw)
		},
	}
	nodes.AddCommand(ls, get)
	return []*cobra.Command{nodes, node}
}

// nodeInfo prints this machine's heartbeat. By default it collects locally (the same code
// onemindd runs); --agent asks a running onemindd instead; --root reads a fixture tree.
func nodeInfo(root, arch, agentURL string, out io.Writer) error {
	if agentURL != "" {
		body, err := httpGetPlain(strings.TrimRight(agentURL, "/") + "/api/v1/node")
		if err != nil {
			return err
		}
		var buf bytes.Buffer
		if err := json.Indent(&buf, body, "", "  "); err != nil {
			return fmt.Errorf("agent returned invalid JSON: %w", err)
		}
		_, err = fmt.Fprintln(out, strings.TrimSpace(buf.String()))
		return err
	}
	var col *detect.Collector
	if root == "/" {
		col = detect.New()
	} else {
		col = detect.NewFixture(root, arch)
	}
	col.Role = envOr("ONEMIND_NODE_ROLE", "node")
	if err := heartbeat.ValidateRole(col.Role); err != nil {
		return fmt.Errorf("ONEMIND_NODE_ROLE: %w", err)
	}
	col.NodeID = os.Getenv("ONEMIND_NODE_ID")
	if col.NodeID != "" {
		if err := heartbeat.ValidateNodeID(col.NodeID); err != nil {
			return fmt.Errorf("ONEMIND_NODE_ID: %w", err)
		}
	}
	return printJSON(out, col.Collect(context.Background()))
}

// httpGetPlain reads onemindd's local status endpoint (no token, no gateway).
func httpGetPlain(url string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, exitWith(ExitUnreachable, "network", err.Error())
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s: HTTP %d", url, resp.StatusCode)
	}
	return body, nil
}

func (a *App) nodesList(status string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	if a.G.JSON { // the gateway's objects, unchanged (today's behaviour)
		var raw []any
		if err := c.Do(bg(), http.MethodGet, "/v1/nodes", nil, &raw); err != nil {
			return err
		}
		if status != "" {
			kept := raw[:0]
			for _, n := range raw {
				if m, ok := n.(map[string]any); ok && m["status"] == status {
					kept = append(kept, n)
				}
			}
			raw = kept
		}
		return printJSON(a.Stdout, raw)
	}
	nodes, err := c.Nodes.List(bg())
	if err != nil {
		return err
	}
	var rows [][]string
	for _, n := range nodes {
		if status != "" && n.Status != status {
			continue
		}
		rows = append(rows, nodeRow(n))
	}
	return table(a.Stdout, "NODE_ID\tHOSTNAME\tROLE\tBOARD\tARCH\tOS\tK3S\tSTATUS\tLAST_SEEN", rows)
}

func nodeRow(n onemind.Node) []string {
	k3s := "-"
	if n.K3s != nil && n.K3s.Present != nil && *n.K3s.Present {
		k3s = "not-ready"
		if n.K3s.Ready != nil && *n.K3s.Ready {
			k3s = "ready"
		}
	}
	osName := ""
	if n.Os != nil {
		osName = strings.TrimSpace(deref(n.Os.Id) + " " + deref(n.Os.VersionId))
	}
	return []string{n.NodeId, deref(n.Hostname), deref(n.Role), deref(n.Board), deref(n.Arch), dash(osName), k3s,
		dash(n.Status), dash(n.LastSeen)}
}
