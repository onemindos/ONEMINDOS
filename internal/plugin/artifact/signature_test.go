// SPDX-License-Identifier: Apache-2.0

package artifact

import (
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func keyPEM(t *testing.T, key any) []byte {
	t.Helper()
	der, err := x509.MarshalPKIXPublicKey(key)
	if err != nil {
		t.Fatal(err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
}
func TestDetachedSignatureVerifiesExactManifestThroughSigstore(t *testing.T) {
	output, digest := packed(t)
	raw, err := os.ReadFile(filepath.Join(output, "blobs/sha256", strings.TrimPrefix(digest, "sha256:")))
	if err != nil {
		t.Fatal(err)
	}
	pub, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	encoded := []byte(base64.StdEncoding.EncodeToString(ed25519.Sign(private, raw)))
	fingerprint, err := CheckSignature(output, digest, keyPEM(t, pub), encoded)
	if err != nil || !digestPattern.MatchString(fingerprint) {
		t.Fatalf("signature check: %s %v", fingerprint, err)
	}
	wrong, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = CheckSignature(output, digest, keyPEM(t, wrong), encoded); err == nil {
		t.Fatal("wrong candidate key accepted")
	}
	if _, err = CheckSignature(output, digest, keyPEM(t, pub), []byte("not-base64")); err == nil {
		t.Fatal("malformed signature accepted")
	}
	if _, err = CheckSignature(output, digest, append(keyPEM(t, pub), keyPEM(t, pub)...), encoded); err == nil {
		t.Fatal("multiple public keys accepted")
	}
	if _, err = CheckSignature(output, "latest", keyPEM(t, pub), encoded); err == nil {
		t.Fatal("mutable reference accepted")
	}
	if err = os.WriteFile(filepath.Join(output, "blobs/sha256", strings.TrimPrefix(digest, "sha256:")), []byte("changed"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = CheckSignature(output, digest, keyPEM(t, pub), encoded); err == nil {
		t.Fatal("modified artifact accepted")
	}
}
func TestECDSADetachedSignatureUsesSHA256(t *testing.T) {
	output, digest := packed(t)
	raw, err := os.ReadFile(filepath.Join(output, "blobs/sha256", strings.TrimPrefix(digest, "sha256:")))
	if err != nil {
		t.Fatal(err)
	}
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(raw)
	sig, err := ecdsa.SignASN1(rand.Reader, key, sum[:])
	if err != nil {
		t.Fatal(err)
	}
	if _, err = CheckSignature(output, digest, keyPEM(t, &key.PublicKey), []byte(base64.StdEncoding.EncodeToString(sig))); err != nil {
		t.Fatal(err)
	}
}
