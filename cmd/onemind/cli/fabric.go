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
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/mesh"
)

// The fabric join on a new machine, and the owner's side of it
// (contract §12.11; docs/leap/core/FABRIC.md §3.1).
func fabricCommands() []Command {
	return []Command{
		{
			Path:  []string{"fabric", "join"},
			Usage: "onemind fabric join 'onemind-join:v1?…' [--hub-addr IP] [--timeout 20m]",
			Run:   func(env *Env, args []string) error { return fabricJoin(args, env.Stdout) },
		},
		{
			Path:  []string{"fabric", "ticket"},
			Usage: "onemind fabric ticket [--hub URL] [--role worker|leaf] [--ttl 15m] [--token T] [--json]",
			Run:   func(env *Env, args []string) error { return fabricTicket(args, env.Stdout) },
		},
		{
			Path:  []string{"fabric", "approve"},
			Usage: "onemind fabric approve ACTION_ID [--hub URL] [--token T]",
			Run:   func(env *Env, args []string) error { return fabricApprove(args, env.Stdout) },
		},
		{
			Path:  []string{"fabric", "status"},
			Usage: "onemind fabric status [--hub URL] [--token T] [--json]",
			Run:   func(env *Env, args []string) error { return fabricStatus(args, env.Stdout) },
		},
	}
}

// Test seams.
var (
	newInstaller = func(out io.Writer) *fabric.Installer {
		return &fabric.Installer{Root: "/", Sys: fabric.RealSystem{}, Mesh: mesh.NewClient(), Out: out}
	}
	collectFacts = func() (fabric.NodeFacts, error) {
		st := detect.New().Collect(context.Background())
		return fabric.NodeFacts{NodeID: st.NodeID, Hostname: hostLabel(st.Hostname), Board: st.Board, Arch: st.Arch,
			OS: map[string]string{"id": st.OS.ID, "version_id": st.OS.VersionID, "pretty": st.OS.Pretty}}, nil
	}
	isRoot   = func() bool { return os.Geteuid() == 0 }
	pollWait = 3 * time.Second
)

var labelRe = regexp.MustCompile(`[^A-Za-z0-9-]+`)

func hostLabel(h string) string {
	h = strings.Trim(labelRe.ReplaceAllString(strings.SplitN(h, ".", 2)[0], "-"), "-")
	if len(h) > 63 {
		h = strings.Trim(h[:63], "-")
	}
	if h == "" {
		return "node"
	}
	return h
}

func fabricJoin(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("fabric join", flag.ContinueOnError)
	code := fs.String("code", "", "join code (instead of the QR text)")
	hub := fs.String("hub", "", "hub URL, e.g. https://box.local (with --code)")
	ca := fs.String("ca", "", "box CA sha256 (with --code)")
	hubAddr := fs.String("hub-addr", "", "dial this IP for the hub instead of resolving its name (mDNS not working)")
	timeout := fs.Duration("timeout", 20*time.Minute, "how long to wait for the owner's approval")
	var payload string
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		payload, args = args[0], args[1:]
	}
	if err := fs.Parse(args); err != nil {
		return err
	}
	var t *fabric.Ticket
	var err error
	if payload != "" {
		t, err = fabric.ParseQR(payload)
	} else {
		t = &fabric.Ticket{Code: *code, Hub: *hub, CASHA: strings.ToLower(*ca)}
		err = t.Validate()
	}
	if err != nil {
		return err
	}
	if !isRoot() {
		return errors.New("run as root (sudo): joining writes the node's identity and starts its services")
	}
	facts, err := collectFacts()
	if err != nil {
		return err
	}
	id, err := fabric.NewIdentity(facts.NodeID, facts.Hostname)
	if err != nil {
		return err
	}
	u, _ := url.Parse(t.Hub)
	hc, _ := fabric.PinnedClient(t.CASHA, u.Hostname(), *hubAddr, 30*time.Second)
	c := &fabric.Client{HTTP: hc, Hub: strings.TrimSuffix(t.Hub, "/")}
	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()

	acc, err := c.Request(ctx, t.Code, id, facts)
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "Hub         %s (box CA pinned)\n", u.Hostname())
	fmt.Fprintf(out, "This node   %s · %s · %s · %s\n", facts.Hostname, facts.Board, facts.Arch, dash(facts.OS["pretty"]))
	fmt.Fprintf(out, "Role        %s\n", acc.Role)
	fmt.Fprintf(out, "Code        %s   <- check this matches the card on your phone\n", acc.MatchCode)
	fmt.Fprintln(out, "Waiting for the owner to approve…")
	creds, err := c.Wait(ctx, t.Code, id, acc.RequestID, pollWait)
	if err != nil {
		return err
	}
	cert, err := creds.Check(id, t.CASHA)
	if err != nil {
		return err
	}
	fmt.Fprintln(out, "Approved.")
	st, err := newInstaller(out).Apply(ctx, id, creds, cert, t, *hubAddr)
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "Done. This node is a %s (node-%s).\n", st.Role, st.NodeID)
	return nil
}

func hubAndToken(fs *flag.FlagSet) (*string, *string) {
	return fs.String("hub", envOr("ONEMIND_HUB", "http://127.0.0.1:8080"), "hub gateway URL"),
		fs.String("token", os.Getenv("ONEMIND_TOKEN"), "owner token (prefer ONEMIND_TOKEN)")
}

func httpSend(method, u, token string, body any, out any) error {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	var rd io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rd = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, u, rd)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if resp.StatusCode >= 300 {
		var ge gatewayError
		if json.Unmarshal(raw, &ge) == nil && ge.Error != "" {
			return fmt.Errorf("HTTP %d %s: %s", resp.StatusCode, ge.Error, ge.Message)
		}
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	if out == nil {
		return nil
	}
	return json.Unmarshal(raw, out)
}

func fabricTicket(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("fabric ticket", flag.ContinueOnError)
	hub, token := hubAndToken(fs)
	role := fs.String("role", "worker", "worker (k3s + leaf) or leaf (NATS leaf only)")
	ttl := fs.Duration("ttl", 15*time.Minute, "how long the code stays valid (at most 1h)")
	asJSON := fs.Bool("json", false, "print JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	var t struct {
		TicketID  string `json:"ticket_id"`
		Role      string `json:"role"`
		ExpiresAt string `json:"expires_at"`
		CA        string `json:"hub_ca_sha256"`
		QR        string `json:"qr_payload"`
		OneTime   struct {
			JoinCode string `json:"join_code"`
		} `json:"one_time"`
	}
	body := map[string]any{"role": *role, "expires_in_s": int(ttl.Seconds())}
	if err := httpSend(http.MethodPost, strings.TrimSuffix(*hub, "/")+"/v1/fabric/join-tickets", *token, body, &t); err != nil {
		return err
	}
	if *asJSON {
		return printJSON(out, t)
	}
	fmt.Fprintf(out, "Join code   %s   (one use, until %s, role %s)\n", t.OneTime.JoinCode, t.ExpiresAt, t.Role)
	fmt.Fprintf(out, "Box CA      %s\n\n", t.CA)
	fmt.Fprintf(out, "On the new machine (from a checkout of this repository):\n\n    sudo deploy/install.sh --role node --join '%s'\n\n", t.QR)
	fmt.Fprintf(out, "or, if OneMind is already installed there:\n\n    sudo onemind fabric join '%s'\n\n", t.QR)
	fmt.Fprintln(out, "Then approve the request on the dashboard (Approvals), after checking its code matches.")
	return nil
}

func fabricApprove(args []string, out io.Writer) error {
	if len(args) == 0 || strings.HasPrefix(args[0], "-") {
		return errors.New("usage: onemind fabric approve ACTION_ID")
	}
	id, args := args[0], args[1:]
	fs := flag.NewFlagSet("fabric approve", flag.ContinueOnError)
	hub, token := hubAndToken(fs)
	if err := fs.Parse(args); err != nil {
		return err
	}
	var a struct {
		Type   string         `json:"type"`
		State  string         `json:"state"`
		Params map[string]any `json:"params"`
	}
	base := strings.TrimSuffix(*hub, "/") + "/v1/actions/" + url.PathEscape(id)
	if err := httpSend(http.MethodGet, base, *token, nil, &a); err != nil {
		return err
	}
	if a.Type != "node.join" {
		return fmt.Errorf("action %s is %s, not node.join", id, a.Type)
	}
	fmt.Fprintf(out, "Approving %s %v (%v, %v) code %v\n", a.Type, a.Params["hostname"], a.Params["role"], a.Params["arch"], a.Params["match_code"])
	if err := httpSend(http.MethodPost, base+"/approve", *token, nil, &a); err != nil {
		return err
	}
	fmt.Fprintf(out, "%s\n", a.State)
	return nil
}

func fabricStatus(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("fabric status", flag.ContinueOnError)
	hub, token := hubAndToken(fs)
	asJSON := fs.Bool("json", false, "print JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	var v struct {
		Nodes []struct {
			NodeID   string `json:"node_id"`
			Hostname string `json:"hostname"`
			Role     string `json:"role"`
			State    string `json:"state"`
			LeafLink string `json:"leaf_link"`
		} `json:"nodes"`
		Joining []struct {
			NodeID    string `json:"node_id"`
			Hostname  string `json:"hostname"`
			Role      string `json:"role"`
			State     string `json:"state"`
			MatchCode string `json:"match_code"`
			ActionID  string `json:"action_id"`
		} `json:"joining"`
	}
	raw := map[string]any{}
	if err := httpSend(http.MethodGet, strings.TrimSuffix(*hub, "/")+"/v1/fabric", *token, nil, &raw); err != nil {
		return err
	}
	if *asJSON {
		return printJSON(out, raw)
	}
	b, _ := json.Marshal(raw)
	_ = json.Unmarshal(b, &v)
	fmt.Fprintln(out, "NODE\tHOSTNAME\tROLE\tSTATE\tLEAF")
	for _, n := range v.Nodes {
		fmt.Fprintf(out, "%s\t%s\t%s\t%s\t%s\n", n.NodeID, n.Hostname, n.Role, n.State, n.LeafLink)
	}
	for _, j := range v.Joining {
		fmt.Fprintf(out, "%s\t%s\t%s\tjoin:%s\tcode %s (action %s)\n", j.NodeID, j.Hostname, j.Role, j.State, j.MatchCode, j.ActionID)
	}
	return nil
}
