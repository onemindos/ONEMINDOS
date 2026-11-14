// SPDX-License-Identifier: Apache-2.0

package fabric

import (
	"bufio"
	"bytes"
	"context"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/netip"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

// Where a joined node keeps its fabric identity (all under Layout.Root).
const (
	IdentityDir   = "/etc/onemind/identity"
	NATSDir       = "/etc/onemind/nats"
	StateFile     = "/etc/onemind/fabric.json"
	OnemindEnv    = "/etc/onemind/onemindd.env"
	K3sConfig     = "/etc/rancher/k3s/config.yaml"
	HostsFile     = "/etc/hosts"
	LeafStoreDir  = "/var/lib/onemind-nats-leaf"
	LeafUnit      = "onemind-nats-leaf.service"
	NATSUser      = "onemind-nats"
	hostsBegin    = "# BEGIN onemind fabric (managed by onemind fabric join)"
	hostsEnd      = "# END onemind fabric"
	StateSchema   = "onemind.fabric.state/v1"
	LocalNATSURL  = "nats://127.0.0.1:4222"
	MeshInterface = "tailscale0"
)

// State is /etc/onemind/fabric.json: what this node is in the fabric. It holds
// no secret; the heartbeat's fabric object is read from it.
type State struct {
	Schema       string `json:"schema"`
	NodeID       string `json:"node_id"`
	Role         string `json:"role"`
	HubURL       string `json:"hub_url"`
	HubMeshIP    string `json:"hub_mesh_ip,omitempty"`
	MeshAddr     string `json:"mesh_addr,omitempty"`
	CASHA256     string `json:"ca_sha256"`
	CertNotAfter string `json:"cert_not_after"`
	JoinedAt     string `json:"joined_at"`
}

// System is how the installer changes the machine; tests use a fake.
type System interface {
	Systemctl(ctx context.Context, args ...string) error
	// Chown gives path to the named system user, when that user exists.
	Chown(path, username string) error
}

// RealSystem runs systemctl and chown for real.
type RealSystem struct{}

// Systemctl runs systemctl with args.
func (RealSystem) Systemctl(ctx context.Context, args ...string) error {
	out, err := exec.CommandContext(ctx, "systemctl", args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("systemctl %s: %w: %s", strings.Join(args, " "), err, bytes.TrimSpace(out))
	}
	return nil
}

// Chown changes the owner of path to username (and its primary group).
func (RealSystem) Chown(path, username string) error {
	u, err := user.Lookup(username)
	if err != nil {
		return nil // no such user on this machine: keep root
	}
	uid, _ := strconv.Atoi(u.Uid)
	gid, _ := strconv.Atoi(u.Gid)
	return os.Chown(path, uid, gid)
}

// Installer applies delivered credentials to this machine.
type Installer struct {
	Root string // "/" in production; a temp dir in tests
	Sys  System
	Mesh *mesh.Client
	Out  io.Writer
	// EnrollTimeout bounds tailscale up + the wait for the mesh address.
	EnrollTimeout time.Duration
	Now           func() time.Time
}

func (in *Installer) p(abs string) string { return filepath.Join(in.Root, abs) }

func (in *Installer) say(format string, a ...any) {
	if in.Out != nil {
		fmt.Fprintf(in.Out, format+"\n", a...)
	}
}

// writeFile writes atomically with mode, creating parents (0755).
// rename is os.Rename; tests replace it.
var rename = os.Rename

func writeFile(path string, body []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".tmp-"+filepath.Base(path)+"-*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if err := tmp.Chmod(mode); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(body); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	err = rename(name, path)
	if errors.Is(err, syscall.EBUSY) || errors.Is(err, syscall.EXDEV) {
		// A file that is a mount point (a container's /etc/hosts) cannot be replaced by rename: write it in place.
		return os.WriteFile(path, body, mode)
	}
	return err
}

// Apply installs the identity, joins the mesh, configures the NATS leaf and,
// for a worker, the k3s agent. It is ordered so that a failure leaves a
// machine that can simply run the join again with a new code.
func (in *Installer) Apply(ctx context.Context, id *Identity, cr *Credentials, cert *x509.Certificate, t *Ticket, hubAddr string) (*State, error) {
	if in.Now == nil {
		in.Now = time.Now
	}
	role := cr.Role
	if role != "worker" && role != "leaf" {
		return nil, fmt.Errorf("credentials: unexpected role %q", role)
	}
	// 1. Identity: the box CA (also what tailscaled trusts, see the installer's drop-in), node cert and key.
	idDir := in.p(IdentityDir)
	if err := os.MkdirAll(idDir, 0o755); err != nil {
		return nil, err
	}
	for _, f := range []struct {
		name string
		body []byte
		mode os.FileMode
	}{{"ca.pem", []byte(cr.CACert), 0o644}, {"node.crt", []byte(cr.NodeCert), 0o644}, {"node.key", id.KeyPEM, 0o600}} {
		if err := writeFile(filepath.Join(idDir, f.name), f.body, f.mode); err != nil {
			return nil, fmt.Errorf("identity: %w", err)
		}
	}
	in.say("Identity    node-%s certificate until %s", id.NodeID, cert.NotAfter.UTC().Format("2006-01-02"))

	// 2. Coordinator names point at the hub on the LAN (NETWORKING §5.4, LAN first).
	ctrl := hubAddr
	if cr.Mesh != nil && len(cr.Mesh.ControlAddrs) > 0 {
		ctrl = cr.Mesh.ControlAddrs[0]
	}
	if ctrl != "" {
		if _, err := netip.ParseAddr(ctrl); err != nil {
			return nil, fmt.Errorf("control address %q is not an IP address", ctrl)
		}
		if err := in.setHosts(ctrl); err != nil {
			return nil, fmt.Errorf("/etc/hosts: %w", err)
		}
	}

	// 3. Mesh: restart tailscaled so it loads the box CA, then enroll with the one-time key.
	st := &State{Schema: StateSchema, NodeID: id.NodeID, Role: role, HubURL: t.Hub, CASHA256: t.CASHA,
		CertNotAfter: cert.NotAfter.UTC().Format(time.RFC3339)}
	if cr.Mesh != nil {
		if err := in.Sys.Systemctl(ctx, "restart", "tailscaled.service"); err != nil {
			return nil, err
		}
		b := &mesh.Bundle{ControlURL: cr.Mesh.ControlURL, ControlAddrs: cr.Mesh.ControlAddrs, CASHA256: cr.Mesh.CASHA256,
			AuthKey: cr.Mesh.AuthKey, Hostname: cr.Mesh.Hostname, HubMeshIP: cr.Mesh.HubMeshIP, ShieldsUp: cr.Mesh.ShieldsUp}
		res, err := in.Mesh.Enroll(ctx, b, mesh.EnrollOptions{KeyDir: in.p(mesh.DefaultKeyDir), Timeout: in.EnrollTimeout})
		if err != nil {
			return nil, err
		}
		st.MeshAddr, st.HubMeshIP = res.Addr, cr.Mesh.HubMeshIP
		in.say("Mesh        joined as %s (%s)", cr.Mesh.Hostname, strings.Join(cr.Mesh.Tags, ", "))
	}

	// 4. NATS leaf: TLS pinned to the box CA, node cert, the node's own nkey (its own account on the hub).
	if err := in.writeLeaf(id, cr); err != nil {
		return nil, fmt.Errorf("nats leaf: %w", err)
	}
	if err := in.Sys.Systemctl(ctx, "enable", "--now", LeafUnit); err != nil {
		return nil, err
	}
	_ = in.Sys.Systemctl(ctx, "reload-or-restart", LeafUnit)
	in.say("NATS        leaf to %s as account %s (own subjects only)", cr.NATS.URL, cr.NATS.Account)

	// 5. Worker: k3s agent config over the mesh (the installer starts the agent).
	if role == "worker" && cr.K3s != nil {
		if st.MeshAddr == "" {
			return nil, errors.New("a worker needs the mesh before k3s (no mesh block in the credentials)")
		}
		if err := in.writeK3s(cr, st.MeshAddr); err != nil {
			return nil, fmt.Errorf("k3s config: %w", err)
		}
		in.say("k3s         agent config written (server %s, ticket valid 1 h)", cr.K3s.ServerURL)
	}

	// 6. onemindd publishes to its local leaf from now on.
	if err := in.setEnv(map[string]string{"ONEMIND_NATS_URL": LocalNATSURL, "ONEMIND_NODE_ROLE": "node"}); err != nil {
		return nil, err
	}
	st.JoinedAt = in.Now().UTC().Format(time.RFC3339)
	raw, _ := json.MarshalIndent(st, "", "  ")
	if err := writeFile(in.p(StateFile), append(raw, '\n'), 0o644); err != nil {
		return nil, err
	}
	if err := in.Sys.Systemctl(ctx, "restart", "onemindd.service"); err != nil {
		in.say("note: %v", err)
	}
	return st, nil
}

func (in *Installer) writeLeaf(id *Identity, cr *Credentials) error {
	dir := in.p(NATSDir)
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return err
	}
	files := map[string][]byte{"ca.pem": []byte(cr.CACert), "node.crt": []byte(cr.NodeCert), "node.key": id.KeyPEM}
	for name, body := range files {
		if err := writeFile(filepath.Join(dir, name), body, 0o600); err != nil {
			return err
		}
	}
	nkeyFile := filepath.Join(dir, "leaf.nkey")
	if _, err := leaf.WriteNkeyFile(nkeyFile, id.NkeySeed); err != nil {
		return err
	}
	c := &leaf.Config{
		ServerName: "node-" + id.NodeID, StoreDir: in.p(LeafStoreDir), HubURLs: []string{cr.NATS.URL},
		CAFile: filepath.Join(dir, "ca.pem"), CertFile: filepath.Join(dir, "node.crt"), KeyFile: filepath.Join(dir, "node.key"),
		NkeyFile: nkeyFile,
	}
	conf := filepath.Join(dir, "leaf.conf")
	if _, err := leaf.Apply(conf, c); err != nil {
		return err
	}
	// onemindd cannot read /etc/onemind/nats (its sandbox), so it supervises the leaf from this copy.
	if _, err := leaf.SaveConfig(in.p(leaf.DefaultConfigPath), c); err != nil {
		return err
	}
	// The leaf's nats-server runs as its own system user (deploy/systemd/onemind-nats-leaf.service).
	for _, f := range []string{dir, conf, nkeyFile, filepath.Join(dir, "ca.pem"), filepath.Join(dir, "node.crt"), filepath.Join(dir, "node.key")} {
		if err := in.Sys.Chown(f, NATSUser); err != nil {
			return err
		}
	}
	return nil
}

func (in *Installer) writeK3s(cr *Credentials, meshAddr string) error {
	var b strings.Builder
	b.WriteString("# Written by `onemind fabric join` (NETWORKING.md §8): k3s over the mesh.\n")
	fmt.Fprintf(&b, "server: %q\n", cr.K3s.ServerURL)
	fmt.Fprintf(&b, "token: %q\n", cr.K3s.Token)
	fmt.Fprintf(&b, "node-ip: %q\n", meshAddr)
	fmt.Fprintf(&b, "flannel-iface: %q\n", MeshInterface)
	b.WriteString("node-label:\n  - \"onemind.io/role=worker\"\n")
	if err := os.MkdirAll(filepath.Dir(in.p(K3sConfig)), 0o700); err != nil {
		return err
	}
	return writeFile(in.p(K3sConfig), []byte(b.String()), 0o600)
}

func (in *Installer) setHosts(addr string) error {
	path := in.p(HostsFile)
	old, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	var out bytes.Buffer
	skip := false
	sc := bufio.NewScanner(bytes.NewReader(old))
	for sc.Scan() {
		line := sc.Text()
		switch {
		case line == hostsBegin:
			skip = true
		case line == hostsEnd:
			skip = false
		case !skip:
			out.WriteString(line + "\n")
		}
	}
	fmt.Fprintf(&out, "%s\n%s control.onemind.internal join.onemind.internal\n%s\n", hostsBegin, addr, hostsEnd)
	return writeFile(path, out.Bytes(), 0o644)
}

func (in *Installer) setEnv(set map[string]string) error {
	path := in.p(OnemindEnv)
	old, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	var out bytes.Buffer
	sc := bufio.NewScanner(bytes.NewReader(old))
	for sc.Scan() {
		line := sc.Text()
		if k, _, ok := strings.Cut(line, "="); ok {
			if _, mine := set[strings.TrimSpace(k)]; mine {
				continue
			}
		}
		out.WriteString(line + "\n")
	}
	for _, k := range []string{"ONEMIND_NATS_URL", "ONEMIND_NODE_ROLE"} {
		if v, ok := set[k]; ok {
			fmt.Fprintf(&out, "%s=%s\n", k, v)
		}
	}
	return writeFile(path, out.Bytes(), 0o644)
}

// LoadState reads fabric.json under root ("/" in production).
func LoadState(root string) (*State, error) {
	raw, err := os.ReadFile(filepath.Join(root, StateFile))
	if err != nil {
		return nil, err
	}
	var s State
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil, err
	}
	if s.Schema != StateSchema {
		return nil, fmt.Errorf("%s: unknown schema %q", StateFile, s.Schema)
	}
	return &s, nil
}

// Reporter returns the heartbeat's fabric object (contract §12.10): the hub
// reports role hub; a joined node its role, leaf link and certificate expiry;
// a machine that never joined (v0 install) reports nothing.
func Reporter(role string, leafLink func() string) func() *heartbeat.Fabric {
	return func() *heartbeat.Fabric {
		if role == "hub" {
			return &heartbeat.Fabric{Role: "hub", LeafLink: "none"}
		}
		st, err := LoadState("/")
		if err != nil {
			return nil
		}
		f := &heartbeat.Fabric{Role: st.Role, LeafLink: "none"}
		if leafLink != nil {
			f.LeafLink = leafLink()
		}
		if st.CertNotAfter != "" {
			na := st.CertNotAfter
			f.CertExpiresAt = &na
		}
		return f
	}
}
