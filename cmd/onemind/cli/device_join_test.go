// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/leaf"
	"github.com/onemindos/onemindos/internal/mesh"
)

const sensorCode = "7KQ4-M2XP-9D3F"

// testCA is a throw-away box CA for the hub stand-in and the NATS test.
type testCA struct {
	cert *x509.Certificate
	key  *ecdsa.PrivateKey
	pem  []byte
	sha  string
}

func newTestCA(t *testing.T) *testCA {
	t.Helper()
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test box CA"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, _ := x509.ParseCertificate(der)
	sum := sha256.Sum256(der)
	return &testCA{cert: cert, key: key, pem: pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), sha: hex.EncodeToString(sum[:])}
}

// issue signs pub for a server name (dns != "") or as a client certificate.
func (ca *testCA) issue(t *testing.T, pub any, dns string) []byte {
	t.Helper()
	tmpl := &x509.Certificate{SerialNumber: big.NewInt(time.Now().UnixNano()), Subject: pkix.Name{CommonName: "leaf"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}}
	if dns != "" {
		tmpl.DNSNames, tmpl.ExtKeyUsage = []string{dns}, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, ca.cert, pub, ca.key)
	if err != nil {
		t.Fatal(err)
	}
	return der
}

// hubStandIn is a test-only hub: the two join routes of contract §12.11 over HTTPS under a box CA.
// The owner's approval is assumed (the first poll delivers), so the test is about the sensor's side.
func hubStandIn(t *testing.T, ca *testCA, role string) *httptest.Server {
	t.Helper()
	return hubStandInMesh(t, ca, role, nil, "tls://127.0.0.1:7422")
}

// hubStandInMesh is hubStandIn for a hub with Headscale on: the credentials carry meshBlock and a NATS
// URL on the hub's mesh address, as core/onemind_core/fabric.py sends them.
func hubStandInMesh(t *testing.T, ca *testCA, role string, meshBlock map[string]any, natsURL string) *httptest.Server {
	t.Helper()
	var csrPEM, natsPub string
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/fabric/join-requests", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Code   string `json:"join_code"`
			CSR    string `json:"csr_pem"`
			Pubkey string `json:"nats_pubkey"`
		}
		if json.NewDecoder(r.Body).Decode(&body) != nil || body.Code != sensorCode {
			http.Error(w, `{"error":"code_unknown"}`, http.StatusUnauthorized)
			return
		}
		csrPEM, natsPub = body.CSR, body.Pubkey
		_ = json.NewEncoder(w).Encode(map[string]string{"join_request_id": "jr1", "match_code": "MATCH1",
			"role": role, "poll": "/v1/fabric/join-requests/jr1"})
	})
	mux.HandleFunc("GET /v1/fabric/join-requests/jr1", func(w http.ResponseWriter, r *http.Request) {
		blk, _ := pem.Decode([]byte(csrPEM))
		csr, err := x509.ParseCertificateRequest(blk.Bytes)
		if err != nil {
			http.Error(w, `{"error":"bad"}`, http.StatusBadRequest)
			return
		}
		node := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: ca.issue(t, csr.PublicKey, "")})
		creds := map[string]any{"role": role, "node_cert": string(node), "ca_cert": string(ca.pem),
			"nats": map[string]string{"url": natsURL, "account": "NODE_abc123", "user_pubkey": natsPub}}
		if meshBlock != nil {
			creds["mesh"] = meshBlock
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"state": "approved", "credentials": creds})
	})
	srv := httptest.NewUnstartedServer(mux)
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	srv.TLS = &tls.Config{Certificates: []tls.Certificate{{Certificate: [][]byte{ca.issue(t, &key.PublicKey, "box.local"), ca.cert.Raw}, PrivateKey: key}}}
	srv.StartTLS()
	t.Cleanup(srv.Close)
	return srv
}

func sensorSeams(t *testing.T, dir string) {
	t.Helper()
	oldFacts, oldWait, oldStore, oldDir := collectFacts, pollWait, sensorStoreDir, sensorDir
	collectFacts = func() (fabric.NodeFacts, error) {
		return fabric.NodeFacts{NodeID: "abc123", Hostname: "sensor1", Board: "test", Arch: "arm64"}, nil
	}
	pollWait, sensorStoreDir = 10*time.Millisecond, filepath.Join(dir, "store")
	sensorDir = func() string { return filepath.Join(dir, "sensor") }
	t.Cleanup(func() { collectFacts, pollWait, sensorStoreDir, sensorDir = oldFacts, oldWait, oldStore, oldDir })
}

func sensorQR(srv *httptest.Server, ca, kind string) string {
	u, _ := url.Parse(srv.URL)
	_, port, _ := net.SplitHostPort(u.Host)
	return "onemind-join:v2?hub=https%3A%2F%2Fbox.local%3A" + port + "&ca=" + ca + "&code=" + sensorCode + "&kind=" + kind
}

// Must refuse (issue #717): a code for a worker or another device, and a typed code without a CA pin.
// None of these reach the network.
func TestDeviceJoinRefusesBeforeTheNetwork(t *testing.T) {
	sensorSeams(t, t.TempDir())
	v2 := "onemind-join:v2?hub=https%3A%2F%2Fbox.local&ca=" + strings.Repeat("ab", 32) + "&code=" + sensorCode + "&kind="
	for _, c := range []struct {
		name string
		args []string
		want string
	}{
		{"worker code", []string{v2 + "worker"}, "a sensor joins only as a leaf"},
		{"phone code", []string{v2 + "phone"}, "for a phone, not a sensor"},
		{"typed code without the CA pin", []string{"--code", sensorCode, "--hub", "https://box.local"}, "--ca is required"},
		{"typed code with a bad CA pin", []string{"--code", sensorCode, "--hub", "https://box.local", "--ca", "abc"}, "fingerprint"},
		{"nothing", nil, "give the join text"},
		{"relative dir", []string{v2 + "sensor", "--dir", "rel"}, "clean absolute path"},
	} {
		if err := deviceJoin(c.args, io.Discard); err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("%s: got %v, want an error containing %q", c.name, err, c.want)
		}
	}
}

// The whole join against the hub stand-in: the CA is pinned, the match code shown, and the sensor
// folder holds its identity, its nkey seed (0600) and a leaf config with the publish-only rule.
func TestDeviceJoinAgainstHubStandIn(t *testing.T) {
	dir := t.TempDir()
	sensorSeams(t, dir)
	ca := newTestCA(t)
	srv := hubStandIn(t, ca, "leaf")
	var out strings.Builder
	if err := deviceJoin([]string{sensorQR(srv, ca.sha, "sensor"), "--hub-addr", "127.0.0.1"}, &out); err != nil {
		t.Fatalf("join: %v\n%s", err, out.String())
	}
	if !strings.Contains(out.String(), "MATCH1") || !strings.Contains(out.String(), "box CA pinned") {
		t.Errorf("output lacks the match code or the pin line:\n%s", out.String())
	}
	sd := filepath.Join(dir, "sensor")
	var st SensorState
	raw, err := os.ReadFile(filepath.Join(sd, "sensor.json"))
	if err != nil || json.Unmarshal(raw, &st) != nil {
		t.Fatalf("sensor.json: %v", err)
	}
	want := []string{"onemind.node.abc123.status", "onemind.node.abc123.event.>"}
	if st.Role != "leaf" || st.CASHA256 != ca.sha || strings.Join(st.Publish, " ") != strings.Join(want, " ") || len(st.Subscribe) != 0 {
		t.Errorf("sensor.json = %+v", st)
	}
	for _, f := range []string{"leaf.nkey", "node.key", "sensor.conf", "sensor.nk"} {
		fi, err := os.Stat(filepath.Join(sd, f))
		if err != nil || fi.Mode().Perm() != 0o600 {
			t.Errorf("%s: %v mode %v, want 0600", f, err, fi)
		}
	}
	conf, _ := os.ReadFile(filepath.Join(sd, "sensor.conf"))
	if !strings.Contains(string(conf), `subscribe: {deny: [">"]}`) || strings.Contains(string(conf), "no_auth_user") || !strings.Contains(string(conf), "{nkey:") {
		t.Errorf("sensor.conf lacks the publish-only rule:\n%s", conf)
	}
	seed, _ := os.ReadFile(filepath.Join(sd, "leaf.nkey"))
	if s := strings.TrimSuffix(strings.TrimPrefix(strings.TrimSpace(string(seed)), `nkey: "`), `"`); !strings.HasPrefix(s, "SU") ||
		strings.Contains(out.String(), s) {
		t.Errorf("the nkey seed is missing from leaf.nkey, or was printed")
	}
}

// A hub whose CA is not the one in the code is refused before anything is sent; a hub that offers
// the worker role is refused before the owner is asked to approve.
func TestDeviceJoinRefusesWrongPinAndWorkerRole(t *testing.T) {
	dir := t.TempDir()
	sensorSeams(t, dir)
	ca, other := newTestCA(t), newTestCA(t)
	srv := hubStandIn(t, ca, "leaf")
	if err := deviceJoin([]string{sensorQR(srv, other.sha, "sensor"), "--hub-addr", "127.0.0.1"}, io.Discard); err == nil ||
		!strings.Contains(err.Error(), "box CA") {
		t.Errorf("wrong pin: got %v", err)
	}
	worker := hubStandIn(t, ca, "worker")
	if err := deviceJoin([]string{sensorQR(worker, ca.sha, "leaf"), "--hub-addr", "127.0.0.1"}, io.Discard); err == nil ||
		!strings.Contains(err.Error(), "only as a leaf") {
		t.Errorf("worker role: got %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "sensor", "sensor.json")); !errors.Is(err, os.ErrNotExist) {
		t.Errorf("a refused join wrote sensor.json: %v", err)
	}
}

// meshOrder records, in order, what the mesh join did to the machine.
type meshOrder struct {
	root, caPEM string
	steps       []string
	up          bool
	upArgs      []string
}

// Systemctl is the fake systemd: at the tailscaled restart it notes whether the box CA is already where
// tailscaled.service reads it and whether the control names are already pinned.
func (m *meshOrder) Systemctl(_ context.Context, args ...string) error {
	call := strings.Join(args, " ")
	if call == "restart tailscaled.service" {
		ca, _ := os.ReadFile(filepath.Join(m.root, fabric.IdentityDir, "ca.pem"))
		hosts, _ := os.ReadFile(filepath.Join(m.root, fabric.HostsFile))
		call += fmt.Sprintf(" (ca=%t hosts=%t)", string(ca) == m.caPEM,
			strings.Contains(string(hosts), "192.0.2.10 control.onemind.internal join.onemind.internal"))
	}
	m.steps = append(m.steps, "systemctl "+call)
	return nil
}
func (m *meshOrder) Chown(string, string) error { return nil }

// Run is the fake tailscale CLI: logged out until `up` runs.
func (m *meshOrder) Run(_ context.Context, args ...string) ([]byte, error) {
	switch args[0] {
	case "status":
		if m.up {
			return []byte(`{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.7"]},"Peer":{}}`), nil
		}
		return []byte(`{"BackendState":"NeedsLogin"}`), nil
	case "up":
		m.steps, m.up, m.upArgs = append(m.steps, "tailscale up"), true, args
	}
	return nil, nil
}

// With Headscale on, the hub sends a sensor a mesh block and a NATS URL on its mesh address. The join
// must put the box CA where tailscaled.service reads it (fabric.IdentityDir) and pin the control
// address before tailscaled restarts and the one-time key is spent, as fabric.Installer.Apply does.
func TestDeviceJoinWithMeshWritesCAAndHostsBeforeEnrolling(t *testing.T) {
	dir := t.TempDir()
	sensorSeams(t, dir)
	ca := newTestCA(t)
	root := filepath.Join(dir, "root")
	rec := &meshOrder{root: root, caPEM: string(ca.pem)}
	old := sensorInstaller
	sensorInstaller = func() *fabric.Installer {
		return &fabric.Installer{Root: root, Sys: rec, Mesh: &mesh.Client{Runner: rec, Now: time.Now}, EnrollTimeout: 5 * time.Second}
	}
	t.Cleanup(func() { sensorInstaller = old })
	meshBlock := map[string]any{"control_url": "https://control.onemind.internal:8444", "control_addrs": []string{"192.0.2.10"},
		"ca_sha256": ca.sha, "auth_key": "hskey-auth-test-only", "hostname": "node-abc123", "hub_mesh_ip": "100.64.0.1",
		"tags": []string{"tag:leaf"}, "shields_up": true}
	srv := hubStandInMesh(t, ca, "leaf", meshBlock, "tls://100.64.0.1:7422")
	var out strings.Builder
	if err := deviceJoin([]string{sensorQR(srv, ca.sha, "sensor"), "--hub-addr", "127.0.0.1"}, &out); err != nil {
		t.Fatalf("join: %v\n%s", err, out.String())
	}
	want := []string{"systemctl restart tailscaled.service (ca=true hosts=true)", "tailscale up"}
	if strings.Join(rec.steps, "; ") != strings.Join(want, "; ") {
		t.Fatalf("mesh steps = %q, want %q", rec.steps, want)
	}
	if fi, err := os.Stat(filepath.Join(root, fabric.IdentityDir, "ca.pem")); err != nil || fi.Mode().Perm() != 0o644 {
		t.Errorf("box CA for tailscaled: %v %v", err, fi)
	}
	args := strings.Join(rec.upArgs, " ")
	if strings.Contains(args, "hskey-auth") || !strings.Contains(args, "--shields-up") || !strings.Contains(args, "--hostname=node-abc123") {
		t.Errorf("tailscale up args: %s", args)
	}
	var st SensorState
	raw, _ := os.ReadFile(filepath.Join(dir, "sensor", "sensor.json"))
	if err := json.Unmarshal(raw, &st); err != nil || st.MeshAddr != "100.64.0.7" || st.NATSURL != "tls://100.64.0.1:7422" {
		t.Errorf("sensor.json = %+v (%v)", st, err)
	}
	conf, _ := os.ReadFile(filepath.Join(dir, "sensor", "sensor.conf"))
	if !strings.Contains(string(conf), `urls: ["tls://100.64.0.1:7422"]`) {
		t.Errorf("the leaf does not dial the hub's mesh address:\n%s", conf)
	}
}

func freeTCPPort(t *testing.T) int {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port
}

// Acceptance (issue #717): a sensor cannot subscribe outside its own subjects (in fact to nothing),
// and may publish only its own. The config is the one the join writes, run by a real nats-server.
func TestSensorCannotSubscribeOutsideItsOwnSubjects(t *testing.T) {
	dir := t.TempDir()
	ca := newTestCA(t)
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	kder, _ := x509.MarshalECPrivateKey(key)
	id, err := fabric.NewIdentity("abc123", "sensor1")
	if err != nil {
		t.Fatal(err)
	}
	files := map[string][]byte{"ca.pem": ca.pem,
		"node.crt": pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: ca.issue(t, &key.PublicKey, "")}),
		"node.key": pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kder})}
	for n, b := range files {
		if err := os.WriteFile(filepath.Join(dir, n), b, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	nkeyFile := filepath.Join(dir, "leaf.nkey")
	if _, err := leaf.WriteNkeyFile(nkeyFile, id.NkeySeed); err != nil {
		t.Fatal(err)
	}
	port := freeTCPPort(t)
	conf := filepath.Join(dir, "sensor.conf")
	lc := &leaf.Config{ServerName: "node-abc123", Listen: fmt.Sprintf("127.0.0.1:%d", port),
		Monitor: fmt.Sprintf("127.0.0.1:%d", freeTCPPort(t)), StoreDir: filepath.Join(dir, "store"),
		HubURLs: []string{fmt.Sprintf("tls://127.0.0.1:%d", freeTCPPort(t))}, CAFile: filepath.Join(dir, "ca.pem"),
		CertFile: filepath.Join(dir, "node.crt"), KeyFile: filepath.Join(dir, "node.key"), NkeyFile: nkeyFile}
	keys := t.TempDir()
	sensorPub, err := leaf.WriteLocalSeed(keys, leaf.ProgramSensor)
	if err != nil {
		t.Fatal(err)
	}
	body, err := RenderSensorConf(conf, lc, "abc123", sensorPub)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(conf, body, 0o600); err != nil {
		t.Fatal(err)
	}
	opts, err := server.ProcessConfigFile(conf)
	if err != nil {
		t.Fatalf("nats-server refused the sensor config: %v\n%s", err, body)
	}
	opts.NoLog, opts.NoSigs = true, true
	srv, err := server.NewServer(opts)
	if err != nil {
		t.Fatal(err)
	}
	go srv.Start()
	t.Cleanup(srv.Shutdown)
	if !srv.ReadyForConnections(10 * time.Second) {
		t.Fatal("nats-server did not start")
	}

	errs := make(chan error, 16)
	url := fmt.Sprintf("nats://127.0.0.1:%d", port)
	if anon, err := nats.Connect(url); err == nil {
		anon.Close()
		t.Fatal("a local client with no key was accepted by the sensor leaf")
	}
	signIn, err := leaf.ClientOptions(leaf.ProgramSensor, filepath.Join(keys, leaf.ProgramSensor+".nk"))
	if err != nil {
		t.Fatal(err)
	}
	nc, err := nats.Connect(url, append(signIn,
		nats.ErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, e error) { errs <- e }))...)
	if err != nil {
		t.Fatalf("the sensor's own key does not sign in: %v", err)
	}
	defer nc.Close()
	expect := func(what string, violation bool, do func() error) {
		t.Helper()
		if err := do(); err != nil {
			t.Fatalf("%s: %v", what, err)
		}
		if err := nc.Flush(); err != nil {
			t.Fatalf("%s: flush: %v", what, err)
		}
		select {
		case e := <-errs:
			if !violation || !strings.Contains(strings.ToLower(e.Error()), "permissions violation") {
				t.Errorf("%s: got %v", what, e)
			}
		case <-time.After(500 * time.Millisecond):
			if violation {
				t.Errorf("%s: allowed, want a permissions violation", what)
			}
		}
	}
	sub := func(s string) func() error { return func() error { _, err := nc.SubscribeSync(s); return err } }
	pub := func(s string) func() error { return func() error { return nc.Publish(s, []byte("{}")) } }

	expect("subscribe to another node's status", true, sub("onemind.node.other.status"))
	expect("subscribe to everything", true, sub(">"))
	expect("subscribe to the hub's jobs for this node", true, sub("onemind.node.abc123.job.>"))
	expect("subscribe to its own status", true, sub("onemind.node.abc123.status"))
	expect("publish as another node", true, pub("onemind.node.other.status"))
	expect("publish a job result", true, pub("onemind.node.abc123.jobresult.x"))
	expect("publish its own status", false, pub("onemind.node.abc123.status"))
	expect("publish its own event", false, pub("onemind.node.abc123.event.temperature"))
}

func TestSensorSubjectsRefuseOddNodeIDs(t *testing.T) {
	for _, id := range []string{"", "ABC", "a.b", "a*", strings.Repeat("a", 33), `a"b`} {
		if _, err := SensorSubjects(id); err == nil {
			t.Errorf("node id %q accepted", id)
		}
	}
}
