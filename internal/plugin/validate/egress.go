// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"net/netip"
	"strings"

	"golang.org/x/net/idna"
	"golang.org/x/net/publicsuffix"
)

var egressIDNA = idna.New(idna.ValidateLabels(true), idna.StrictDomainName(true))

// validateEgress implements P9 without DNS or network access. The bundled
// Public Suffix List includes private suffixes, so *.github.io cannot grant
// access to every tenant. This checks names, not resolved destination addresses:
// runtime egress enforcement must separately reject private/rebound addresses.
func validateEgress(spec map[string]any) error {
	entries, ok := spec["egress"].([]any)
	if !ok {
		return nil
	}
	seen := make(map[string]bool)
	for _, raw := range entries {
		entry := raw.(string)
		canonical, err := egressName(entry)
		if err != nil {
			return fmt.Errorf("egress %q: %w", entry, err)
		}
		if seen[canonical] {
			return fmt.Errorf("duplicate egress hostname %q", entry)
		}
		seen[canonical] = true
	}
	return nil
}

func egressName(entry string) (string, error) {
	for _, c := range entry {
		if c > 127 {
			return "", fmt.Errorf("IDNs must use validated ASCII punycode")
		}
	}
	canonical := strings.ToLower(entry)
	host := strings.TrimPrefix(canonical, "*.")
	if host == "" || len(host) > 253 || !strings.Contains(host, ".") {
		return "", fmt.Errorf("expected a qualified hostname of at most 253 bytes")
	}
	if _, err := netip.ParseAddr(host); err == nil {
		return "", fmt.Errorf("IP literals are forbidden")
	}
	for _, c := range host {
		if c > 127 || !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '.') {
			return "", fmt.Errorf("expected an ASCII hostname, optionally prefixed with '*.'; use validated punycode for IDNs")
		}
	}
	for _, label := range strings.Split(host, ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return "", fmt.Errorf("invalid hostname label")
		}
	}
	for _, label := range strings.Split(host, ".") {
		if strings.HasPrefix(label, "xn--") {
			if _, err := egressIDNA.ToASCII(label); err != nil {
				return "", fmt.Errorf("invalid punycode label: %w", err)
			}
		}
	}
	// Special-use/local domains cannot become internet egress grants. Unknown
	// single-label suffixes are also refused below; new public TLDs need a PSL update.
	for _, suffix := range []string{"localhost", "local", "internal", "test", "invalid", "example", "onion", "alt", "arpa"} {
		if host == suffix || strings.HasSuffix(host, "."+suffix) {
			return "", fmt.Errorf("special-use hostname is forbidden")
		}
	}
	suffix, icann := publicsuffix.PublicSuffix(host)
	if !icann && !strings.Contains(suffix, ".") {
		return "", fmt.Errorf("hostname has an unknown public suffix")
	}
	if strings.HasPrefix(canonical, "*.") {
		if _, err := publicsuffix.EffectiveTLDPlusOne(host); err != nil {
			return "", fmt.Errorf("wildcard must be below a public suffix: %w", err)
		}
	}
	return canonical, nil
}
