// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/onemindos/onemindos/internal/plugin/scaffold"
)

func TestPluginSigningRoundTripAndSafeOutput(t *testing.T) {
	for _, algorithm := range []string{"ed25519", "ecdsa", "rsa"} {
		t.Run(algorithm, func(t *testing.T) {
			var private any
			var err error
			switch algorithm {
			case "ed25519":
				_, private, err = ed25519.GenerateKey(rand.Reader)
			case "ecdsa":
				private, err = ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
			default:
				private, err = rsa.GenerateKey(rand.Reader, 2048)
			}
			if err != nil {
				t.Fatal(err)
			}
			root := t.TempDir()
			source, layout := filepath.Join(root, "source"), filepath.Join(root, "artifact")
			if err = scaffold.Create(source, "signed", "settings", "https://example.invalid/source"); err != nil {
				t.Fatal(err)
			}
			digest, err := artifact.Pack(source, layout)
			if err != nil {
				t.Fatal(err)
			}
			der, err := x509.MarshalPKCS8PrivateKey(private)
			if err != nil {
				t.Fatal(err)
			}
			key := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
			keyPath, output := filepath.Join(root, "key"), filepath.Join(root, "signature")
			if err = os.WriteFile(keyPath, key, 0600); err != nil {
				t.Fatal(err)
			}
			var stdout, stderr bytes.Buffer
			args := []string{"plugin", "sign", layout, "--digest", digest, "--key", keyPath, "--output", output, "--json"}
			if code := Run(args, Env{Stdout: &stdout, Stderr: &stderr}); code != ExitOK {
				t.Fatalf("%d: %s", code, stderr.String())
			}
			if !strings.Contains(stdout.String(), `"verified": false`) || strings.Contains(stdout.String()+stderr.String(), string(key)) {
				t.Fatalf("unsafe output: %s %s", &stdout, &stderr)
			}
			sig, err := os.ReadFile(output)
			if err != nil {
				t.Fatal(err)
			}
			public := private.(crypto.Signer).Public()
			pubDER, err := x509.MarshalPKIXPublicKey(public)
			if err != nil {
				t.Fatal(err)
			}
			if _, err = artifact.CheckSignature(layout, digest, pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER}), sig); err != nil {
				t.Fatal(err)
			}
			if code := Run(args, Env{Stdout: &stdout, Stderr: &stderr}); code != ExitVerifyFailed {
				t.Fatal("existing signature overwritten")
			}
			after, _ := os.ReadFile(output)
			if !bytes.Equal(sig, after) {
				t.Fatal("existing signature changed")
			}
			if err = os.Chmod(keyPath, 0644); err != nil {
				t.Fatal(err)
			}
			args[len(args)-2] = filepath.Join(root, "unsafe-output")
			if code := Run(args, Env{Stdout: &stdout, Stderr: &stderr}); code != ExitVerifyFailed {
				t.Fatal("world-readable private key accepted")
			}
		})
	}
}

func TestPrivateSigningInputRejectsLinksAndOversize(t *testing.T) {
	root := t.TempDir()
	key := filepath.Join(root, "key")
	if err := os.WriteFile(key, bytes.Repeat([]byte("x"), 17<<10), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := privateSigningInput(key); err == nil {
		t.Fatal("oversized key accepted")
	}
	link := filepath.Join(root, "link")
	if err := os.Symlink(key, link); err != nil {
		t.Fatal(err)
	}
	if _, err := privateSigningInput(link); err == nil {
		t.Fatal("symlink key accepted")
	}
	if _, err := privateSigningInput(root); err == nil {
		t.Fatal("directory accepted")
	}
}
