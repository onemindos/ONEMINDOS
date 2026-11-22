// SPDX-License-Identifier: Apache-2.0

package artifact

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSigningRefusesUnsafeKeysReferencesAndCorruptArtifacts(t *testing.T) {
	output, digest := packed(t)
	_, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(private)
	if err != nil {
		t.Fatal(err)
	}
	key := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	weak, err := rsa.GenerateKey(rand.Reader, 1024)
	if err != nil {
		t.Fatal(err)
	}
	weakDER, err := x509.MarshalPKCS8PrivateKey(weak)
	if err != nil {
		t.Fatal(err)
	}
	for _, bad := range [][]byte{nil, []byte("not PEM"), keyPEM(t, private.Public()), append(append([]byte{}, key...), key...), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: weakDER})} {
		if sig, _, err := Sign(output, digest, bad); err == nil || len(sig) != 0 {
			t.Fatal("unsafe signing key accepted")
		}
	}
	if sig, _, err := Sign(output, "latest", key); err == nil || len(sig) != 0 {
		t.Fatal("mutable reference signed")
	}
	if err = os.WriteFile(filepath.Join(output, "blobs/sha256", strings.TrimPrefix(digest, "sha256:")), []byte("corrupted"), 0600); err != nil {
		t.Fatal(err)
	}
	if sig, _, err := Sign(output, digest, key); err == nil || len(sig) != 0 {
		t.Fatal("corrupted artifact signed")
	}
}
