// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
)

// CORE-SEC-4 (#161): on a strict hub every hub-local client (gateway, onemindd)
// signs in with its own service nkey. testdata/hub-accounts-services.golden.conf
// is what the gateway renders with two nodes and two service keys
// (core/tests/test_nats_service_keys.py checks it byte for byte); the four
// public keys are swapped for keys made here.
const (
	goldenPubGW = "UAIETCIAFQAMTEIL47WBJYZ7OVLKMFPNIJ4P5T6XMGO7EHNVADUNJAAR"
	goldenPubOD = "UC4NBEYQFAATYOQQ7SNT66S4WUDHAPZJ76SYNNSFMH2RXR3A6YESSM3V"
)

func startServicesHub(t *testing.T, dir string, repl ...string) *accountsHub {
	t.Helper()
	golden, err := os.ReadFile(filepath.Join("testdata", "hub-accounts-services.golden.conf"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(golden), "no_auth_user") {
		t.Fatal("a hub with service keys must not have a passwordless user")
	}
	acc := strings.NewReplacer(repl...).Replace(string(golden))
	if err := os.WriteFile(filepath.Join(dir, "accounts.conf"), []byte(acc), 0o600); err != nil {
		t.Fatal(err)
	}
	p := newPKI(t, dir, "box")
	cert, key := p.issue(t, "nats-hub", true)
	h := &accountsHub{pki: p, leafPort: freePort(t)}
	cport := freePort(t)
	h.client = fmt.Sprintf("nats://127.0.0.1:%d", cport)
	conf := filepath.Join(dir, "hub.conf")
	body := fmt.Sprintf(`server_name: hub
listen: "127.0.0.1:%d"
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

func TestServiceKeysRefuseEveryOtherClient(t *testing.T) {
	dir := t.TempDir()
	seedA, pubA := userKey(t)
	_, pubB := userKey(t)
	seedGW, pubGW := userKey(t)
	_, pubOD := userKey(t)
	hub := startServicesHub(t, dir, goldenPubA, pubA, goldenPubB, pubB, goldenPubGW, pubGW, goldenPubOD, pubOD)

	// No credentials: refused (no passwordless hub-local user any more).
	if nc, err := nats.Connect(hub.client); err == nil {
		nc.Close()
		t.Fatal("a client without an nkey was accepted")
	}
	// A valid nkey the hub does not list: refused.
	strangerSeed, _ := userKey(t)
	if nc, err := nats.Connect(hub.client, nats.Nkey(mustPub(t, strangerSeed), signerFor(t, strangerSeed))); err == nil {
		nc.Close()
		t.Fatal("a client with an unknown nkey was accepted")
	}
	// The right public key with a signature from another key: refused.
	if nc, err := nats.Connect(hub.client, nats.Nkey(pubGW, signerFor(t, strangerSeed))); err == nil {
		nc.Close()
		t.Fatal("a forged signature for the gateway's key was accepted")
	}
	// A node's leaf key on the client port: still refused.
	if nc, err := nats.Connect(hub.client, nats.Nkey(pubA, signerFor(t, seedA))); err == nil {
		nc.Close()
		t.Fatal("a node key logged in as a hub-local client")
	}

	// The gateway, from its seed file the way onemindd and nats-py load one, lands in ONEMIND
	// and still hears node A's status through the per-node account.
	seedFile := filepath.Join(dir, "gateway.nk")
	if err := os.WriteFile(seedFile, append(seedGW, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	opt, err := nats.NkeyOptionFromSeed(seedFile)
	if err != nil {
		t.Fatal(err)
	}
	gw, err := nats.Connect(hub.client, opt)
	if err != nil {
		t.Fatalf("the gateway's own service key was refused: %v", err)
	}
	defer gw.Close()
	got := make(chan string, 16)
	if _, err := gw.Subscribe("onemind.node.*.status", func(m *nats.Msg) { got <- m.Subject }); err != nil {
		t.Fatal(err)
	}
	gw.Flush()
	leafA := startNodeLeaf(t, dir, "aaa111", hub, seedA)
	a, err := dialLeaf(leafA)
	if err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	deadline := time.Now().Add(8 * time.Second)
	for {
		_ = a.Publish("onemind.node.aaa111.status", []byte("{}"))
		a.Flush()
		select {
		case s := <-got:
			if s != "onemind.node.aaa111.status" {
				t.Fatalf("unexpected subject %s", s)
			}
			return
		case <-time.After(150 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			t.Fatal("node A's status never reached the gateway on a strict hub")
		}
	}
}

func mustPub(t *testing.T, seed []byte) string {
	t.Helper()
	kp, err := nkeys.FromSeed(seed)
	if err != nil {
		t.Fatal(err)
	}
	pub, _ := kp.PublicKey()
	return pub
}
