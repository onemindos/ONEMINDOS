// Command onemind is the OneMind command-line tool (v0: node commands only).
//
//	onemind node info [--root DIR] [--arch A] [--agent URL]
//	onemind nodes --hub URL [--token T] [--json]
//	onemind update status [--config F] [--json]
//	onemind update check  [--config F]
//	onemind update apply  [--config F] [--no-reboot]
//	onemind version
//
// The gateway token can come from --token or the ONEMIND_TOKEN environment
// variable (prefer the variable: flags end up in shell history).
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"runtime"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/version"
)

const usage = `usage:
  onemind node info [--root DIR] [--arch amd64|arm64] [--agent URL]
  onemind nodes --hub URL [--token TOKEN] [--json]
  onemind update status [--config FILE] [--json]
  onemind update check  [--config FILE]
  onemind update apply  [--config FILE] [--no-reboot]
  onemind version
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	var err error
	switch {
	case args[0] == "version":
		fmt.Fprintln(stdout, "onemind", version.Version)
		return 0
	case args[0] == "node" && len(args) > 1 && args[1] == "info":
		err = nodeInfo(args[2:], stdout)
	case args[0] == "nodes":
		err = nodes(args[1:], stdout)
	case args[0] == "update" && len(args) > 1 && (args[1] == "status" || args[1] == "check" || args[1] == "apply"):
		err = updateCmd(args[1], args[2:], stdout, stderr)
	default:
		fmt.Fprint(stderr, usage)
		return 2
	}
	if err != nil {
		fmt.Fprintln(stderr, "onemind:", err)
		return 1
	}
	return 0
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

func dash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// gatewayError is the contract §3 error body.
type gatewayError struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

func httpGet(url, token string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		var ge gatewayError
		if json.Unmarshal(body, &ge) == nil && ge.Error != "" {
			return nil, fmt.Errorf("%s: HTTP %d %s: %s", url, resp.StatusCode, ge.Error, ge.Message)
		}
		return nil, fmt.Errorf("%s: HTTP %d", url, resp.StatusCode)
	}
	return body, nil
}

func printJSON(out io.Writer, v any) error {
	enc := json.NewEncoder(out)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}
