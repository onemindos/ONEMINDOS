// SPDX-License-Identifier: Apache-2.0

package artifact

import (
	"bytes"
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"strings"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"github.com/sigstore/sigstore/pkg/signature"
)

// SignaturePurpose separates plugin artifact signatures from other uses of a key.
const SignaturePurpose = "onemind.plugin.artifact/v1\n"

func signingMessage(digest string, raw []byte) []byte {
	return append([]byte(SignaturePurpose+digest+"\n"), raw...)
}

// CheckSignature verifies a detached base64 signature over the exact OCI artifact
// manifest, using Sigstore's existing crypto verifier. The returned SPKI key id
// is a candidate identity, not proof that an owner enrolled or trusts this key.
func CheckSignature(directory, digest string, publicPEM, encoded []byte) (string, error) {
	if !digestPattern.MatchString(digest) || len(publicPEM) > 16<<10 || len(encoded) > 16<<10 {
		return "", fmt.Errorf("invalid signature input bounds")
	}
	block, rest := pem.Decode(publicPEM)
	if block == nil || block.Type != "PUBLIC KEY" || len(bytes.TrimSpace(rest)) != 0 {
		return "", fmt.Errorf("a single public SPKI PEM key is required")
	}
	key, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return "", fmt.Errorf("invalid public key")
	}
	switch k := key.(type) {
	case *rsa.PublicKey:
		if k.N.BitLen() < 2048 {
			return "", fmt.Errorf("RSA key must have at least 2048 bits")
		}
	case *ecdsa.PublicKey:
		if k.Curve.Params().BitSize < 256 {
			return "", fmt.Errorf("ECDSA key must have at least 256 bits")
		}
	case ed25519.PublicKey:
	default:
		return "", fmt.Errorf("unsupported plugin public key")
	}
	raw, err := read(directory, "blobs/sha256/"+strings.TrimPrefix(digest, "sha256:"), validate.MaxManifestBytes)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(raw)
	if digest != "sha256:"+hex.EncodeToString(sum[:]) {
		return "", fmt.Errorf("artifact digest mismatch")
	}
	sig, err := base64.StdEncoding.Strict().DecodeString(strings.TrimSpace(string(encoded)))
	if err != nil || len(sig) == 0 {
		return "", fmt.Errorf("invalid detached signature encoding")
	}
	verifier, err := signature.LoadVerifier(key, crypto.SHA256)
	if err != nil {
		return "", fmt.Errorf("unsupported signature verifier")
	}
	if err = verifier.VerifySignature(bytes.NewReader(sig), bytes.NewReader(signingMessage(digest, raw))); err != nil {
		return "", fmt.Errorf("plugin signature does not match the artifact and key")
	}
	fingerprint := sha256.Sum256(block.Bytes)
	return "sha256:" + hex.EncodeToString(fingerprint[:]), nil
}
