// SPDX-License-Identifier: Apache-2.0

package relay

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const hubName = "control.example.com"

// startHub is a stand-in hub: a TLS server whose certificate only the hub holds.
func startHub(t *testing.T) (addr string, pool *x509.CertPool) {
	t.Helper()
	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "hub says hello")
	}))
	srv.StartTLS()
	t.Cleanup(srv.Close)
	pool = x509.NewCertPool()
	pool.AddCert(srv.Certificate())
	return srv.Listener.Addr().String(), pool
}

func startRelay(t *testing.T, routes ...Route) (string, *Router) {
	t.Helper()
	cfg := &Config{Listen: ":443", Routes: routes}
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}
	rt := NewRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)))
	rt.HelloTimeout = time.Second
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go rt.Serve(ctx, ln)
	return ln.Addr().String(), rt
}

func TestRelayPassesEncryptedTrafficToTheHubWithoutTerminatingTLS(t *testing.T) {
	hub, pool := startHub(t)
	relayAddr, rt := startRelay(t, Route{Name: hubName, Upstream: hub})
	// The client verifies the HUB's certificate through the relay: the relay holds no key.
	c := &http.Client{Transport: &http.Transport{
		TLSClientConfig: &tls.Config{RootCAs: pool, ServerName: hubName},
		DialContext: func(ctx context.Context, n, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, n, relayAddr)
		},
	}}
	resp, err := c.Get("https://" + hubName + "/")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if string(body) != "hub says hello" {
		t.Fatalf("body %q", body)
	}
	if a, d := rt.Counts(); a != 1 || d != 0 {
		t.Fatalf("accepted=%d denied=%d", a, d)
	}
}

func denied(t *testing.T, relayAddr string, cfg *tls.Config) {
	t.Helper()
	c, err := tls.DialWithDialer(&net.Dialer{Timeout: 2 * time.Second}, "tcp", relayAddr, cfg)
	if err == nil {
		c.Close()
		t.Fatal("handshake succeeded; the relay must close it")
	}
}

func TestRelayClosesUnknownNamesMissingNamesAndNonTLS(t *testing.T) {
	hub, _ := startHub(t)
	relayAddr, rt := startRelay(t, Route{Name: hubName, Upstream: hub})
	insecure := func(name string) *tls.Config { return &tls.Config{InsecureSkipVerify: true, ServerName: name} }
	denied(t, relayAddr, insecure("dashboard.example.com"))
	denied(t, relayAddr, insecure("")) // an IP-literal dial sends no name
	denied(t, relayAddr, insecure("CONTROL.example.test.evil.test"))

	raw, err := net.Dial("tcp", relayAddr) // plain HTTP, no TLS at all
	if err != nil {
		t.Fatal(err)
	}
	defer raw.Close()
	io.WriteString(raw, "GET / HTTP/1.1\r\nHost: control.example.com\r\n\r\n")
	raw.SetReadDeadline(time.Now().Add(2 * time.Second))
	if n, _ := raw.Read(make([]byte, 16)); n != 0 {
		t.Fatal("the relay answered a non-TLS client")
	}
	time.Sleep(50 * time.Millisecond)
	if a, d := rt.Counts(); a != 0 || d < 4 {
		t.Fatalf("accepted=%d denied=%d", a, d)
	}
}

func TestRelayWithAnUnreachableUpstreamClosesInsteadOfHanging(t *testing.T) {
	dead, _ := net.Listen("tcp", "127.0.0.1:0")
	addr := dead.Addr().String()
	dead.Close()
	relayAddr, _ := startRelay(t, Route{Name: hubName, Upstream: addr})
	denied(t, relayAddr, &tls.Config{InsecureSkipVerify: true, ServerName: hubName})
}

func TestPeekServerNameReturnsTheBytesItRead(t *testing.T) {
	a, b := net.Pipe()
	defer a.Close()
	go func() {
		tls.Client(b, &tls.Config{ServerName: "x.example.test", InsecureSkipVerify: true}).Handshake()
		b.Close()
	}()
	name, read, err := PeekServerName(a, time.Second)
	if err != nil || name != "x.example.test" {
		t.Fatalf("name=%q err=%v", name, err)
	}
	if len(read) < 40 || read[0] != 0x16 {
		t.Fatalf("expected the raw ClientHello record, got %d bytes", len(read))
	}
}

func TestPairingRoundTripAndRefusals(t *testing.T) {
	code, err := NewCode()
	if err != nil {
		t.Fatal(err)
	}
	p := Pairing{Addr: "203.0.113.7", FP: strings.Repeat("ab", 32), Code: code}
	got, err := ParsePairing(p.String())
	if err != nil || got != p {
		t.Fatalf("got %+v err %v", got, err)
	}
	for _, bad := range []string{
		"", "https://example.test", "onemind-relay:v1?addr=" + strings.Join([]string{"10", "0", "0", "5"}, ".") + "&fp=" + p.FP + "&code=" + code, // private address
		"onemind-relay:v1?addr=203.0.113.7&fp=zz&code=" + code,
		"onemind-relay:v1?addr=203.0.113.7&fp=" + p.FP + "&code=short",
	} {
		if _, err := ParsePairing(bad); err == nil {
			t.Errorf("accepted %q", bad)
		} else if strings.Contains(err.Error(), code) {
			t.Errorf("error leaks the code: %v", err)
		}
	}
}

func TestCodeIsStoredHashedAndComparedExactly(t *testing.T) {
	code, _ := NewCode()
	h := HashCode(code)
	if strings.Contains(h, code) || !CodeMatches(strings.ToLower(code), h) || CodeMatches(code+"A", h) || CodeMatches(code, "nothex") {
		t.Fatal("code hashing is wrong")
	}
}

func TestConfigRefusesAnythingBeyondExactNamedRoutes(t *testing.T) {
	ok := Route{Name: hubName, Upstream: "192.0.2.1:8444"}
	cases := map[string]Config{
		"no routes":  {Listen: ":443"},
		"wildcard":   {Listen: ":443", Routes: []Route{{Name: "*.example.test", Upstream: "192.0.2.1:1"}}},
		"bare label": {Listen: ":443", Routes: []Route{{Name: "localhost", Upstream: "192.0.2.1:1"}}},
		"duplicate":  {Listen: ":443", Routes: []Route{ok, ok}},
		"no port":    {Listen: ":443", Routes: []Route{{Name: hubName, Upstream: "192.0.2.1"}}},
		"bad listen": {Listen: "443", Routes: []Route{ok}},
		"too many":   {Listen: ":443", Routes: []Route{ok, ok, ok, ok, ok, ok, ok, ok, ok}},
	}
	for name, c := range cases {
		if c.Validate() == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	if err := (&Config{Listen: ":443", Routes: []Route{ok}}).Validate(); err != nil {
		t.Fatal(err)
	}
}

func TestInitWritesAPrivateConfigPrintsPairingOnceAndRefusesToRepeat(t *testing.T) {
	path := filepath.Join(t.TempDir(), "relay", "config.json")
	var out bytes.Buffer
	args := []string{"--addr", "203.0.113.7", "--route", hubName + "=192.0.2.1:8444", "--config", path}
	if err := cliInit(args, &out); err != nil {
		t.Fatal(err)
	}
	line := out.String()[strings.Index(out.String(), PairingScheme):]
	p, err := ParsePairing(line)
	if err != nil {
		t.Fatal(err)
	}
	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(path)
	if strings.Contains(string(raw), p.Code) || !CodeMatches(p.Code, cfg.CodeHash) || cfg.SetupFP != p.FP {
		t.Fatal("config must hold the code's hash only, and the pairing fingerprint")
	}
	if st, _ := os.Stat(path); st.Mode().Perm() != 0o600 {
		t.Fatalf("mode %v", st.Mode())
	}
	if err := cliInit(args, io.Discard); err == nil {
		t.Fatal("init ran twice")
	}
}

func TestStatusSaysPlainlyWhenThisMachineIsNotARelay(t *testing.T) {
	var out bytes.Buffer
	if err := cliStatus([]string{"--config", filepath.Join(t.TempDir(), "none.json")}, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "not a relay") {
		t.Fatal(out.String())
	}
}
