// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/onemindos/onemindos/internal/plugin/scaffold"
)

func TestSignatureInspectionNeverClaimsEnrolledTrust(t *testing.T) {
	src := filepath.Join(t.TempDir(), "example")
	if err := scaffold.Create(src, "example", "settings", "https://example.invalid/source"); err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(t.TempDir(), "oci")
	digest, err := artifact.Pack(src, output)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join(output, "blobs/sha256", strings.TrimPrefix(digest, "sha256:")))
	if err != nil {
		t.Fatal(err)
	}
	pub, key, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		t.Fatal(err)
	}
	publicPath := filepath.Join(t.TempDir(), "public.pem")
	signaturePath := filepath.Join(t.TempDir(), "signature.txt")
	if err = os.WriteFile(publicPath, pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}), 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(signaturePath, []byte(base64.StdEncoding.EncodeToString(ed25519.Sign(key, append([]byte(artifact.SignaturePurpose+digest+"\n"), raw...)))), 0600); err != nil {
		t.Fatal(err)
	}
	var out, stderr bytes.Buffer
	args := []string{"plugin", "inspect", output, "--digest", digest, "--key", publicPath, "--signature", signaturePath, "--json"}
	if code := Run(args, Env{Stdout: &out, Stderr: &stderr}); code != ExitOK || !strings.Contains(out.String(), `"signature_valid": true`) || !strings.Contains(out.String(), `"verified": false`) {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}
	var manifest artifact.Manifest
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(output, "blobs/sha256", strings.TrimPrefix(manifest.Layers[0].Digest, "sha256:")), []byte("bad layer"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(signaturePath, []byte("not-base64"), 0600); err != nil {
		t.Fatal(err)
	}
	out.Reset()
	stderr.Reset()
	if code := Run(args, Env{Stdout: &out, Stderr: &stderr}); code != ExitVerifyFailed || !strings.Contains(stderr.String(), "invalid detached signature encoding") {
		t.Fatalf("signature was not checked before extraction: %d %s", code, &stderr)
	}
	out.Reset()
	stderr.Reset()
	if code := Run([]string{"plugin", "inspect", output, "--digest", digest, "--key", publicPath}, Env{Stdout: &out, Stderr: &stderr}); code != ExitUsage {
		t.Fatalf("unpaired signature flags: %d", code)
	}
}
