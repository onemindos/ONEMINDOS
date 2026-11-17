// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// testCA makes a throwaway CA (in memory, never written) and a server certificate it signed for
// 127.0.0.1. Test data only.
func testCA(t *testing.T) (caPEM []byte, server tls.Certificate) {
	t.Helper()
	caKey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	caTpl := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "onemind-sdk-test-ca"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTpl, caTpl, &caKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	caCert, _ := x509.ParseCertificate(caDER)
	leafKey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	leafTpl := &x509.Certificate{
		SerialNumber: big.NewInt(2), Subject: pkix.Name{CommonName: "gateway"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		IPAddresses: []net.IP{net.ParseIP("127.0.0.1")}, KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leafTpl, caCert, &leafKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}),
		tls.Certificate{Certificate: [][]byte{leafDER}, PrivateKey: leafKey}
}

func tlsGateway(t *testing.T, cert tls.Certificate) string {
	t.Helper()
	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `[{"node_id":"abc","status":"online","last_seen":"t"}]`)
	}))
	srv.TLS = &tls.Config{Certificates: []tls.Certificate{cert}}
	srv.StartTLS()
	t.Cleanup(srv.Close)
	return srv.URL
}

func TestFromEnvTrustsGatewayCA(t *testing.T) {
	caPEM, cert := testCA(t)
	url := tlsGateway(t, cert)
	t.Setenv("ONEMIND_HUB", "")
	t.Setenv("ONEMIND_GATEWAY_URL", url)
	t.Setenv("ONEMIND_AGENT_TOKEN", token)

	// Without the CA the box's certificate is rejected: verification is on.
	t.Setenv("ONEMIND_GATEWAY_CA", "")
	c, err := FromEnv(WithRetries(1))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := c.Nodes.List(context.Background()); err == nil {
		t.Fatal("an unknown CA must be rejected")
	}

	// With it, the same gateway verifies.
	t.Setenv("ONEMIND_GATEWAY_CA", string(caPEM))
	c, err = FromEnv(WithRetries(1))
	if err != nil {
		t.Fatal(err)
	}
	nodes, err := c.Nodes.List(context.Background())
	if err != nil || len(nodes) != 1 {
		t.Fatalf("nodes=%v err=%v", nodes, err)
	}
	cfg := c.http.Transport.(*http.Transport).TLSClientConfig
	if cfg.MinVersion != tls.VersionTLS12 || cfg.InsecureSkipVerify {
		t.Fatalf("TLS config weakened: %+v", cfg)
	}

	// Another CA does not verify it (the system roots are not added).
	other, _ := testCA(t)
	t.Setenv("ONEMIND_GATEWAY_CA", string(other))
	c, _ = FromEnv(WithRetries(1))
	if _, err := c.Nodes.List(context.Background()); err == nil {
		t.Fatal("a different CA must not verify the gateway")
	}
}

func TestFromEnvRejectsMalformedGatewayCA(t *testing.T) {
	t.Setenv("ONEMIND_HUB", "")
	t.Setenv("ONEMIND_GATEWAY_URL", "https://gw.example.test:8443")
	t.Setenv("ONEMIND_GATEWAY_CA", "not a pem")
	if _, err := FromEnv(); err == nil || !strings.Contains(err.Error(), "gateway CA") {
		t.Fatalf("want a CA error, got %v", err)
	}
}
