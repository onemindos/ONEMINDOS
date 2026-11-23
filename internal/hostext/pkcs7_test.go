// SPDX-License-Identifier: Apache-2.0

package hostext

import (
	"crypto/x509"
	"strings"
	"testing"
)

// The fixtures are real OpenSSL output (testdata/README.md), so the parser is checked against
// what a signer produces, not against an encoder written next to it.
func TestPKCS7AgainstOpenSSL(t *testing.T) {
	rh := []byte(strings.TrimSpace(string(fixture(t, "roothash"))))
	rsa, _ := LoadKeys([]string{keyDir(t, "rsa.crt")})
	ec, _ := LoadKeys([]string{keyDir(t, "ec.crt")})
	both, _ := LoadKeys([]string{keyDir(t, "rsa.crt", "ec.crt")})
	tampered := append([]byte{}, rh...)
	tampered[3] ^= 1
	for _, tc := range []struct {
		name    string
		sig     string
		content []byte
		keys    int // 0 rsa, 1 ec, 2 both
		fp      string
		code    string
	}{
		{"rsa, no signed attributes", "rsa-noattr.p7s", rh, 0, "", ""},
		{"ec, signed attributes", "ec-attr.p7s", rh, 1, "", ""},
		{"both keys trusted", "ec-attr.p7s", rh, 2, "", ""},
		{"fingerprint names the signer", "rsa-noattr.p7s", rh, 2, certFingerprint(t, "rsa.crt"), ""},
		{"key not in the set", "rsa-noattr.p7s", rh, 1, "", "untrusted_key"},
		{"fingerprint names another key", "ec-attr.p7s", rh, 2, certFingerprint(t, "rsa.crt"), "untrusted_key"},
		{"unknown fingerprint", "rsa-noattr.p7s", rh, 0, strings.Repeat("ab", 32), "untrusted_key"},
		{"content changed, no attributes", "rsa-noattr.p7s", tampered, 0, "", "bad_signature"},
		{"content changed, digest attribute", "ec-attr.p7s", tampered, 1, "", "bad_signature"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			keys := [][]*x509.Certificate{rsa, ec, both}[tc.keys]
			_, err := verifyPKCS7(fixture(t, tc.sig), tc.content, keys, tc.fp)
			if tc.code == "" {
				if err != nil {
					t.Fatal(err)
				}
				return
			}
			wantRefused(t, err, tc.code)
		})
	}
	if _, err := verifyPKCS7([]byte("not der"), rh, rsa, ""); err == nil {
		t.Fatal("garbage accepted")
	}
}
