// SPDX-License-Identifier: Apache-2.0

package hostext

// A small PKCS#7 (RFC 2315) SignedData verifier for detached dm-verity root-hash signatures: the
// form `openssl smime -sign -nocerts -binary` writes and the kernel's dm-verity signature check
// reads, with or without signed attributes. Certificates inside the blob are ignored on purpose:
// only certificates from the OneMind key set can vouch for an image.

import (
	"bytes"
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"sort"
)

var (
	oidSignedData    = asn1.ObjectIdentifier{1, 2, 840, 113549, 1, 7, 2}
	oidData          = asn1.ObjectIdentifier{1, 2, 840, 113549, 1, 7, 1}
	oidMessageDigest = asn1.ObjectIdentifier{1, 2, 840, 113549, 1, 9, 4}
	oidRSAPSS        = asn1.ObjectIdentifier{1, 2, 840, 113549, 1, 1, 10}
	digests          = map[string]crypto.Hash{
		"2.16.840.1.101.3.4.2.1": crypto.SHA256, "2.16.840.1.101.3.4.2.2": crypto.SHA384, "2.16.840.1.101.3.4.2.3": crypto.SHA512,
	}
)

type rawElem struct{ Raw asn1.RawContent }

type contentInfo struct {
	ContentType asn1.ObjectIdentifier
	Content     asn1.RawValue `asn1:"explicit,optional,tag:0"`
}

type signedData struct {
	Version          int
	DigestAlgorithms []pkix.AlgorithmIdentifier `asn1:"set"`
	ContentInfo      contentInfo
	Certificates     rawElem      `asn1:"optional,tag:0"`
	CRLs             rawElem      `asn1:"optional,tag:1"`
	SignerInfos      []signerInfo `asn1:"set"`
}

type signerInfo struct {
	Version int
	Issuer  struct {
		Name   asn1.RawValue
		Serial *big.Int
	}
	DigestAlgorithm pkix.AlgorithmIdentifier
	AuthAttrs       rawElem `asn1:"optional,tag:0"`
	SigAlgorithm    pkix.AlgorithmIdentifier
	Signature       []byte
	UnauthAttrs     rawElem `asn1:"optional,tag:1"`
}

type attribute struct {
	Type   asn1.ObjectIdentifier
	Values asn1.RawValue `asn1:"set"`
}

func sha256Sum(b []byte) [32]byte { return sha256.Sum256(b) }

// LoadKeys reads every PEM certificate in *.crt files of dirs: the OneMind key set. Keys live in
// the read-only image (/usr/lib/verity.d), so nothing on the writable data partition can add one.
func LoadKeys(dirs []string) ([]*x509.Certificate, error) {
	var out []*x509.Certificate
	for _, d := range dirs {
		files, _ := filepath.Glob(filepath.Join(d, "*.crt"))
		sort.Strings(files)
		for _, f := range files {
			b, err := os.ReadFile(f)
			if err != nil {
				return nil, err
			}
			for blk, rest := pem.Decode(b); blk != nil; blk, rest = pem.Decode(rest) {
				if blk.Type != "CERTIFICATE" {
					continue
				}
				c, err := x509.ParseCertificate(blk.Bytes)
				if err != nil {
					return nil, fmt.Errorf("%s: %w", f, err)
				}
				out = append(out, c)
			}
		}
	}
	return out, nil
}

// verifyPKCS7 checks a detached signature over content against keys and returns the signer.
// fp, when set, is the SHA-256 fingerprint of the signer's certificate (the verity JSON field).
func verifyPKCS7(der, content []byte, keys []*x509.Certificate, fp string) (*x509.Certificate, error) {
	var ci contentInfo
	if rest, err := asn1.Unmarshal(der, &ci); err != nil || len(rest) != 0 || !ci.ContentType.Equal(oidSignedData) {
		return nil, refuse("bad_signature", "the signature is not PKCS#7 signed data")
	}
	var sd signedData
	if rest, err := asn1.Unmarshal(ci.Content.Bytes, &sd); err != nil || len(rest) != 0 {
		return nil, refuse("bad_signature", "the signature is not PKCS#7 signed data")
	}
	if !sd.ContentInfo.ContentType.Equal(oidData) || len(sd.ContentInfo.Content.Bytes) != 0 || len(sd.SignerInfos) != 1 {
		return nil, refuse("bad_signature", "the signature must be detached, over data, with one signer")
	}
	si := sd.SignerInfos[0]
	h, ok := digests[si.DigestAlgorithm.Algorithm.String()]
	if !ok || si.SigAlgorithm.Algorithm.Equal(oidRSAPSS) {
		return nil, refuse("bad_signature", "unsupported signature algorithm")
	}
	candidates := keys
	if fp != "" {
		candidates = nil
		for _, k := range keys {
			if fingerprint(k) == fp {
				candidates = append(candidates, k)
			}
		}
	}
	var signer *x509.Certificate
	for _, k := range candidates {
		if bytes.Equal(k.RawIssuer, si.Issuer.Name.FullBytes) && si.Issuer.Serial != nil && k.SerialNumber.Cmp(si.Issuer.Serial) == 0 {
			signer = k
			break
		}
	}
	if signer == nil {
		return nil, refuse("untrusted_key", "signed by a key that is not in the OneMind key set")
	}
	d := h.New()
	d.Write(content)
	sum := d.Sum(nil)
	signed := content
	if len(si.AuthAttrs.Raw) > 0 {
		set := append([]byte{0x31}, si.AuthAttrs.Raw[1:]...) // [0] IMPLICIT -> SET OF, as signed
		var attrs []attribute
		if _, err := asn1.UnmarshalWithParams(set, &attrs, "set"); err != nil {
			return nil, refuse("bad_signature", "unreadable signed attributes")
		}
		var md []byte
		for _, a := range attrs {
			if a.Type.Equal(oidMessageDigest) {
				if _, err := asn1.Unmarshal(a.Values.Bytes, &md); err != nil {
					md = nil
				}
			}
		}
		if !bytes.Equal(md, sum) {
			return nil, refuse("bad_signature", "the signature does not match the root hash")
		}
		signed = set
	}
	alg := x509.UnknownSignatureAlgorithm
	switch signer.PublicKey.(type) {
	case *rsa.PublicKey:
		alg = map[crypto.Hash]x509.SignatureAlgorithm{crypto.SHA256: x509.SHA256WithRSA, crypto.SHA384: x509.SHA384WithRSA, crypto.SHA512: x509.SHA512WithRSA}[h]
	case *ecdsa.PublicKey:
		alg = map[crypto.Hash]x509.SignatureAlgorithm{crypto.SHA256: x509.ECDSAWithSHA256, crypto.SHA384: x509.ECDSAWithSHA384, crypto.SHA512: x509.ECDSAWithSHA512}[h]
	case ed25519.PublicKey:
		alg = x509.PureEd25519
	}
	if err := signer.CheckSignature(alg, signed, si.Signature); err != nil {
		return nil, refuse("bad_signature", "the signature does not match the root hash (key %s)", hex.EncodeToString(signer.SubjectKeyId))
	}
	return signer, nil
}
