// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
)

// Every key, seed and certificate here is generated when the test runs.
// Loopback stands in for the hub's mesh address.

type pki struct {
	dir    string
	ca     *x509.Certificate
	caKey  *ecdsa.PrivateKey
	caFile string
}

func newPKI(t *testing.T, dir, name string) *pki {
	t.Helper()
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: name},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	ca, _ := x509.ParseCertificate(der)
	p := &pki{dir: dir, ca: ca, caKey: key, caFile: filepath.Join(dir, name+"-ca.pem")}
	writePEM(t, p.caFile, "CERTIFICATE", der)
	return p
}

func writePEM(t *testing.T, path, typ string, der []byte) {
	t.Helper()
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: typ, Bytes: der}), 0o600); err != nil {
		t.Fatal(err)
	}
}

// issue returns cert and key paths for a leaf certificate.
func (p *pki) issue(t *testing.T, name string, server bool) (string, string) {
	t.Helper()
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	serial, _ := rand.Int(rand.Reader, big.NewInt(1<<62))
	tmpl := &x509.Certificate{
		SerialNumber: serial, Subject: pkix.Name{CommonName: name},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		KeyUsage: x509.KeyUsageDigitalSignature,
	}
	if server {
		tmpl.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
		tmpl.IPAddresses = []net.IP{net.ParseIP("127.0.0.1")}
	} else {
		tmpl.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
		tmpl.DNSNames = []string{name + ".onemind.internal"}
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, p.ca, &key.PublicKey, p.caKey)
	if err != nil {
		t.Fatal(err)
	}
	kder, _ := x509.MarshalECPrivateKey(key)
	c, k := filepath.Join(p.dir, name+".pem"), filepath.Join(p.dir, name+".key")
	writePEM(t, c, "CERTIFICATE", der)
	writePEM(t, k, "EC PRIVATE KEY", kder)
	return c, k
}

func freePort(t *testing.T) int {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port
}

func userKey(t *testing.T) ([]byte, string) {
	t.Helper()
	kp, err := nkeys.CreateUser()
	if err != nil {
		t.Fatal(err)
	}
	seed, _ := kp.Seed()
	pub, _ := kp.PublicKey()
	return seed, pub
}

func startServer(t *testing.T, conf string) *server.Server {
	t.Helper()
	opts, err := server.ProcessConfigFile(conf)
	if err != nil {
		t.Fatalf("config %s: %v", filepath.Base(conf), err)
	}
	opts.NoSigs, opts.NoLog = true, true
	s, err := server.NewServer(opts)
	if err != nil {
		t.Fatal(err)
	}
	go s.Start()
	if !s.ReadyForConnections(10 * time.Second) {
		t.Fatal("server not ready")
	}
	t.Cleanup(s.Shutdown)
	return s
}

// hubFixture is the hub side of §7: leaf listener with TLS verify, nkey users
// with per-node permissions.
type hubFixture struct {
	pki      *pki
	leafPort int
	nodePub  string
	srv      *server.Server
	client   string
}

func startHub(t *testing.T, dir string, nodePub string) *hubFixture {
	t.Helper()
	p := newPKI(t, dir, "box")
	cert, key := p.issue(t, "nats-hub", true)
	h := &hubFixture{pki: p, leafPort: freePort(t), nodePub: nodePub}
	cport := freePort(t)
	h.client = fmt.Sprintf("nats://127.0.0.1:%d", cport)
	conf := filepath.Join(dir, "hub.conf")
	body := fmt.Sprintf(`server_name: hub
listen: "127.0.0.1:%d"
leafnodes {
  listen: "127.0.0.1:%d"
  tls { cert_file: %q, key_file: %q, ca_file: %q, verify: true, timeout: 5 }
}
authorization { users = [
  { user: "local", password: "local-test-only" }
  { nkey: %q, permissions: {
      publish:   { allow: ["onemind.node.n1.status", "onemind.node.n1.event.>"] },
      subscribe: { allow: ["_INBOX.>"] } } }
] }
`, cport, h.leafPort, cert, key, p.caFile, nodePub)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	h.srv = startServer(t, conf)
	return h
}

type nodeFixture struct {
	cfg      *Config
	confPath string
}

func nodeConfig(t *testing.T, dir string, h *hubFixture, seed []byte, caFile string, withCert bool) *nodeFixture {
	t.Helper()
	confDir := filepath.Join(dir, "leaf")
	nkeyFile := filepath.Join(confDir, "node.nkey.conf")
	if _, err := WriteNkeyFile(nkeyFile, seed); err != nil {
		t.Fatal(err)
	}
	c := &Config{
		ServerName: "node-n1",
		Listen:     fmt.Sprintf("127.0.0.1:%d", freePort(t)),
		Monitor:    fmt.Sprintf("127.0.0.1:%d", freePort(t)),
		StoreDir:   filepath.Join(dir, "store"),
		HubURLs:    []string{fmt.Sprintf("tls://127.0.0.1:%d", h.leafPort)},
		CAFile:     caFile,
		NkeyFile:   nkeyFile,
	}
	if withCert {
		c.CertFile, c.KeyFile = h.pki.issue(t, "node-n1", false)
	}
	return &nodeFixture{cfg: c, confPath: filepath.Join(confDir, "leaf.conf")}
}

func waitHealth(t *testing.T, s *Supervisor, want string, d time.Duration) Health {
	t.Helper()
	deadline := time.Now().Add(d)
	var h Health
	for time.Now().Before(deadline) {
		h = s.Check(context.Background())
		if h.State == want {
			return h
		}
		time.Sleep(100 * time.Millisecond)
	}
	return h
}

func TestLeafConnectsOverTLSWithNodeNkey(t *testing.T) {
	dir := t.TempDir()
	seed, pub := userKey(t)
	hub := startHub(t, dir, pub)
	n := nodeConfig(t, dir, hub, seed, hub.pki.caFile, true)

	var reloads atomic.Int32
	sup := &Supervisor{ConfPath: n.confPath, Config: n.cfg, Reload: func(context.Context) error { reloads.Add(1); return nil }}
	changed, err := sup.Sync(context.Background())
	if err != nil || !changed || reloads.Load() != 1 {
		t.Fatalf("sync: changed=%v err=%v reloads=%d", changed, err, reloads.Load())
	}
	if changed, _ := sup.Sync(context.Background()); changed || reloads.Load() != 1 {
		t.Fatal("unchanged config must not rewrite or reload")
	}
	raw, _ := os.ReadFile(n.confPath)
	if strings.Contains(string(raw), string(seed)) {
		t.Fatal("leaf.conf must not contain the seed")
	}
	if fi, _ := os.Stat(n.cfg.NkeyFile); fi.Mode().Perm() != 0o600 {
		t.Fatalf("nkey file mode %o", fi.Mode().Perm())
	}

	if h := sup.Check(context.Background()); h.State != StateNoServer {
		t.Fatalf("before start: %+v", h)
	}
	startServer(t, n.confPath)
	if h := waitHealth(t, sup, StateUp, 10*time.Second); h.State != StateUp {
		t.Fatalf("leaf never connected: %+v", h)
	}
	if hub.srv.NumLeafNodes() != 1 {
		t.Fatalf("hub sees %d leaves", hub.srv.NumLeafNodes())
	}

	// A local publish on the node reaches the hub; a forbidden subject does not.
	hc, err := nats.Connect(hub.client, nats.UserInfo("local", "local-test-only"))
	if err != nil {
		t.Fatal(err)
	}
	defer hc.Close()
	got := make(chan string, 4)
	if _, err := hc.Subscribe("onemind.>", func(m *nats.Msg) { got <- m.Subject }); err != nil {
		t.Fatal(err)
	}
	hc.Flush()
	nc, err := nats.Connect("nats://" + n.cfg.Listen)
	if err != nil {
		t.Fatal(err)
	}
	defer nc.Close()
	deadline := time.Now().Add(5 * time.Second)
	for {
		// Interest propagates to the leaf asynchronously: retry until it lands.
		_ = nc.Publish("onemind.node.n1.status", []byte("{}"))
		_ = nc.Publish("onemind.node.n2.status", []byte("{}"))
		nc.Flush()
		select {
		case s := <-got:
			if s != "onemind.node.n1.status" {
				t.Fatalf("hub received a subject the node may not publish: %s", s)
			}
			goto done
		case <-time.After(200 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			t.Fatal("status never reached the hub")
		}
	}
done:
	time.Sleep(300 * time.Millisecond)
	for len(got) > 0 {
		if s := <-got; s != "onemind.node.n1.status" {
			t.Fatalf("hub received %s", s)
		}
	}
}

func TestLeafRefusedWithoutValidCredentials(t *testing.T) {
	cases := []struct {
		name     string
		otherKey bool
		otherCA  bool
		noCert   bool
	}{
		{name: "unknown nkey", otherKey: true},
		{name: "hub cert not from the pinned CA", otherCA: true},
		{name: "no node certificate", noCert: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir()
			seed, pub := userKey(t)
			hub := startHub(t, dir, pub)
			if tc.otherKey {
				seed, _ = userKey(t)
			}
			ca := hub.pki.caFile
			if tc.otherCA {
				ca = newPKI(t, dir, "other").caFile
			}
			n := nodeConfig(t, dir, hub, seed, ca, !tc.noCert)
			if _, err := Apply(n.confPath, n.cfg); err != nil {
				t.Fatal(err)
			}
			startServer(t, n.confPath)
			sup := &Supervisor{Config: n.cfg}
			time.Sleep(1500 * time.Millisecond)
			if h := sup.Check(context.Background()); h.State != StateDown {
				t.Fatalf("leaf state %+v, want down", h)
			}
			if hub.srv.NumLeafNodes() != 0 {
				t.Fatal("hub accepted the leaf")
			}
		})
	}
}

func validConfig() *Config {
	return &Config{
		ServerName: "node-3f9c2a1b7d4e", StoreDir: "/data/onemind/nats",
		HubURLs: []string{"tls://100.64.0.1:7422"}, CAFile: "/data/onemind/identity/ca.pem",
		CertFile: "/data/onemind/identity/tls.crt", KeyFile: "/data/onemind/identity/tls.key",
		NkeyFile: "/etc/onemind/nats/node.nkey.conf",
	}
}

func TestRenderGolden(t *testing.T) {
	got, err := validConfig().Render("/etc/onemind/nats/leaf.conf")
	if err != nil {
		t.Fatal(err)
	}
	want := `# Generated by onemindd (internal/leaf). Do not edit: changes are overwritten.
server_name: "node-3f9c2a1b7d4e"
listen: "127.0.0.1:4222"
http: "127.0.0.1:8222"
jetstream {
  store_dir: "/data/onemind/nats"
  domain: "node-3f9c2a1b7d4e"
  max_file_store: 256MB
}
leafnodes {
  remotes: [
    {
      urls: ["tls://100.64.0.1:7422"]
      include "node.nkey.conf"
      tls {
        ca_file: "/data/onemind/identity/ca.pem"
        cert_file: "/data/onemind/identity/tls.crt"
        key_file: "/data/onemind/identity/tls.key"
        timeout: 5
      }
    }
  ]
}
`
	if string(got) != want {
		t.Fatalf("render mismatch:\n%s", got)
	}
	c := validConfig()
	c.NkeyFile, c.CredsFile = "", "/etc/onemind/nats/node.creds"
	got, err = c.Render("/etc/onemind/nats/leaf.conf")
	if err != nil || !strings.Contains(string(got), `credentials: "/etc/onemind/nats/node.creds"`) {
		t.Fatalf("creds render: %v\n%s", err, got)
	}
}

func TestValidateRejects(t *testing.T) {
	cases := map[string]func(c *Config){
		"plaintext hub":    func(c *Config) { c.HubURLs = []string{"nats://100.64.0.1:7422"} },
		"password in url":  func(c *Config) { c.HubURLs = []string{"tls://u:p@100.64.0.1:7422"} },
		"no port":          func(c *Config) { c.HubURLs = []string{"tls://100.64.0.1"} },
		"no hub":           func(c *Config) { c.HubURLs = nil },
		"public listen":    func(c *Config) { c.Listen = "0.0.0.0:4222" },
		"public monitor":   func(c *Config) { c.Monitor = "192.0.2.5:8222" },
		"no CA":            func(c *Config) { c.CAFile = "" },
		"relative path":    func(c *Config) { c.CAFile = "ca.pem" },
		"quote in path":    func(c *Config) { c.StoreDir = `/data/x" }` },
		"cert without key": func(c *Config) { c.KeyFile = "" },
		"no credentials":   func(c *Config) { c.NkeyFile = "" },
		"both credentials": func(c *Config) { c.CredsFile = "/etc/onemind/nats/node.creds" },
		"hub domain":       func(c *Config) { c.Domain = "hub" },
		"bad name":         func(c *Config) { c.ServerName = "node.1" },
		"bad size":         func(c *Config) { c.MaxFileStore = "lots" },
	}
	for name, mut := range cases {
		c := validConfig()
		mut(c)
		if _, err := c.Render("/etc/onemind/nats/leaf.conf"); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	if _, err := validConfig().Render("/etc/other/leaf.conf"); err == nil {
		t.Error("nkey file outside the config directory accepted")
	}
}

func TestWriteNkeyFileRejectsNonUserSeeds(t *testing.T) {
	dir := t.TempDir()
	if _, err := WriteNkeyFile(filepath.Join(dir, "a"), []byte("not-a-seed")); err == nil {
		t.Fatal("garbage accepted")
	}
	acc, _ := nkeys.CreateAccount()
	seed, _ := acc.Seed()
	if _, err := WriteNkeyFile(filepath.Join(dir, "b"), seed); err == nil {
		t.Fatal("account seed accepted")
	}
	if _, err := os.Stat(filepath.Join(dir, "b")); err == nil {
		t.Fatal("file written for a rejected seed")
	}
}

func TestCheckHealthBadServer(t *testing.T) {
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(500) })}
	l, _ := net.Listen("tcp", "127.0.0.1:0")
	go srv.Serve(l)
	defer srv.Close()
	h := CheckHealth(context.Background(), http.DefaultClient, l.Addr().String())
	if h.State != StateNoServer || !strings.Contains(h.Error, "500") {
		t.Fatalf("%+v", h)
	}
}

func TestRunRetriesSyncAndStops(t *testing.T) {
	dir := t.TempDir()
	c := validConfig()
	c.NkeyFile = filepath.Join(dir, "node.nkey.conf")
	c.Monitor = fmt.Sprintf("127.0.0.1:%d", freePort(t))
	var reloads atomic.Int32
	s := &Supervisor{ConfPath: filepath.Join(dir, "leaf.conf"), Config: c, Interval: 20 * time.Millisecond,
		Reload: func(context.Context) error { reloads.Add(1); return nil }}
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
	defer cancel()
	s.Run(ctx)
	if reloads.Load() != 1 || s.Last().State != StateNoServer {
		t.Fatalf("reloads=%d last=%+v", reloads.Load(), s.Last())
	}
}
