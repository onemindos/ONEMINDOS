// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"runtime"
	"strings"
	"text/tabwriter"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
)

func nodeCommands() []Command {
	return []Command{
		{
			Path:  []string{"node", "info"},
			Usage: "onemind node info [--root DIR] [--arch amd64|arm64] [--agent URL]",
			Run:   func(env *Env, args []string) error { return nodeInfo(args, env.Stdout) },
		},
		{
			Path:  []string{"nodes"},
			Usage: "onemind nodes --hub URL [--token TOKEN] [--json]",
			Run:   func(env *Env, args []string) error { return nodes(args, env.Stdout) },
		},
	}
}

// nodeInfo prints this machine's heartbeat. By default it collects locally
// (the same code onemindd runs); --agent asks a running onemindd instead;
// --root reads a fixture tree (useful to see what a board would report).
func nodeInfo(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("node info", flag.ContinueOnError)
	root := fs.String("root", "/", "filesystem root to inspect")
	arch := fs.String("arch", runtime.GOARCH, "architecture to report with --root")
	agentURL := fs.String("agent", "", "read from a running onemindd, e.g. http://127.0.0.1:7480")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *agentURL != "" {
		body, err := httpGet(strings.TrimRight(*agentURL, "/")+"/api/v1/node", "")
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
	if *root == "/" {
		col = detect.New()
	} else {
		col = detect.NewFixture(*root, *arch)
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

// nodeRow is the subset of a gateway node (contract §3 GET /v1/nodes) the
// table shows. The JSON output passes the gateway's objects through unchanged.
type nodeRow struct {
	NodeID   string `json:"node_id"`
	Hostname string `json:"hostname"`
	Role     string `json:"role"`
	Board    string `json:"board"`
	Arch     string `json:"arch"`
	Status   string `json:"status"`
	LastSeen string `json:"last_seen"`
	OS       struct {
		ID        string `json:"id"`
		VersionID string `json:"version_id"`
	} `json:"os"`
	K3s struct {
		Present bool `json:"present"`
		Ready   bool `json:"ready"`
	} `json:"k3s"`
}

func nodes(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("nodes", flag.ContinueOnError)
	hub := fs.String("hub", os.Getenv("ONEMIND_HUB"), "gateway URL, e.g. http://hub.local:8080")
	token := fs.String("token", os.Getenv("ONEMIND_TOKEN"), "bearer token (or ONEMIND_TOKEN)")
	asJSON := fs.Bool("json", false, "print the raw JSON list")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *hub == "" {
		return errors.New("--hub is required (or set ONEMIND_HUB)")
	}
	body, err := httpGet(strings.TrimRight(*hub, "/")+"/v1/nodes", *token)
	if err != nil {
		return err
	}
	if *asJSON {
		var v any
		if err := json.Unmarshal(body, &v); err != nil {
			return fmt.Errorf("gateway returned invalid JSON: %w", err)
		}
		return printJSON(out, v)
	}
	var rows []nodeRow
	if err := json.Unmarshal(body, &rows); err != nil {
		return fmt.Errorf("gateway returned unexpected JSON: %w", err)
	}
	tw := tabwriter.NewWriter(out, 0, 2, 2, ' ', 0)
	fmt.Fprintln(tw, "NODE_ID\tHOSTNAME\tROLE\tBOARD\tARCH\tOS\tK3S\tSTATUS\tLAST_SEEN")
	for _, r := range rows {
		k3s := "-"
		if r.K3s.Present {
			k3s = "not-ready"
			if r.K3s.Ready {
				k3s = "ready"
			}
		}
		osName := strings.TrimSpace(r.OS.ID + " " + r.OS.VersionID)
		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
			r.NodeID, r.Hostname, r.Role, r.Board, r.Arch, dash(osName), k3s, dash(r.Status), dash(r.LastSeen))
	}
	return tw.Flush()
}
