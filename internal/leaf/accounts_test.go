// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
)

// The hub's per-node NATS accounts (core/onemind_core/natsconf.py) proven
// against a real in-process nats-server: testdata/hub-accounts.golden.conf is
// what the gateway renders for nodes aaa111 and bbb222 (core/tests/test_net.py
// checks it byte for byte). The two public keys in it are swapped for keys made
// here, whose seeds the two leaves use. FB-3 lab E2 showed config-file leaf
// users cannot carry permissions; one account per node is the fix it named.
const (
	goldenPubA = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
	goldenPubB = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"
)

type accountsHub struct {
	pki      *pki
	leafPort int
	client   string
	srv      *server.Server
}

func startAccountsHub(t *testing.T, dir, pubA, pubB string) *accountsHub {
	t.Helper()
	golden, err := os.ReadFile(filepath.Join("testdata", "hub-accounts.golden.conf"))
	if err != nil {
		t.Fatal(err)
	}
	acc := strings.NewReplacer(goldenPubA, pubA, goldenPubB, pubB).Replace(string(golden))
	if err := os.WriteFile(filepath.Join(dir, "accounts.conf"), []byte(acc), 0o600); err != nil {
		t.Fatal(err)
	}
	p := newPKI(t, dir, "box")
	cert, key := p.issue(t, "nats-hub", true)
	h := &accountsHub{pki: p, leafPort: freePort(t)}
	cport := freePort(t)
	h.client = fmt.Sprintf("nats://127.0.0.1:%d", cport)
	// The hub nats.conf deploy/install.sh writes, with loopback for the mesh IP.
	conf := filepath.Join(dir, "hub.conf")
	body := fmt.Sprintf(`server_name: hub
listen: "127.0.0.1:%d"
ping_interval: "20s"
ping_max: 2
leafnodes {
  listen: "127.0.0.1:%d"
  tls { cert_file: %q, key_file: %q, ca_file: %q, verify: true, timeout: 5 }
}
include "accounts.conf"
`, cport, h.leafPort, cert, key, p.caFile)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	h.srv = startServer(t, conf)
	return h
}

func startNodeLeaf(t *testing.T, dir, name string, h *accountsHub, seed []byte) string {
	t.Helper()
	nd := filepath.Join(dir, name)
	nkeyFile := filepath.Join(nd, "leaf.nkey")
	if _, err := WriteNkeyFile(nkeyFile, seed); err != nil {
		t.Fatal(err)
	}
	c := &Config{
		ServerName: "node-" + name, Listen: fmt.Sprintf("127.0.0.1:%d", freePort(t)),
		Monitor: fmt.Sprintf("127.0.0.1:%d", freePort(t)), StoreDir: filepath.Join(nd, "store"),
		HubURLs: []string{fmt.Sprintf("tls://127.0.0.1:%d", h.leafPort)}, CAFile: h.pki.caFile, NkeyFile: nkeyFile,
	}
	c.CertFile, c.KeyFile = h.pki.issue(t, "node-"+name, false)
	confPath := filepath.Join(nd, "leaf.conf")
	if _, err := Apply(confPath, c); err != nil {
		t.Fatal(err)
	}
	startServer(t, confPath)
	s := &Supervisor{ConfPath: confPath, Config: c}
	if hh := waitHealth(t, s, StateUp, 10*time.Second); hh.State != StateUp {
		t.Fatalf("leaf %s never connected: %+v", name, hh)
	}
	return "nats://" + c.Listen
}

func TestPerNodeAccountsIsolateNodes(t *testing.T) {
	dir := t.TempDir()
	seedA, pubA := userKey(t)
	seedB, pubB := userKey(t)
	hub := startAccountsHub(t, dir, pubA, pubB)
	leafA := startNodeLeaf(t, dir, "aaa111", hub, seedA)
	leafB := startNodeLeaf(t, dir, "bbb222", hub, seedB)

	// The gateway: a loopback client with no credentials lands in ONEMIND as hub-local.
	gw, err := nats.Connect(hub.client)
	if err != nil {
		t.Fatal(err)
	}
	defer gw.Close()
	got := make(chan string, 64)
	if _, err := gw.Subscribe("onemind.node.*.status", func(m *nats.Msg) { got <- m.Subject + "=" + string(m.Data) }); err != nil {
		t.Fatal(err)
	}
	gw.Flush()

	a, err := nats.Connect(leafA)
	if err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	b, err := nats.Connect(leafB)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()

	// Each node publishes its own status, and A also tries to speak as B.
	seen := map[string]bool{}
	deadline := time.Now().Add(8 * time.Second)
	for !(seen["onemind.node.aaa111.status=from-a"] && seen["onemind.node.bbb222.status=from-b"]) {
		_ = a.Publish("onemind.node.aaa111.status", []byte("from-a"))
		_ = a.Publish("onemind.node.bbb222.status", []byte("spoof-by-a"))
		_ = b.Publish("onemind.node.bbb222.status", []byte("from-b"))
		a.Flush()
		b.Flush()
		select {
		case s := <-got:
			seen[s] = true
		case <-time.After(150 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			t.Fatalf("own statuses did not both reach the hub: %v", seen)
		}
	}
	time.Sleep(300 * time.Millisecond)
	for len(got) > 0 {
		seen[<-got] = true
	}
	if seen["onemind.node.bbb222.status=spoof-by-a"] {
		t.Fatal("node A published as node B and the hub accepted it")
	}

	// Jobs go down to the one node they name, and only to it.
	jobsA := make(chan string, 4)
	if _, err := a.Subscribe("onemind.node.>", func(m *nats.Msg) { jobsA <- m.Subject }); err != nil {
		t.Fatal(err)
	}
	a.Flush()
	deadline = time.Now().Add(8 * time.Second)
	for {
		_ = gw.Publish("onemind.node.aaa111.job.x", []byte("{}"))
		_ = gw.Publish("onemind.node.bbb222.job.x", []byte("{}"))
		gw.Flush()
		select {
		case s := <-jobsA:
			if s != "onemind.node.aaa111.job.x" {
				t.Fatalf("node A received %s", s)
			}
			goto jobsDone
		case <-time.After(150 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			t.Fatal("job never reached node A")
		}
	}
jobsDone:
	time.Sleep(300 * time.Millisecond)
	for len(jobsA) > 0 {
		if s := <-jobsA; s != "onemind.node.aaa111.job.x" {
			t.Fatalf("node A received another node's subject %s", s)
		}
	}
}

func TestNodeKeyIsLeafOnly(t *testing.T) {
	dir := t.TempDir()
	seedA, pubA := userKey(t)
	_, pubB := userKey(t)
	hub := startAccountsHub(t, dir, pubA, pubB)
	// A node's nkey on the client port (not a leaf connection) is refused.
	if nc, err := nats.Connect(hub.client, nats.Nkey(pubA, signerFor(t, seedA))); err == nil {
		nc.Close()
		t.Fatal("a node key must not log in as a normal client")
	}
}

func signerFor(t *testing.T, seed []byte) nats.SignatureHandler {
	t.Helper()
	kp, err := nkeys.FromSeed(seed)
	if err != nil {
		t.Fatal(err)
	}
	return func(nonce []byte) ([]byte, error) { return kp.Sign(nonce) }
}

// A leaf that presents a valid node certificate but no nkey must not fall into
// the hub account through no_auth_user: hub-local is allowed on STANDARD only.
func TestLeafWithoutCredentialsIsRefused(t *testing.T) {
	dir := t.TempDir()
	_, pubA := userKey(t)
	_, pubB := userKey(t)
	hub := startAccountsHub(t, dir, pubA, pubB)
	cert, key := hub.pki.issue(t, "node-anon", false)
	conf := filepath.Join(dir, "anon.conf")
	body := fmt.Sprintf(`server_name: anon
listen: "127.0.0.1:%d"
leafnodes { remotes: [ { urls: ["tls://127.0.0.1:%d"], tls { ca_file: %q, cert_file: %q, key_file: %q } } ] }
`, freePort(t), hub.leafPort, hub.pki.caFile, cert, key)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	startServer(t, conf)
	time.Sleep(2 * time.Second)
	if n := hub.srv.NumLeafNodes(); n != 0 {
		t.Fatalf("hub accepted %d leaf connections without credentials", n)
	}
}
