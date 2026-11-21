// SPDX-License-Identifier: Apache-2.0

// Package relay is the OneMind relay role (docs/architecture/NETWORKING.md §4.4).
//
// A relay is any OneMind machine the owner controls that has a public address. It lets phones and
// laptops reach the hub from outside the home network, with no third-party account and no vendor
// server. It does one thing: read the server name a TLS client asks for (the "SNI", sent in the
// clear in the first message) and pass the still-encrypted connection to a fixed upstream for that
// name. It never decrypts, holds no key for any hub name, and closes everything else (default deny).
// Only the Go standard library is used.
package relay

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base32"
	"encoding/hex"
	"errors"
	"fmt"
	"net/netip"
	"net/url"
	"regexp"
	"strings"
)

// PairingScheme is the prefix of the pairing text the relay prints and the owner pastes into the
// dashboard (NETWORKING.md §4.4): onemind-relay:v1?addr=<public ip>&fp=<sha256>&code=<one-time>.
const PairingScheme = "onemind-relay:v1"

var cgnat = netip.MustParsePrefix("100.64.0.0/10") // the mesh's own range: never a relay's address

var fpRe = regexp.MustCompile(`^[0-9a-f]{64}$`)

// Pairing is what the owner carries from the relay to the hub. Code is a secret: it is shown once
// and only its hash is kept on the relay.
type Pairing struct {
	Addr string // the relay's public IP address
	FP   string // sha256 (hex) of the relay's setup certificate, so the hub can pin it
	Code string // one-time code that authorises the pairing
}

// String is the pairing text.
func (p Pairing) String() string {
	q := url.Values{"addr": {p.Addr}, "fp": {p.FP}, "code": {p.Code}}
	return PairingScheme + "?" + q.Encode()
}

// ParsePairing validates a pairing text. Errors never echo the code.
func ParsePairing(s string) (Pairing, error) {
	s = strings.TrimSpace(s)
	rest, ok := strings.CutPrefix(s, PairingScheme+"?")
	if !ok {
		return Pairing{}, errors.New("not a OneMind relay pairing text")
	}
	q, err := url.ParseQuery(rest)
	if err != nil {
		return Pairing{}, errors.New("pairing text is malformed")
	}
	p := Pairing{Addr: q.Get("addr"), FP: q.Get("fp"), Code: q.Get("code")}
	if a, err := netip.ParseAddr(p.Addr); err != nil || !a.IsGlobalUnicast() || a.IsPrivate() || cgnat.Contains(a) {
		return Pairing{}, errors.New("pairing addr must be a public IP address")
	}
	if !fpRe.MatchString(p.FP) {
		return Pairing{}, errors.New("pairing fp must be 64 lower-case hex characters")
	}
	if len(p.Code) < 16 || len(p.Code) > 64 {
		return Pairing{}, errors.New("pairing code has the wrong length")
	}
	return p, nil
}

var codeEnc = base32.StdEncoding.WithPadding(base32.NoPadding)

// NewCode returns a fresh one-time code (160 random bits, upper-case base32).
func NewCode() (string, error) {
	b := make([]byte, 20)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return codeEnc.EncodeToString(b), nil
}

// CodeMatches compares a presented code with the stored sha256 hex hash in constant time.
func CodeMatches(presented, storedHashHex string) bool {
	got, err1 := hex.DecodeString(HashCode(presented))
	want, err2 := hex.DecodeString(storedHashHex)
	return err1 == nil && err2 == nil && len(want) == len(got) && subtle.ConstantTimeCompare(got, want) == 1
}

// HashCode is the hex sha256 of a code; the relay stores this, never the code.
func HashCode(code string) string { return sha256Hex([]byte(strings.ToUpper(strings.TrimSpace(code)))) }

func sha256Hex(b []byte) string {
	h := sha256Sum(b)
	return fmt.Sprintf("%x", h)
}
