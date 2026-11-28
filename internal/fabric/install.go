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

	"github.com/onemindos/onemindos/internal/etcdir"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

// Where a joined node keeps its fabric identity (all under Installer.Root): /etc/onemind, or
// ONEMIND_ETC_DIR on the OS image, whose /etc is read-only (internal/etcdir, #292).
var (
	IdentityDir = filepath.Join(etcdir.Dir(), "identity")
	NATSDir     = filepath.Join(etcdir.Dir(), "nats")
	StateFile   = filepath.Join(etcdir.Dir(), "fabric.json")
	// LocalKeysDir holds the nkey seeds of the programs that sign in to this machine's leaf (G1).
	// It is outside NATSDir, which belongs to the nats-server user: a seed is read only by the
	// program it names (onemindd, the owner's CLI), both of which run as root.
	LocalKeysDir = filepath.Join(etcdir.Dir(), leaf.LocalKeysDirName)
	OnemindEnv   = filepath.Join(etcdir.Dir(), "onemindd.env")
)

const (
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
		if errors.Is(err, syscall.EROFS) || errors.Is(err, syscall.EACCES) {
			// A read-only directory (the image's /etc) cannot take a temp file, but the file itself may be a
			// writable bind mount (/etc/hosts from /data/state): write it in place, as the Python set_hosts does.
			if _, serr := os.Stat(path); serr == nil {
				return os.WriteFile(path, body, mode)
			}
		}
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
	if err := in.pinControl(cr, hubAddr); err != nil {
		return nil, err
	}

	// 3. Mesh: restart tailscaled so it loads the box CA, then enroll with the one-time key.
	st := &State{Schema: StateSchema, NodeID: id.NodeID, Role: role, HubURL: t.Hub, CASHA256: t.CASHA,
		CertNotAfter: cert.NotAfter.UTC().Format(time.RFC3339)}
	if cr.Mesh != nil {
		res, err := in.enrollMesh(ctx, cr.Mesh, cr.Mesh.ShieldsUp)
		if err != nil {
			return nil, err
		}
		st.MeshAddr, st.HubMeshIP = res.Addr, cr.Mesh.HubMeshIP
	}

	// 4. NATS leaf: TLS pinned to the box CA, node cert, the node's own nkey (its own account on the hub).
	if err := in.writeLeaf(id, cr); err != nil {
		return nil, fmt.Errorf("nats leaf: %w", err)
	}
	if err := in.startLeaf(ctx); err != nil {
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

	// 6. onemindd publishes to its local leaf from now on, under the id the hub knows (firstboot wrote a
	// different one; the leaf account and fabric.json use this one, so heartbeats on the old id never arrive).
	if err := in.setEnv(map[string]string{"ONEMIND_NATS_URL": LocalNATSURL, "ONEMIND_NODE_ROLE": "node", "ONEMIND_NODE_ID": id.NodeID,
		"ONEMIND_NATS_NKEY_SEED":    filepath.Join(LocalKeysDir, leaf.ProgramOnemindd+".nk"),
		"ONEMIND_NATS_INBOX_PREFIX": leaf.InboxPrefix(leaf.ProgramOnemindd)}); err != nil {
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

// JoinMesh is the mesh part of Apply for a device that keeps the rest of its identity elsewhere (a
// sensor, `onemind device join`). It runs Apply's steps in Apply's order: the box CA into IdentityDir,
// where tailscaled.service reads it (its ConditionPathExists and SSL_CERT_FILE), the coordinator names
// pinned to the hub's LAN address, and only then the tailscaled restart and the enrollment, which uses
// up the one-time key. A device that joins this way accepts nothing inbound (shields up).
func (in *Installer) JoinMesh(ctx context.Context, cr *Credentials, hubAddr string) (*mesh.Result, error) {
	if cr.Mesh == nil {
		return nil, errors.New("no mesh block in the credentials")
	}
	if err := writeFile(filepath.Join(in.p(IdentityDir), "ca.pem"), []byte(cr.CACert), 0o644); err != nil {
		return nil, fmt.Errorf("identity: %w", err)
	}
	if err := in.pinControl(cr, hubAddr); err != nil {
		return nil, err
	}
	return in.enrollMesh(ctx, cr.Mesh, true)
}

// pinControl points the coordinator names at the mesh block's first control address, or at hubAddr
// when there is none (NETWORKING §5.4, LAN first).
func (in *Installer) pinControl(cr *Credentials, hubAddr string) error {
	ctrl := hubAddr
	if cr.Mesh != nil && len(cr.Mesh.ControlAddrs) > 0 {
		ctrl = cr.Mesh.ControlAddrs[0]
	}
	if ctrl == "" {
		return nil
	}
	if _, err := netip.ParseAddr(ctrl); err != nil {
		return fmt.Errorf("control address %q is not an IP address", ctrl)
	}
	if err := in.setHosts(ctrl); err != nil {
		return fmt.Errorf("/etc/hosts: %w", err)
	}
	return nil
}

// enrollMesh restarts tailscaled so it loads the box CA, then enrolls with the one-time key.
func (in *Installer) enrollMesh(ctx context.Context, m *MeshBlock, shieldsUp bool) (*mesh.Result, error) {
	if err := in.Sys.Systemctl(ctx, "restart", "tailscaled.service"); err != nil {
		return nil, err
	}
	b := &mesh.Bundle{ControlURL: m.ControlURL, ControlAddrs: m.ControlAddrs, CASHA256: m.CASHA256,
		AuthKey: m.AuthKey, Hostname: m.Hostname, HubMeshIP: m.HubMeshIP, ShieldsUp: shieldsUp}
	res, err := in.Mesh.Enroll(ctx, b, mesh.EnrollOptions{KeyDir: in.p(mesh.DefaultKeyDir), Timeout: in.EnrollTimeout})
	if err != nil {
		return nil, err
	}
	in.say("Mesh        joined as %s (%s)", m.Hostname, strings.Join(m.Tags, ", "))
	return res, nil
}

// startLeaf enables and starts the leaf. The OS image's units cannot be enabled (read-only /etc);
// its first boot starts them on every boot instead, so starting it now is enough (IMG-MESH-01, #292).
func (in *Installer) startLeaf(ctx context.Context) error {
	if err := in.Sys.Systemctl(ctx, "enable", "--now", LeafUnit); err != nil {
		in.say("note: %v; starting %s without enabling it", err, LeafUnit)
		return in.Sys.Systemctl(ctx, "start", LeafUnit)
	}
	return nil
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
	// Local sign-in (G1): each local program gets its own key and exact subjects; the leaf has no
	// passwordless user. The seeds stay in LocalKeysDir (root only); leaf.conf holds public keys.
	pubs := map[string]string{}
	for _, name := range []string{leaf.ProgramOnemindd, leaf.ProgramCLI} {
		pub, err := leaf.WriteLocalSeed(in.p(LocalKeysDir), name)
		if err != nil {
			return err
		}
		pubs[name] = pub
	}
	progs, err := leaf.MachinePrograms(id.NodeID, pubs)
	if err != nil {
		return err
	}
	c := &leaf.Config{
		Local:      progs,
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
	for _, k := range []string{"ONEMIND_NATS_URL", "ONEMIND_NODE_ROLE", "ONEMIND_NODE_ID", "ONEMIND_NATS_NKEY_SEED", "ONEMIND_NATS_INBOX_PREFIX"} {
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

// UpgradeLocal brings a machine that joined before the local sign-in (G1) up to it. Such a machine
// has a leaf.conf with a passwordless local user and no seeds, and onemind-leaf-check (the health
// gate's G3) refuses that file, so without this the update that ships G1 would fail its own trial
// boot and roll back. The image runs it at every boot, before the gate (onemind-leaf-local.service):
// it makes the onemindd and cli seeds, renders leaf.conf again with the machine's programs, points
// onemindd at its seed and reply prefix, and restarts the leaf and onemindd if they run.
// It does nothing, and returns false, on a machine that has not joined or is already current.
func (in *Installer) UpgradeLocal(ctx context.Context) (bool, error) {
	c, err := leaf.LoadConfig(in.p(leaf.DefaultConfigPath))
	if errors.Is(err, os.ErrNotExist) {
		return false, nil // not joined: there is no leaf to fix
	}
	if err != nil {
		return false, err
	}
	if len(c.Local) > 0 {
		return false, nil
	}
	st, err := LoadState(in.Root)
	if err != nil {
		return false, fmt.Errorf("fabric state: %w", err)
	}
	pubs := map[string]string{}
	for _, name := range []string{leaf.ProgramOnemindd, leaf.ProgramCLI} {
		pub, err := leaf.WriteLocalSeed(in.p(LocalKeysDir), name)
		if err != nil {
			return false, err
		}
		pubs[name] = pub
	}
	if c.Local, err = leaf.MachinePrograms(st.NodeID, pubs); err != nil {
		return false, err
	}
	// Order: leaf.conf, onemindd's env, then the saved Config. A crash in between leaves a Config
	// without Local, so the next boot redoes all of it.
	conf := in.p(filepath.Join(NATSDir, "leaf.conf"))
	if _, err := leaf.Apply(conf, c); err != nil {
		return false, err
	}
	if err := in.Sys.Chown(conf, NATSUser); err != nil {
		return false, err
	}
	if err := in.setEnv(map[string]string{
		"ONEMIND_NATS_NKEY_SEED":    filepath.Join(LocalKeysDir, leaf.ProgramOnemindd+".nk"),
		"ONEMIND_NATS_INBOX_PREFIX": leaf.InboxPrefix(leaf.ProgramOnemindd)}); err != nil {
		return false, err
	}
	if _, err := leaf.SaveConfig(in.p(leaf.DefaultConfigPath), c); err != nil {
		return false, err
	}
	// try-restart: a unit that is not running yet reads the new files when it starts. --no-block: this
	// runs before the health gate, and the gate must not wait on a restart queue.
	for _, u := range []string{LeafUnit, "onemindd.service"} {
		if err := in.Sys.Systemctl(ctx, "--no-block", "try-restart", u); err != nil {
			in.say("note: %v", err)
		}
	}
	in.say("Local bus   signed in with per-program keys (was open to every program on this machine)")
	return true, nil
}
