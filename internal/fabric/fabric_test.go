// SPDX-License-Identifier: Apache-2.0

package fabric

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/mesh"
)

// Every key and certificate here is made when the test runs.

type testCA struct {
	cert *x509.Certificate
	key  *ecdsa.PrivateKey
	pin  string
}

func newCA(t *testing.T) *testCA {
	t.Helper()
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "OneMind box1 CA"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(24 * time.Hour), IsCA: true,
		BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign, PermittedDNSDomains: []string{"box1.local", "onemind.internal"}}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	c, _ := x509.ParseCertificate(der)
	sum := sha256.Sum256(der)
	return &testCA{cert: c, key: key, pin: hex.EncodeToString(sum[:])}
}

func (ca *testCA) sign(t *testing.T, pub any, tmpl *x509.Certificate) *x509.Certificate {
	t.Helper()
	tmpl.SerialNumber, _ = rand.Int(rand.Reader, big.NewInt(1<<62))
	tmpl.NotBefore, tmpl.NotAfter = time.Now().Add(-time.Hour), time.Now().Add(24*time.Hour)
	der, err := x509.CreateCertificate(rand.Reader, tmpl, ca.cert, pub, ca.key)
	if err != nil {
		t.Fatal(err)
	}
	c, _ := x509.ParseCertificate(der)
	return c
}

func pemOf(c *x509.Certificate) string {
	return string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: c.Raw}))
}

// fakeHub is the gateway's join routes, as far as the node can tell.
type fakeHub struct {
	t        *testing.T
	ca       *testCA
	mu       sync.Mutex
	csrPub   *ecdsa.PublicKey
	nkey     string
	polls    int
	approved bool
	gotFacts NodeFacts
	role     string
}

func (h *fakeHub) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	h.mu.Lock()
	defer h.mu.Unlock()
	switch {
	case r.Method == http.MethodPost && r.URL.Path == "/v1/fabric/join-requests":
		var body struct {
			Code string    `json:"join_code"`
			Node NodeFacts `json:"node"`
			CSR  string    `json:"csr_pem"`
			Nkey string    `json:"nats_pubkey"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body.Code != "7KQ4-M2XP-9D3F" {
			w.WriteHeader(401)
			w.Write([]byte(`{"error":"unauthenticated","message":"unknown join code","reason":"code_unknown"}`))
			return
		}
		blk, _ := pem.Decode([]byte(body.CSR))
		csr, err := x509.ParseCertificateRequest(blk.Bytes)
		if err != nil || csr.CheckSignature() != nil {
			w.WriteHeader(422)
			return
		}
		h.csrPub, h.nkey, h.gotFacts = csr.PublicKey.(*ecdsa.PublicKey), body.Nkey, body.Node
		w.WriteHeader(202)
		fmt.Fprintf(w, `{"join_request_id":"jr_1","match_code":"K7-4QX","role":%q,"poll":"/v1/fabric/join-requests/jr_1"}`, h.role)
	case r.Method == http.MethodGet && r.URL.Path == "/v1/fabric/join-requests/jr_1":
		sig, _ := base64.StdEncoding.DecodeString(r.Header.Get("OneMind-Join-Proof"))
		sum := sha256.Sum256([]byte(PollContext + "jr_1"))
		if r.Header.Get("OneMind-Join-Code") != "7KQ4-M2XP-9D3F" || !ecdsa.VerifyASN1(h.csrPub, sum[:], sig) {
			w.WriteHeader(401)
			w.Write([]byte(`{"error":"unauthenticated","message":"bad proof"}`))
			return
		}
		h.polls++
		if h.polls < 2 {
			w.Write([]byte(`{"state":"awaiting_approval","match_code":"K7-4QX"}`))
			return
		}
		if h.approved {
			w.Write([]byte(`{"state":"delivered","match_code":"K7-4QX"}`))
			return
		}
		h.approved = true
		cert := h.ca.sign(h.t, h.csrPub, &x509.Certificate{Subject: pkix.Name{CommonName: "node-n1"},
			DNSNames: []string{"node-n1.onemind.internal"}, KeyUsage: x509.KeyUsageDigitalSignature,
			ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth}})
		cr := map[string]any{
			"role": h.role, "node_cert": pemOf(cert), "ca_cert": pemOf(h.ca.cert),
			"nats": map[string]string{"url": "tls://100.64.0.1:7422", "account": "NODE_n1", "user_pubkey": h.nkey},
			"mesh": map[string]any{"control_url": "https://control.onemind.internal:8444", "control_addrs": []string{"192.0.2.10"},
				"ca_sha256": h.ca.pin, "auth_key": "hskey-auth-test-only", "hostname": "node-n1", "hub_mesh_ip": "100.64.0.1",
				"tags": []string{"tag:onemind-worker", "tag:onemind-k3s"}},
			"k3s": map[string]string{"server_url": "https://100.64.0.1:6443", "token": "K10" + strings.Repeat("ab", 32) + "::abcdef.0123456789abcdef"},
		}
		json.NewEncoder(w).Encode(map[string]any{"state": "delivered", "match_code": "K7-4QX", "credentials": cr})
	default:
		w.WriteHeader(404)
	}
}

func startHub(t *testing.T, role string) (*fakeHub, string, string) {
	t.Helper()
	ca := newCA(t)
	skey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	scert := ca.sign(t, &skey.PublicKey, &x509.Certificate{DNSNames: []string{"box1.local"},
		KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}})
	h := &fakeHub{t: t, ca: ca, role: role}
	srv := httptest.NewUnstartedServer(h)
	srv.TLS = &tls.Config{Certificates: []tls.Certificate{{Certificate: [][]byte{scert.Raw, ca.cert.Raw}, PrivateKey: skey}}}
	srv.StartTLS()
	t.Cleanup(srv.Close)
	_, port, _ := net.SplitHostPort(srv.Listener.Addr().String())
	return h, "https://box1.local:" + port, "127.0.0.1"
}

// fakeTS is the tailscale CLI: logged out until `up` runs with a key file.
type fakeTS struct {
	mu     sync.Mutex
	up     bool
	upArgs []string
	keyRd  string
}

func (f *fakeTS) Run(_ context.Context, args ...string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	switch args[0] {
	case "status":
		if f.up {
			return []byte(`{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.7"]},"Peer":{}}`), nil
		}
		return []byte(`{"BackendState":"NeedsLogin"}`), nil
	case "up":
		f.upArgs = args
		for _, a := range args {
			if p, ok := strings.CutPrefix(a, "--auth-key=file:"); ok {
				b, _ := os.ReadFile(p)
				f.keyRd = string(b)
			}
		}
		f.up = true
	}
	return nil, nil
}

type fakeSys struct{ calls []string }

func (s *fakeSys) Systemctl(_ context.Context, args ...string) error {
	s.calls = append(s.calls, strings.Join(args, " "))
	return nil
}
func (s *fakeSys) Chown(string, string) error { return nil }

func TestParseQR(t *testing.T) {
	pin := strings.Repeat("a1", 32)
	tk, err := ParseQR("onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=" + pin + "&role=leaf&hub=https%3A%2F%2Fbox1.local")
	if err != nil || tk.Code != "7KQ4-M2XP-9D3F" || tk.Role != "leaf" || tk.Hub != "https://box1.local" || tk.CASHA != pin {
		t.Fatalf("%+v %v", tk, err)
	}
	for _, bad := range []string{
		"https://example.org",
		"onemind-join:v1?code=x&ca=" + pin + "&hub=https%3A%2F%2Fbox1.local",
		"onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=short&hub=https%3A%2F%2Fbox1.local",
		"onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=" + pin + "&hub=http%3A%2F%2Fbox1.local",
		"onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=" + pin + "&role=hub&hub=https%3A%2F%2Fbox1.local",
	} {
		if _, err := ParseQR(bad); err == nil {
			t.Errorf("accepted %q", bad)
		}
	}
}

func TestJoinEndToEnd(t *testing.T) {
	hub, hubURL, addr := startHub(t, "worker")
	id, err := NewIdentity("n1", "mini-pc")
	if err != nil {
		t.Fatal(err)
	}
	hc, _ := PinnedClient(hub.ca.pin, "box1.local", addr, 10*time.Second)
	c := &Client{HTTP: hc, Hub: hubURL}
	ctx := context.Background()
	if _, err := c.Request(ctx, "AAAA-BBBB-CCCC", id, NodeFacts{NodeID: "n1"}); err == nil || !strings.Contains(err.Error(), "code_unknown") {
		t.Fatalf("wrong code: %v", err)
	}
	acc, err := c.Request(ctx, "7KQ4-M2XP-9D3F", id, NodeFacts{NodeID: "n1", Hostname: "mini-pc", Board: "vm", Arch: "arm64"})
	if err != nil || acc.MatchCode != "K7-4QX" || hub.gotFacts.Hostname != "mini-pc" {
		t.Fatalf("%+v %v", acc, err)
	}
	cr, err := c.Wait(ctx, "7KQ4-M2XP-9D3F", id, acc.RequestID, 10*time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := cr.Check(id, hub.ca.pin)
	if err != nil {
		t.Fatal(err)
	}
	// a second collection is refused by the hub (credentials come once)
	if _, err := c.Wait(ctx, "7KQ4-M2XP-9D3F", id, acc.RequestID, time.Millisecond); err == nil {
		t.Fatal("second collection accepted")
	}

	root := t.TempDir()
	os.MkdirAll(filepath.Join(root, "etc"), 0o755)
	os.WriteFile(filepath.Join(root, HostsFile), []byte("127.0.0.1 localhost\n"), 0o644)
	os.MkdirAll(filepath.Join(root, "etc/onemind"), 0o755)
	os.WriteFile(filepath.Join(root, OnemindEnv), []byte("ONEMIND_NATS_URL=nats://old:4222\nONEMIND_NODE_ROLE=node\nOTHER=1\n"), 0o644)
	ts, sys := &fakeTS{}, &fakeSys{}
	var out bytes.Buffer
	in := &Installer{Root: root, Sys: sys, Mesh: &mesh.Client{Runner: ts, Now: time.Now}, Out: &out, EnrollTimeout: 5 * time.Second}
	tk := &Ticket{Code: "7KQ4-M2XP-9D3F", CASHA: hub.ca.pin, Role: "worker", Hub: "https://box1.local"}
	st, err := in.Apply(ctx, id, cr, cert, tk, addr)
	if err != nil {
		t.Fatalf("%v\n%s", err, out.String())
	}
	if st.MeshAddr != "100.64.0.7" || st.Role != "worker" {
		t.Fatalf("%+v", st)
	}
	// the one-time key went through a file that is gone now, never argv
	if ts.keyRd != "hskey-auth-test-only" || strings.Contains(strings.Join(ts.upArgs, " "), "hskey-auth") {
		t.Fatalf("key handling: read %q args %v", ts.keyRd, ts.upArgs)
	}
	if !contains(ts.upArgs, "--login-server=https://control.onemind.internal:8444") || !contains(ts.upArgs, "--hostname=node-n1") {
		t.Fatalf("tailscale up args %v", ts.upArgs)
	}
	read := func(rel string) string { b, _ := os.ReadFile(filepath.Join(root, rel)); return string(b) }
	mode := func(rel string) os.FileMode { fi, _ := os.Stat(filepath.Join(root, rel)); return fi.Mode().Perm() }
	if mode(IdentityDir+"/node.key") != 0o600 || mode(NATSDir+"/leaf.nkey") != 0o600 || mode(K3sConfig) != 0o600 {
		t.Fatal("secret files must be 0600")
	}
	hosts := read(HostsFile)
	if !strings.Contains(hosts, "127.0.0.1 localhost") || !strings.Contains(hosts, "192.0.2.10 control.onemind.internal join.onemind.internal") {
		t.Fatalf("hosts:\n%s", hosts)
	}
	leafConf := read(NATSDir + "/leaf.conf")
	for _, want := range []string{`urls: ["tls://100.64.0.1:7422"]`, `server_name: "node-n1"`, "ca_file", "cert_file", `include "leaf.nkey"`} {
		if !strings.Contains(leafConf, want) {
			t.Errorf("leaf.conf missing %q:\n%s", want, leafConf)
		}
	}
	if strings.Contains(leafConf, string(id.NkeySeed)) {
		t.Fatal("seed inside leaf.conf")
	}
	k3s := read(K3sConfig)
	for _, want := range []string{`server: "https://100.64.0.1:6443"`, `node-ip: "100.64.0.7"`, `flannel-iface: "tailscale0"`} {
		if !strings.Contains(k3s, want) {
			t.Errorf("k3s config missing %q:\n%s", want, k3s)
		}
	}
	env := read(OnemindEnv)
	if !strings.Contains(env, "ONEMIND_NATS_URL=nats://127.0.0.1:4222") || strings.Contains(env, "nats://old") || !strings.Contains(env, "OTHER=1") {
		t.Fatalf("env:\n%s", env)
	}
	if got := strings.Join(sys.calls, "; "); !strings.Contains(got, "restart tailscaled.service") ||
		!strings.Contains(got, "enable --now onemind-nats-leaf.service") || !strings.Contains(got, "restart onemindd.service") {
		t.Fatalf("systemctl calls: %s", got)
	}
	// re-running rewrites the managed hosts block, never duplicates it
	if err := in.setHosts("192.0.2.11"); err != nil {
		t.Fatal(err)
	}
	if h := read(HostsFile); strings.Count(h, hostsBegin) != 1 || strings.Contains(h, "192.0.2.10") {
		t.Fatalf("hosts:\n%s", h)
	}
	if s, err := LoadState(root); err != nil || s.NodeID != "n1" {
		t.Fatalf("%+v %v", s, err)
	}
}

func TestPinRefusesAnotherCA(t *testing.T) {
	_, hubURL, addr := startHub(t, "leaf")
	other := newCA(t)
	hc, _ := PinnedClient(other.pin, "box1.local", addr, 5*time.Second)
	id, _ := NewIdentity("n1", "x")
	_, err := (&Client{HTTP: hc, Hub: hubURL}).Request(context.Background(), "7KQ4-M2XP-9D3F", id, NodeFacts{NodeID: "n1"})
	if err == nil || !strings.Contains(err.Error(), "box CA") {
		t.Fatalf("a hub with another CA was accepted: %v", err)
	}
	// right CA, wrong name: the leaf certificate is for box1.local only
	hub2, hubURL2, _ := startHub(t, "leaf")
	hc2, _ := PinnedClient(hub2.ca.pin, "elsewhere.local", addr, 5*time.Second)
	_, err = (&Client{HTTP: hc2, Hub: strings.Replace(hubURL2, "box1.local", "elsewhere.local", 1)}).Request(
		context.Background(), "7KQ4-M2XP-9D3F", id, NodeFacts{NodeID: "n1"})
	if err == nil {
		t.Fatal("a certificate for another name was accepted")
	}
}

func TestCheckRefusesForeignCredentials(t *testing.T) {
	ca := newCA(t)
	id, _ := NewIdentity("n1", "x")
	other, _ := NewIdentity("n2", "y")
	cert := ca.sign(t, &other.Key.PublicKey, &x509.Certificate{ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}})
	cr := &Credentials{NodeCert: pemOf(cert), CACert: pemOf(ca.cert)}
	cr.NATS.UserPubkey = id.NkeyPub
	if _, err := cr.Check(id, ca.pin); err == nil {
		t.Fatal("a certificate for another key was accepted")
	}
	if _, err := cr.Check(id, strings.Repeat("0", 64)); err == nil {
		t.Fatal("an unpinned CA was accepted")
	}
	// A certificate with a key of another type is refused, not a panic (review finding).
	edPub, _, _ := ed25519.GenerateKey(rand.Reader)
	cr.NodeCert = pemOf(ca.sign(t, edPub, &x509.Certificate{ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}}))
	if _, err := cr.Check(id, ca.pin); err == nil {
		t.Fatal("an Ed25519 certificate was accepted")
	}
}

func contains(list []string, s string) bool {
	for _, v := range list {
		if v == s {
			return true
		}
	}
	return false
}
