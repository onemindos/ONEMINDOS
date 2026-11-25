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

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/mesh"
)

// The fabric join on a new machine, and the owner's side of it
// (contract §12.11; docs/leap/core/FABRIC.md §3.1).
func fabricCommands(a *App) []*cobra.Command {
	// Each subcommand keeps its own flag handling, so cobra passes the arguments through untouched.
	sub := func(use, short string, run func(args []string, out io.Writer) error) *cobra.Command {
		return &cobra.Command{Use: use, Short: short, DisableFlagParsing: true,
			RunE: func(_ *cobra.Command, args []string) error { return run(args, a.Stdout) }}
	}
	fab := &cobra.Command{Use: "fabric", Short: "Join this machine to a OneMind, or add one (the owner's side)"}
	fab.AddCommand(
		sub("join 'onemind-join:v2?…' | --code-file F [--hub-addr IP] [--timeout 20m]", "Join this machine to a hub (run as root)", fabricJoin),
		sub("ticket [--hub URL] [--role worker|leaf] [--ttl 15m] [--token T] [--json]", "Mint a one-use join code", fabricTicket),
		sub("approve ACTION_ID [--hub URL] [--token T]", "Approve a node join request", fabricApprove),
		sub("status [--hub URL] [--token T] [--json]", "Nodes and pending joins", fabricStatus),
		sub("events [--count N] [--hub URL] [--token T] [--json]", "Who connected to the message bus, and who was refused (read-only)", fabricEvents),
		sub("upgrade-local", "Machine joined before G1: give its local NATS leaf per-program keys (run as root; the image does it at boot)", fabricUpgradeLocal),
		sub("outbox init|status|send", "Leaf node: queue messages for the hub through hub outages", fabricOutbox),
	)
	return []*cobra.Command{fab}
}

// Test seams.
var (
	newInstaller = func(out io.Writer) *fabric.Installer {
		return &fabric.Installer{Root: "/", Sys: fabric.RealSystem{}, Mesh: mesh.NewClient(), Out: out}
	}
	collectFacts = func() (fabric.NodeFacts, error) {
		st := detect.New().Collect(context.Background())
		name := st.Hostname
		if n := seedName(seedStatePath); n != "" {
			name = n
		}
		id, err := fabricNodeID(os.Getenv("ONEMIND_NODE_ID"), seedStatePath, st.NodeID)
		if err != nil {
			return fabric.NodeFacts{}, err
		}
		return fabric.NodeFacts{NodeID: id, Hostname: hostLabel(name), Board: st.Board, Arch: st.Arch,
			OS: map[string]string{"id": st.OS.ID, "version_id": st.OS.VersionID, "pretty": st.OS.Pretty}}, nil
	}
	isRoot   = func() bool { return os.Geteuid() == 0 }
	pollWait = 3 * time.Second
)

// seedStatePath is firstboot's record of the seed (the name the owner chose for this machine).
var seedStatePath = "/data/onemind/firstboot/state.json"

// seedName returns the node name from the seed, or "" when there is none (the
// default "OneMind" is not a choice, so the machine's own hostname is used).
func seedName(path string) string {
	raw, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var st struct {
		Name string `json:"name"`
	}
	if json.Unmarshal(raw, &st) != nil {
		return ""
	}
	if n := strings.TrimSpace(st.Name); n != "OneMind" {
		return n
	}
	return ""
}

// fabricIDRe is the hub's node id rule (core/onemind_core/natsconf.py NODE_ID_RE).
var fabricIDRe = sensorNodeIDRe

// fabricNodeID picks the id this machine asks to join with (#943): ONEMIND_NODE_ID when set (as
// `onemind node info` does), else the node_id first boot drew at random on this machine, else the
// detected id. The detected id is sha256(machine-id), which every machine built from one image can
// share, so it is only the fallback for a machine that never ran first boot.
func fabricNodeID(env, statePath, detected string) (string, error) {
	if env != "" {
		if !fabricIDRe.MatchString(env) {
			return "", fmt.Errorf("ONEMIND_NODE_ID must be 1-32 characters of a-z and 0-9, got %q", env)
		}
		return env, nil
	}
	if id := seedNodeID(statePath); id != "" {
		return id, nil
	}
	return detected, nil
}

// seedNodeID returns first boot's node_id, or "" when there is none the hub would accept.
func seedNodeID(path string) string {
	raw, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var st struct {
		NodeID string `json:"node_id"`
	}
	if json.Unmarshal(raw, &st) != nil || !fabricIDRe.MatchString(st.NodeID) {
		return ""
	}
	return st.NodeID
}

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

// fabricUpgradeLocal is what onemind-leaf-local.service runs before the health gate on every boot of
// an edge (Installer.UpgradeLocal). It is quiet when there is nothing to do.
func fabricUpgradeLocal(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("fabric upgrade-local", flag.ContinueOnError)
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() > 0 {
		return errors.New("fabric upgrade-local takes no arguments")
	}
	if !isRoot() {
		return errors.New("run as root (sudo): this writes the leaf's keys and configuration")
	}
	_, err := newInstaller(out).UpgradeLocal(context.Background())
	return err
}

func fabricJoin(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("fabric join", flag.ContinueOnError)
	code := fs.String("code", "", "join code (instead of the QR text)")
	hub := fs.String("hub", "", "hub URL, e.g. https://box.local (with --code)")
	ca := fs.String("ca", "", "box CA sha256 (with --code)")
	hubAddr := fs.String("hub-addr", "", "dial this IP for the hub instead of resolving its name (mDNS not working)")
	timeout := fs.Duration("timeout", 20*time.Minute, "how long to wait for the owner's approval")
	// The OS image's first boot keeps the code in a 0600 file: an argument is visible to every local
	// user in the process list for as long as the join waits (IMG-MESH-01, #292).
	codeFile := fs.String("code-file", "", "read the 'onemind-join:v2?...' (or v1) text from this file")
	var payload string
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		payload, args = args[0], args[1:]
	}
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *codeFile != "" {
		if payload != "" || *code != "" {
			return errors.New("--code-file replaces the join text and --code; give only one")
		}
		raw, err := os.ReadFile(*codeFile)
		if err != nil {
			return fmt.Errorf("--code-file: %w", err)
		}
		if payload = strings.TrimSpace(string(raw)); payload == "" {
			return errors.New("--code-file: the file is empty")
		}
	}
	var t *fabric.Ticket
	var err error
	if payload != "" {
		if t, err = fabric.ParseQR(payload); err == nil && !t.IsMachine() {
			err = fmt.Errorf("this join code is for a %s, not a machine: open it in the OneMind app on that device", t.Kind)
		}
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

// fabricEvents is `onemind fabric events` (#620, NATS plan N3): GET /v1/fabric/events, the newest
// connections, disconnections and refused sign-ins the hub's observer saw on the message bus.
// Read-only: nothing here can change a key or an account. Needs audit:read (owner or adult).
func fabricEvents(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("fabric events", flag.ContinueOnError)
	hub, token := hubAndToken(fs)
	asJSON := fs.Bool("json", false, "print JSON")
	limit := fs.Int("count", 50, "how many events, newest first (1 to 200)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *limit < 1 || *limit > 200 {
		return fmt.Errorf("--count must be between 1 and 200")
	}
	var v struct {
		Observer string `json:"observer"`
		Events   []struct {
			Seq      int    `json:"seq"`
			TS       string `json:"ts"`
			Event    string `json:"event"`
			Account  string `json:"account"`
			Key      string `json:"key"`
			Identity string `json:"identity"`
			Client   string `json:"client"`
			Name     string `json:"name"`
			Cause    string `json:"cause"`
			Reason   string `json:"reason"`
			Repeats  int    `json:"repeats"`
		} `json:"events"`
	}
	raw := map[string]any{}
	url := fmt.Sprintf("%s/v1/fabric/events?count=%d", strings.TrimSuffix(*hub, "/"), *limit)
	if err := httpSend(http.MethodGet, url, *token, nil, &raw); err != nil {
		return err
	}
	if *asJSON {
		return printJSON(out, raw)
	}
	b, _ := json.Marshal(raw)
	if err := json.Unmarshal(b, &v); err != nil {
		return fmt.Errorf("the hub's bus events are not readable: %w", err)
	}
	if v.Observer == "off" {
		fmt.Fprintln(out, "The bus observer is off on this hub (no observer key), so nothing is listed.")
		return nil
	}
	fmt.Fprintln(out, "TIME\tEVENT\tWHO\tACCOUNT\tDETAIL")
	for _, e := range v.Events {
		who := e.Identity
		if who == "" && e.Key != "" {
			who = e.Key[:8] + "..."
		}
		if who == "" {
			who = "-"
		}
		detail := strings.TrimSpace(e.Cause + " " + e.Reason)
		if e.Repeats > 0 {
			detail = fmt.Sprintf("%s (+%d more)", detail, e.Repeats)
		}
		fmt.Fprintf(out, "%s\t%s\t%s\t%s\t%s\n", e.TS, strings.TrimPrefix(e.Event, "fabric."), who, orDash(e.Account), orDash(detail))
	}
	if len(v.Events) == 0 {
		fmt.Fprintln(out, "No bus events yet.")
	}
	return nil
}

func orDash(s string) string {
	if strings.TrimSpace(s) == "" {
		return "-"
	}
	return s
}
