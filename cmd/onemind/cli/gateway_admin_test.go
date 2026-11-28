// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func makeBoxCA(t *testing.T) (der []byte, fp string) {
	t.Helper()
	k, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test box CA"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &k.PublicKey, k)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(der)
	return der, hex.EncodeToString(sum[:])
}

// adminHub answers like the routes in routers/identity.py, shares.py, share_links.py, net.py and network.py.
func adminHub(t *testing.T, got *[]string) []byte {
	t.Helper()
	isolate(t)
	der, _ := makeBoxCA(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.RequestURI()+" "+string(body))
		open := r.URL.Path == "/v1/tls/ca.crt"
		if !open && r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.URL.Path == "/v1/instance":
			w.Header().Set("Date", time.Now().UTC().Format(http.TimeFormat))
			jsonOut(w, 200, map[string]any{"name": "box"})
		case r.URL.Path == "/v1/tls/ca.crt":
			if r.URL.Query().Get("format") == "pem" {
				_, _ = w.Write(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))
				return
			}
			_, _ = w.Write(der)
		case r.URL.Path == "/v1/tls":
			jsonOut(w, 200, map[string]any{"ca_sha256": "ab12", "names": []string{"box.local"}, "not_after": "2027-01-01T00:00:00Z", "https": true, "acme": nil})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/auth/sessions":
			jsonOut(w, 200, []map[string]any{{"id": "s1", "principal_id": "zeus", "client": "dashboard", "transport": "cookie",
				"auth_method": "passkey", "created_at": "2026-11-25T01:00:00Z", "last_seen_at": nil, "expires_at": "2026-12-25T01:00:00Z", "current": true}})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/auth/sessions/s1":
			w.WriteHeader(204)
		case r.URL.Path == "/v1/auth/sessions/nope":
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such session"})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/shares/smb":
			jsonOut(w, 200, map[string]any{"service": map[string]any{"available": true}, "people": []any{},
				"shares": []map[string]any{{"id": "sh1", "kind": "timemachine", "person_id": "zeus", "name": "zeus-timemachine", "quota_bytes": 2147483648, "state": "active"}}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/shares/smb/sh1/stop":
			jsonOut(w, 200, map[string]any{"id": "sh1", "state": "stopped"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/actions":
			jsonOut(w, 201, map[string]any{"id": "act-9", "type": "files.share.create", "state": "awaiting_approval"})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/files/shares":
			jsonOut(w, 200, []map[string]any{{"id": "l1", "name": "holiday", "expires_at": "2026-12-01T00:00:00Z"}})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/files/shares/l1":
			jsonOut(w, 202, map[string]any{"id": "frq_revoke", "state": "awaiting_approval"})
		case r.URL.Path == "/v1/network":
			jsonOut(w, 200, map[string]any{"available": true, "interfaces": []map[string]any{{"name": "eth0", "kind": "ethernet", "state": "up",
				"mac": nil, "mtu": 1500, "addresses": []string{"192.0.2.10/24"}, "wifi": nil}},
				"gateways": []map[string]any{{"interface": "eth0", "via": "192.0.2.1", "family": "ipv4"}}, "dns": []string{"192.0.2.1"},
				"ports": []map[string]any{{"proto": "tcp", "addr": "0.0.0.0", "port": 443, "scope": "any"}}, "dropped": 0})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return der
}

func TestSessionsListAndRevoke(t *testing.T) {
	var got []string
	adminHub(t, &got)
	r := run(t, "", false, "sessions", "list")
	if r.code != 0 || !strings.Contains(r.out, "s1") || !strings.Contains(r.out, "passkey") || !strings.Contains(r.out, "this one") {
		t.Fatalf("%+v", r)
	}
	r = run(t, "", false, "--json", "sessions", "list")
	var list []map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &list) != nil || len(list) != 1 {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "sessions", "revoke", "s1"); r.code != 0 || !strings.Contains(r.out, "signed out") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "sessions", "revoke", "nope"); r.code != ExitNotFound {
		t.Fatalf("unknown session must exit not_found: %+v", r)
	}
	if r = run(t, "", false, "--json", "sessions", "revoke", "s1"); !strings.Contains(r.out, `"revoked": "s1"`) {
		t.Fatalf("%+v", r)
	}
}

func TestSharesListStopAndLinks(t *testing.T) {
	var got []string
	adminHub(t, &got)
	r := run(t, "", false, "shares", "list")
	if r.code != 0 || !strings.Contains(r.out, "zeus-timemachine") || !strings.Contains(r.out, "2.0GiB") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "--json", "shares", "list"); r.code != 0 || !strings.Contains(r.out, `"shares"`) {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "shares", "stop", "sh1"); r.code != 0 || !strings.Contains(got[len(got)-1], "POST /v1/shares/smb/sh1/stop") {
		t.Fatalf("%+v %v", r, got)
	}
	if r = run(t, "", false, "shares", "links", "list"); r.code != 0 || !strings.Contains(r.out, "holiday") {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "shares", "links", "revoke", "l1"); r.code != 0 ||
		!strings.Contains(r.out, "Requested end share link l1") || !strings.Contains(r.out, "frq_revoke") {
		t.Fatalf("%+v", r)
	}
}

func TestSharesAddFilesAnActionAndNeverApproves(t *testing.T) {
	var got []string
	adminHub(t, &got)
	r := run(t, "", false, "--json", "shares", "add", "zeus", "--kind", "timemachine", "--quota-gib", "2")
	if r.code != 0 || !strings.Contains(r.out, "awaiting_approval") {
		t.Fatalf("%+v", r)
	}
	var posted string
	for _, g := range got {
		if strings.HasPrefix(g, "POST /v1/actions ") {
			posted = g
		}
		if strings.Contains(g, "/approve") {
			t.Fatalf("the CLI must only request: %v", got)
		}
	}
	for _, want := range []string{`"type":"files.share.create"`, `"person_id":"zeus"`, `"kind":"timemachine"`, `"quota_bytes":2147483648`, `"expires_at"`, `"idempotency_key"`} {
		if !strings.Contains(posted, want) {
			t.Fatalf("missing %s in %s", want, posted)
		}
	}
	if r = run(t, "", false, "shares", "add", "zeus"); r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") {
		t.Fatalf("home share: %+v", r)
	}
	for _, bad := range [][]string{{"--kind", "timemachine"}, {"--kind", "home", "--quota-gib", "5"}, {"--kind", "nfs"}} {
		if r = run(t, "", false, append([]string{"shares", "add", "zeus"}, bad...)...); r.code != ExitUsage {
			t.Fatalf("%v must be a usage error: %+v", bad, r)
		}
	}
}

func TestTLSShowAndCADownload(t *testing.T) {
	var got []string
	der := adminHub(t, &got)
	sum := sha256.Sum256(der)
	fp := hex.EncodeToString(sum[:])
	if r := run(t, "", false, "tls", "show"); r.code != 0 || !strings.Contains(r.out, "box.local") || !strings.Contains(r.out, "ab12") {
		t.Fatalf("%+v", r)
	}
	out := filepath.Join(t.TempDir(), "ca.pem")
	r := run(t, "", false, "tls", "ca", "-o", out, "--pin", fp)
	if r.code != 0 || !strings.Contains(r.out, fp) {
		t.Fatalf("%+v", r)
	}
	b, _ := os.ReadFile(out)
	if blk, _ := pem.Decode(b); blk == nil || string(blk.Bytes) != string(der) {
		t.Fatalf("the saved file is not the box CA")
	}
	bad := filepath.Join(t.TempDir(), "bad.pem")
	if r = run(t, "", false, "tls", "ca", "-o", bad, "--pin", strings.Repeat("0", 64)); r.code == 0 {
		t.Fatalf("a wrong pin must fail: %+v", r)
	}
	if _, err := os.Stat(bad); err == nil {
		t.Fatalf("a certificate that fails its pin must not be saved")
	}
	if r = run(t, "", false, "--json", "tls", "ca", "--der", "-o", filepath.Join(t.TempDir(), "ca.crt")); r.code != 0 || !strings.Contains(r.out, fp) {
		t.Fatalf("%+v", r)
	}
	if r = run(t, "", false, "tls", "ca", "--der"); r.code != ExitUsage {
		t.Fatalf("binary to a terminal needs -o: %+v", r)
	}
	if r = run(t, "", false, "tls", "ca"); r.code != 0 || !strings.Contains(r.out, "BEGIN CERTIFICATE") || !strings.Contains(r.errOut, fp) {
		t.Fatalf("%+v", r)
	}
}

func TestNetworkShow(t *testing.T) {
	var got []string
	adminHub(t, &got)
	r := run(t, "", false, "network", "show")
	for _, want := range []string{"eth0", "192.0.2.10/24", "gateway (ipv4): 192.0.2.1 via eth0", "dns: 192.0.2.1", "443"} {
		if r.code != 0 || !strings.Contains(r.out, want) {
			t.Fatalf("missing %q: %+v", want, r)
		}
	}
	r = run(t, "", false, "--json", "network", "show")
	var v map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || v["available"] != true {
		t.Fatalf("%+v", r)
	}
	t.Setenv("ONEMIND_TOKEN", "wrong-token-0123456789abcdef")
	if r = run(t, "", false, "network", "show"); r.code != ExitUnauthenticated {
		t.Fatalf("%+v", r)
	}
}
