// SPDX-License-Identifier: Apache-2.0

package artifact

import (
	"bytes"
	"crypto"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"fmt"
	"strings"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/sigstore/sigstore/pkg/signature"
)

// Sign signs the exact immutable OCI manifest using a caller-supplied PKCS8 key.
// It creates no keys and conveys no owner enrollment, scan or install approval.
func Sign(directory, digest string, privatePEM []byte) (encoded []byte, keyID string, err error) {
	if len(privatePEM) > 16<<10 || !digestPattern.MatchString(digest) {
		return nil, "", fmt.Errorf("invalid signing input bounds or digest")
	}
	block, rest := pem.Decode(privatePEM)
	if block == nil || block.Type != "PRIVATE KEY" || len(bytes.TrimSpace(rest)) != 0 {
		return nil, "", fmt.Errorf("one unencrypted PKCS8 private key is required")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, "", fmt.Errorf("invalid PKCS8 private key")
	}
	private, ok := key.(crypto.Signer)
	if !ok {
		return nil, "", fmt.Errorf("unsupported signing key")
	}
	public, err := x509.MarshalPKIXPublicKey(private.Public())
	if err != nil {
		return nil, "", fmt.Errorf("unsupported public key")
	}
	// Check the complete artifact before producing a signature, including layers.
	bundle, err := Open(directory, digest)
	if err != nil {
		return nil, "", err
	}
	defer bundle.Close()
	raw, err := read(directory, "blobs/sha256/"+strings.TrimPrefix(digest, "sha256:"), validate.MaxManifestBytes)
	if err != nil {
		return nil, "", err
	}
	signer, err := signature.LoadSigner(key, crypto.SHA256)
	if err != nil {
		return nil, "", fmt.Errorf("unsupported signing algorithm")
	}
	sig, err := signer.SignMessage(bytes.NewReader(raw))
	if err != nil {
		return nil, "", fmt.Errorf("artifact signing failed")
	}
	encoded = []byte(base64.StdEncoding.EncodeToString(sig) + "\n")
	keyID, err = CheckSignature(directory, digest, pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: public}), encoded)
	if err != nil {
		return nil, "", err
	}
	return encoded, keyID, nil
}
