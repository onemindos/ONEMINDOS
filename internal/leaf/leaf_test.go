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
	mrand "math/rand/v2"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
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

// freePort picks a port a lab server listens on a moment later. It comes from below the kernels'
// ephemeral ranges (Linux 32768-60999, macOS 49152-65535): a port 0 pick is an ephemeral port, which
// any outgoing connection on a busy CI machine may take before the server binds it ("server not
// ready"); a port from 20000-32767 is never handed to an outgoing connection.
func freePort(t *testing.T) int {
	t.Helper()
	for i := 0; i < 200; i++ {
		port := 20000 + mrand.IntN(12768)
		if l, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port)); err == nil {
			l.Close()
			return port
		}
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port
}

// Lab leaves are rendered with one local program that may use the whole lab namespace, so the
// older tests can keep proving isolation between nodes. The real per-program lists are tested in
// local_test.go. Seeds are kept by leaf URL; dialLeaf and connectJS sign in with them.
var labSeeds sync.Map // leaf client URL -> user seed

func labProgram(t *testing.T) (LocalProgram, []byte) {
	t.Helper()
	seed, pub := userKey(t)
	all := []string{"onemind.>", "outbox.>", "$JS.>", "_INBOX.>"}
	return LocalProgram{Name: "lab", PublicKey: pub, Publish: all, Subscribe: all}, seed
}

// labLeaf adds the lab program to c and remembers its seed for c's client URL.
func labLeaf(t *testing.T, c *Config) {
	t.Helper()
	p, seed := labProgram(t)
	c.Local = []LocalProgram{p}
	labSeeds.Store("nats://"+c.Listen, seed)
}

func labOpts(url string) []nats.Option {
	if v, ok := labSeeds.Load(url); ok {
		seed := v.([]byte)
		pub, _ := nkeys.FromSeed(seed)
		p, _ := pub.PublicKey()
		return []nats.Option{nats.Nkey(p, func(b []byte) ([]byte, error) { return pub.Sign(b) })}
	}
	return nil
}

func dialLeaf(url string, o ...nats.Option) (*nats.Conn, error) {
	return nats.Connect(url, append(labOpts(url), o...)...)
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
	// ONEMIND_LAB_LOGDIR=<dir> keeps a debug log of every lab server and copies those of a failed
	// test into <dir> (for chasing a flaky lab run; off in CI).
	logDir := os.Getenv("ONEMIND_LAB_LOGDIR")
	if logDir != "" {
		opts.NoLog, opts.Debug, opts.Logtime = false, true, true
		opts.LogFile = conf + ".log"
	}
	s, err := server.NewServer(opts)
	if err != nil {
		t.Fatal(err)
	}
	if logDir != "" {
		s.ConfigureLogger()
		t.Cleanup(func() {
			if t.Failed() {
				b, _ := os.ReadFile(opts.LogFile)
				_ = os.WriteFile(filepath.Join(logDir, fmt.Sprintf("%d-%s.log", time.Now().UnixNano(), opts.ServerName)), b, 0o600)
			}
		})
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
	labLeaf(t, c)
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
	nc, err := dialLeaf("nats://" + n.cfg.Listen)
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

// Public user keys made once for the golden config (the seeds were thrown away).
const (
	goldenPubOnemindd = "UBSMVUZ4GQXTXWP5H5SMM4LPEZAIBCEU54ADTY25RCHRECSM2O5KJ25J"
	goldenPubCLI      = "UBCBIFZS445IWJW4WAVVVTVX5A4EFZOTO4JHC24I6NGDQGA4WU4MEOIN"
)

func validConfig() *Config {
	return &Config{
		ServerName: "node-3f9c2a1b7d4e", StoreDir: "/data/onemind/nats",
		HubURLs: []string{"tls://100.64.0.1:7422"}, CAFile: "/data/onemind/identity/ca.pem",
		CertFile: "/data/onemind/identity/tls.crt", KeyFile: "/data/onemind/identity/tls.key",
		NkeyFile: "/etc/onemind/nats/node.nkey.conf",
		Local:    []LocalProgram{{Name: "onemindd", PublicKey: goldenPubOnemindd, Publish: []string{"onemind.node.3f9c2a1b7d4e.status"}, Subscribe: []string{"_INBOX_onemindd.>"}}},
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
ping_interval: "15s"
ping_max: 2
jetstream {
  store_dir: "/data/onemind/nats"
  domain: "node-3f9c2a1b7d4e"
  max_file_store: 256MB
  max_memory_store: 0
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
# Local sign-in (G1): every program on this machine has its own nkey and its own subjects.
# There is no passwordless user: a client without a key is refused.
authorization {
  users: [
    {nkey: "UBSMVUZ4GQXTXWP5H5SMM4LPEZAIBCEU54ADTY25RCHRECSM2O5KJ25J", permissions: {publish: {allow: ["onemind.node.3f9c2a1b7d4e.status"]}, subscribe: {allow: ["_INBOX_onemindd.>"]}}}  # onemindd
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

// #601: a leaf config without max_memory_store: 0 (or without a file cap) is refused, so the
// leaf's JetStream can never grow in RAM.
func TestCheckConfRefusesUncappedJetStream(t *testing.T) {
	good, err := validConfig().Render("/etc/onemind/nats/leaf.conf")
	if err != nil {
		t.Fatal(err)
	}
	if err := CheckConf(good); err != nil {
		t.Fatalf("rendered config refused: %v", err)
	}
	ok := []string{
		"jetstream { store_dir: \"/x\", domain: \"node-n1\", max_file_store: 256MB, max_memory_store: 0 }\n",
		"jetstream {\n  max_file_store = 268435456\n  max_memory_store = 0B\n}\n",
	}
	for _, c := range ok {
		if err := CheckConf([]byte(c)); err != nil {
			t.Errorf("%q refused: %v", c, err)
		}
	}
	bad := map[string]string{
		"no memory cap":      strings.Replace(string(good), "  max_memory_store: 0\n", "", 1),
		"memory not zero":    strings.Replace(string(good), "max_memory_store: 0", "max_memory_store: 1GB", 1),
		"no file cap":        strings.Replace(string(good), "  max_file_store: 256MB\n", "", 1),
		"file cap zero":      strings.Replace(string(good), "max_file_store: 256MB", "max_file_store: 0", 1),
		"alias hides value":  strings.Replace(string(good), "max_memory_store: 0", "max_memory_store: 0\n  max_mem: 2GB", 1),
		"no jetstream block": strings.Replace(string(good), "jetstream {", "jetstream_off {", 1),
		"jetstream enabled":  "jetstream: enabled\n",
		"two blocks":         string(good) + "jetstream { max_file_store: 1GB, max_memory_store: 0 }\n",
		"lab config of #472": "jetstream { store_dir: \"/x\", domain: \"node-n1\", max_file_store: 256MB }\n",
	}
	for name, c := range bad {
		if err := CheckConf([]byte(c)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

// #601: the rendered leaf.conf, run by a real nats-server, refuses memory streams and keeps the
// outbox (a file stream) working.
func TestRenderedLeafRefusesMemoryStreams(t *testing.T) {
	dir := t.TempDir()
	seed, pub := userKey(t)
	hub := startHub(t, dir, pub)
	n := nodeConfig(t, dir, hub, seed, hub.pki.caFile, true)
	if _, err := Apply(n.confPath, n.cfg); err != nil {
		t.Fatal(err)
	}
	startServer(t, n.confPath)
	js := connectJS(t, "nats://"+n.cfg.Listen)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if _, err := js.CreateStream(ctx, jetstream.StreamConfig{Name: "MEM", Subjects: []string{"mem.>"}, Storage: jetstream.MemoryStorage}); err == nil {
		t.Fatal("the leaf accepted a memory stream: max_memory_store 0 is not in effect")
	}
	if err := EnsureOutbox(ctx, js, OutboxConfig{}); err != nil {
		t.Fatalf("the outbox (file storage) must still work: %v", err)
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
