// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const (
	sshFP  = "SHA256:Sm3mEwGWtcN5uE/w5uJvL4hEW37jBLnA2WL/97w+ods"
	sshID  = "Sm3mEwGWtcN5uE_w5uJvL4hEW37jBLnA2WL_97w-ods"
	sshPub = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGexample alex@laptop"
)

// sshHub answers like core/onemind_core/routers/ssh.py: the list, and every change filed as an action
// awaiting approval (202). It records each call.
// sshLastIdem is the Idempotency-Key header of the last call sshHub saw.
var sshLastIdem string

func sshHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.EscapedPath()+" "+string(body))
		sshLastIdem = r.Header.Get("Idempotency-Key")
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/ssh/keys":
			jsonOut(w, 200, map[string]any{"keys": []map[string]any{{"id": sshID, "fingerprint": sshFP, "type": "ed25519", "bits": 256, "comment": "alex@laptop\x1b[31m"}}})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/ssh":
			jsonOut(w, 200, map[string]any{"service": map[string]any{"state": "on", "user": "admin", "port": 22, "rate_limit": "6 new connections a minute per address"},
				"keys": []map[string]any{{"id": sshID}}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/ssh/keys":
			jsonOut(w, 202, map[string]any{"id": "act-ssh-1", "type": "ssh.key.add", "state": "awaiting_approval"})
		case r.Method == http.MethodDelete && strings.HasPrefix(r.URL.Path, "/v1/ssh/keys/"):
			jsonOut(w, 202, map[string]any{"id": "act-ssh-2", "type": "ssh.key.remove", "state": "awaiting_approval"})
		case r.Method == http.MethodPut && r.URL.Path == "/v1/ssh":
			jsonOut(w, 202, map[string]any{"id": "act-ssh-3", "type": "ssh.toggle", "state": "awaiting_approval"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func pubFile(t *testing.T, content string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "id.pub")
	if err := os.WriteFile(p, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestSSHKeyListStripsControlCharacters(t *testing.T) {
	var got []string
	sshHub(t, &got)
	r := run(t, "", false, "ssh-key", "list")
	if r.code != 0 || !strings.Contains(r.out, sshFP) || !strings.Contains(r.out, "ed25519") || strings.Contains(r.out, "\x1b") {
		t.Fatalf("%+v", r)
	}
	r = run(t, "", false, "--json", "ssh-key", "list")
	if r.code != 0 || !strings.Contains(r.out, `"fingerprint"`) {
		t.Fatalf("%+v", r)
	}
}

func TestSSHKeyAddFilesARequestAndNeverApproves(t *testing.T) {
	var got []string
	sshHub(t, &got)
	r := run(t, "", false, "ssh-key", "add", pubFile(t, "# my laptop\n\n"+sshPub+"\n"), "--label", "Laptop", "--reason", "new laptop")
	if r.code != 0 || !strings.Contains(r.out, "act-ssh-1") || !strings.Contains(r.out, "passkey") {
		t.Fatalf("%+v", r)
	}
	if len(got) != 1 || !strings.HasPrefix(got[0], "POST /v1/ssh/keys ") || !strings.Contains(got[0], `"public_key":"`+sshPub+`"`) ||
		!strings.Contains(got[0], `"label":"Laptop"`) || !strings.Contains(got[0], `"idempotency_key":"cli-`) {
		t.Fatalf("asked %v", got)
	}
	for _, g := range got {
		if strings.Contains(g, "approve") {
			t.Fatalf("the CLI never approves: %v", got)
		}
	}
}

func TestSSHKeyAddReadsStdinAndRefusesAPrivateKey(t *testing.T) {
	var got []string
	sshHub(t, &got)
	if r := run(t, sshPub+"\n", false, "--json", "ssh-key", "add", "-"); r.code != 0 || !strings.Contains(r.out, `"awaiting_approval"`) {
		t.Fatalf("%+v", r)
	}
	n := len(got)
	r := run(t, "", false, "ssh-key", "add", pubFile(t, "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\n"))
	if r.code != ExitUsage || len(got) != n {
		t.Fatalf("a private key must be refused before any request: %+v %v", r, got)
	}
	if r := run(t, "", false, "ssh-key", "add", pubFile(t, "\n# nothing\n")); r.code != ExitUsage {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "ssh-key", "add", filepath.Join(t.TempDir(), "missing.pub")); r.code != ExitUsage {
		t.Fatalf("%+v", r)
	}
}

func TestSSHKeyRmTurnsAFingerprintIntoTheRouteID(t *testing.T) {
	var got []string
	sshHub(t, &got)
	for _, arg := range []string{sshFP, sshID} {
		got = nil
		r := run(t, "", false, "ssh-key", "rm", arg)
		if r.code != 0 || !strings.Contains(r.out, "act-ssh-2") {
			t.Fatalf("%s: %+v", arg, r)
		}
		if len(got) != 1 || got[0] != "DELETE /v1/ssh/keys/"+sshID+" " {
			t.Fatalf("%s: asked %v", arg, got)
		}
		if !strings.HasPrefix(sshLastIdem, "cli-") {
			t.Fatalf("%s: a removal carries an Idempotency-Key header (a retry files one request): %q", arg, sshLastIdem)
		}
	}
}

func TestSSHOnOffAndStatus(t *testing.T) {
	var got []string
	sshHub(t, &got)
	if r := run(t, "", false, "ssh", "off"); r.code != 0 || !strings.Contains(r.out, "act-ssh-3") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "ssh", "on"); r.code != 0 {
		t.Fatalf("%+v", r)
	}
	if !strings.Contains(got[0], `PUT /v1/ssh {"enabled":false`) || !strings.Contains(got[1], `PUT /v1/ssh {"enabled":true`) {
		t.Fatalf("asked %v", got)
	}
	r := run(t, "", false, "ssh", "status")
	if r.code != 0 || !strings.Contains(r.out, "on and listening") || !strings.Contains(r.out, "public key only, as admin, port 22") ||
		!strings.Contains(r.out, "LAN and mesh (also the internet on a cloud box)") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "--quiet", "ssh", "off"); r.code != 0 || strings.TrimSpace(r.out) != "act-ssh-3" {
		t.Fatalf("--quiet prints the id only: %+v", r)
	}
}

func TestSSHKeyID(t *testing.T) {
	if sshKeyID(sshFP) != sshID || sshKeyID(" "+sshID+"\n") != sshID {
		t.Fatal(sshKeyID(sshFP))
	}
}
