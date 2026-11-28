// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/etcdir"
	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

// `onemind device join` (issue #717): a small device such as a sensor joins as a NATS leaf that may
// only publish its own subjects. It uses the same owner-approved join as `onemind fabric join`
// (contract §12.11): the box CA is pinned by the sha256 in the join code, the owner compares the
// match code on the approval card, and the hub delivers the credentials once. What differs is the
// local side: the sensor's leaf config lets every local client publish only
// onemind.node.<id>.status and onemind.node.<id>.event.>, and subscribe to nothing. The hub already
// keeps each node in its own NATS account (core/onemind_core/natsconf.py), so another node's subjects
// never reach this one; the local rule also keeps a sensor from reading even its own jobs.
func deviceCommands(a *App) []*cobra.Command {
	dev := &cobra.Command{Use: "device", Short: "Join a small device (a sensor) to a OneMind"}
	dev.AddCommand(&cobra.Command{
		Use:                "join 'onemind-join:v2?…' | --code-file F | --code C --hub URL --ca SHA256 [--dir D] [--hub-addr IP]",
		Short:              "Join this sensor as a publish-only leaf (the owner approves it)",
		DisableFlagParsing: true,
		RunE:               func(_ *cobra.Command, args []string) error { return deviceJoin(args, a.Stdout) },
	})
	return []*cobra.Command{dev}
}

// SensorStateSchema names sensor.json, what the device join wrote (no secret in it).
const SensorStateSchema = "onemind.sensor.state/v1"

// sensorNodeIDRe is the hub's node id rule (core/onemind_core/natsconf.py NODE_ID_RE). The id goes
// into subject names and the config file, so nothing else is accepted.
var sensorNodeIDRe = regexp.MustCompile(`^[a-z0-9]{1,32}$`)

// SensorSubjects is the publish-only set of a sensor: the node subjects the hub imports from its
// account (contract §12.9), without job results, since a sensor runs no jobs.
func SensorSubjects(nodeID string) ([]string, error) {
	if !sensorNodeIDRe.MatchString(nodeID) {
		return nil, fmt.Errorf("node id %q is not a lower-case id (a-z, 0-9, at most 32)", nodeID)
	}
	p := "onemind.node." + nodeID + "."
	return []string{p + "status", p + "event.>"}, nil
}

// RenderSensorConf is the leaf config (internal/leaf) for a sensor. Its one local program, "sensor",
// signs in with its own nkey (publicKey; the seed is <dir>/sensor.nk) and may publish only the
// sensor's own subjects and read nothing. There is no passwordless user: a sensor runs whatever
// the owner puts on it, and loopback alone does not tell those programs apart (G1).
func RenderSensorConf(confPath string, c *leaf.Config, nodeID, publicKey string) ([]byte, error) {
	if _, err := SensorSubjects(nodeID); err != nil {
		return nil, err
	}
	p, err := leaf.SensorProgram(nodeID, publicKey)
	if err != nil {
		return nil, err
	}
	d := *c
	d.Local = []leaf.LocalProgram{p}
	return d.Render(confPath)
}

// SensorState is <dir>/sensor.json.
type SensorState struct {
	Schema    string   `json:"schema"`
	NodeID    string   `json:"node_id"`
	Role      string   `json:"role"`
	HubURL    string   `json:"hub_url"`
	CASHA256  string   `json:"ca_sha256"`
	NATSURL   string   `json:"nats_url"`
	Publish   []string `json:"publish"`
	Subscribe []string `json:"subscribe"`
	// NkeyFile is the seed local programs on the sensor sign in with (0600; the seed is not in this file).
	NkeyFile string `json:"nkey_file,omitempty"`
	MeshAddr string `json:"mesh_addr,omitempty"`
	JoinedAt string `json:"joined_at"`
}

// Test seams.
var (
	sensorDir      = func() string { return filepath.Join(etcdir.Dir(), "sensor") }
	sensorStoreDir = "/var/lib/onemind-sensor"
	// sensorInstaller is what joins the mesh when the hub has Headscale on. It is fabric.Installer, so the
	// box CA lands where tailscaled reads it and the control names are pinned before the enrollment.
	sensorInstaller = func() *fabric.Installer {
		return &fabric.Installer{Root: "/", Sys: fabric.RealSystem{}, Mesh: mesh.NewClient()}
	}
)

// sensorTicket reads the join code and refuses anything a sensor must not use: another kind of
// device, a worker (a sensor never runs workloads), or a typed code without the box CA pin.
func sensorTicket(payload, code, hub, ca string) (*fabric.Ticket, error) {
	if payload != "" {
		t, err := fabric.ParseQR(payload)
		if err != nil {
			return nil, err
		}
		switch {
		case t.Kind == "worker":
			return nil, errors.New("this join code is for a worker; a sensor joins only as a leaf (ask for a leaf or sensor code)")
		case t.Kind != "leaf" && t.Kind != "sensor":
			return nil, fmt.Errorf("this join code is for a %s, not a sensor: open it on that device", dash(t.Kind))
		}
		return t, nil
	}
	if code == "" {
		return nil, errors.New("give the join text, --code-file F, or --code C with --hub URL and --ca SHA256")
	}
	if strings.TrimSpace(ca) == "" {
		return nil, errors.New("--ca is required with --code: the box CA fingerprint is what proves the hub is yours")
	}
	t := &fabric.Ticket{Code: code, Hub: hub, CASHA: strings.ToLower(strings.TrimSpace(ca)), Role: "leaf", Kind: "sensor"}
	if err := t.Validate(); err != nil {
		return nil, err
	}
	return t, nil
}

func deviceJoin(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("device join", flag.ContinueOnError)
	code := fs.String("code", "", "join code (instead of the QR text)")
	hub := fs.String("hub", "", "hub URL, e.g. https://box.local (with --code)")
	ca := fs.String("ca", "", "box CA sha256 (required with --code)")
	codeFile := fs.String("code-file", "", "read the 'onemind-join:v2?...' text from this file (keeps it out of the process list)")
	hubAddr := fs.String("hub-addr", "", "dial this IP for the hub instead of resolving its name (mDNS not working)")
	timeout := fs.Duration("timeout", 20*time.Minute, "how long to wait for the owner's approval")
	dir := fs.String("dir", "", "where the sensor keeps its identity and leaf config (default <etc>/onemind/sensor)")
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
	t, err := sensorTicket(payload, *code, *hub, *ca)
	if err != nil {
		return err
	}
	d := *dir
	if d == "" {
		d = sensorDir()
	}
	if !filepath.IsAbs(d) || filepath.Clean(d) != d {
		return fmt.Errorf("--dir must be a clean absolute path, got %q", d)
	}
	// Fail on a folder we cannot write before the owner is asked to approve anything.
	if err := os.MkdirAll(d, 0o700); err != nil {
		return fmt.Errorf("sensor folder: %w (run as root, or pass --dir)", err)
	}
	facts, err := collectFacts()
	if err != nil {
		return err
	}
	if _, err := SensorSubjects(facts.NodeID); err != nil {
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
	if acc.Role != "leaf" {
		return fmt.Errorf("the hub offered the %s role; a sensor joins only as a leaf, so nothing was approved (the request expires on its own)", dash(acc.Role))
	}
	fmt.Fprintf(out, "Hub         %s (box CA pinned)\n", u.Hostname())
	fmt.Fprintf(out, "This sensor %s · %s · %s\n", facts.Hostname, dash(facts.Board), dash(facts.Arch))
	fmt.Fprintln(out, "Role        leaf, publish only")
	fmt.Fprintf(out, "Code        %s   <- check this matches the card on your phone\n", acc.MatchCode)
	fmt.Fprintln(out, "Waiting for the owner to approve…")
	creds, err := c.Wait(ctx, t.Code, id, acc.RequestID, pollWait)
	if err != nil {
		return err
	}
	if creds.Role != "leaf" {
		return fmt.Errorf("credentials: role %s; a sensor accepts only leaf", dash(creds.Role))
	}
	if _, err := creds.Check(id, t.CASHA); err != nil {
		return err
	}
	fmt.Fprintln(out, "Approved.")
	st, err := writeSensor(ctx, d, id, creds, t, *hubAddr)
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "Done. node-%s may publish %s and reads nothing.\n", st.NodeID, strings.Join(st.Publish, ", "))
	fmt.Fprintf(out, "Programs on this sensor sign in to the leaf with the key in %s (owner only); there is no password-free user.\n", st.NkeyFile)
	fmt.Fprintf(out, "Start its leaf with: nats-server -c %s\n", filepath.Join(d, "sensor.conf"))
	return nil
}

// writeSensor writes the identity, the nkey seed (0600, never printed), the leaf config with the
// publish-only rule, and sensor.json. With a mesh block it joins the mesh first, since the hub's leaf
// port (the NATS URL in the credentials) is then on the mesh: fabric.Installer.JoinMesh writes the box
// CA to fabric.IdentityDir and pins the control address before it restarts tailscaled and enrolls.
func writeSensor(ctx context.Context, dir string, id *fabric.Identity, cr *fabric.Credentials, t *fabric.Ticket, hubAddr string) (*SensorState, error) {
	subjects, err := SensorSubjects(id.NodeID)
	if err != nil {
		return nil, err
	}
	st := &SensorState{Schema: SensorStateSchema, NodeID: id.NodeID, Role: "leaf", HubURL: t.Hub, CASHA256: t.CASHA,
		NATSURL: cr.NATS.URL, Publish: subjects, Subscribe: []string{}}
	if cr.Mesh != nil {
		res, err := sensorInstaller().JoinMesh(ctx, cr, hubAddr)
		if err != nil {
			return nil, fmt.Errorf("mesh: %w", err)
		}
		st.MeshAddr = res.Addr
	}
	for _, f := range []struct {
		name string
		body []byte
	}{{"ca.pem", []byte(cr.CACert)}, {"node.crt", []byte(cr.NodeCert)}, {"node.key", id.KeyPEM}} {
		if err := os.WriteFile(filepath.Join(dir, f.name), f.body, 0o600); err != nil {
			return nil, fmt.Errorf("identity: %w", err)
		}
	}
	nkeyFile := filepath.Join(dir, "leaf.nkey")
	if _, err := leaf.WriteNkeyFile(nkeyFile, id.NkeySeed); err != nil {
		return nil, err
	}
	// The sensor's own local key (G1): whatever writes readings on this device signs in with it.
	sensorPub, err := leaf.WriteLocalSeed(dir, leaf.ProgramSensor)
	if err != nil {
		return nil, err
	}
	st.NkeyFile = filepath.Join(dir, leaf.ProgramSensor+".nk")
	conf := filepath.Join(dir, "sensor.conf")
	lc := &leaf.Config{ServerName: "node-" + id.NodeID, StoreDir: sensorStoreDir, HubURLs: []string{cr.NATS.URL},
		CAFile: filepath.Join(dir, "ca.pem"), CertFile: filepath.Join(dir, "node.crt"), KeyFile: filepath.Join(dir, "node.key"),
		NkeyFile: nkeyFile}
	body, err := RenderSensorConf(conf, lc, id.NodeID, sensorPub)
	if err != nil {
		return nil, fmt.Errorf("leaf config: %w", err)
	}
	if err := os.WriteFile(conf, body, 0o600); err != nil {
		return nil, err
	}
	st.JoinedAt = time.Now().UTC().Format(time.RFC3339)
	raw, _ := json.MarshalIndent(st, "", "  ")
	if err := os.WriteFile(filepath.Join(dir, "sensor.json"), append(raw, '\n'), 0o644); err != nil {
		return nil, err
	}
	return st, nil
}
