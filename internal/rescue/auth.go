// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"gopkg.in/yaml.v3"
)

// DefaultTokensFile is the gateway's principals file (deploy/install.sh). It
// holds only "sha256:<hex>" keys, so reading it gives the rescue console the
// owner credential without the gateway, k3s or any network running.
const DefaultTokensFile = "/etc/onemind/tokens.yaml"

type principal struct {
	Token string `yaml:"token"`
	ID    string `yaml:"id"`
	Kind  string `yaml:"kind"`
	Role  string `yaml:"role"`
}

// loadPrincipals reads the tokens file (both shapes core/onemind_core/auth.py accepts).
func loadPrincipals(path string) ([]principal, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var doc struct {
		Tokens yaml.Node `yaml:"tokens"`
	}
	if err := yaml.Unmarshal(b, &doc); err != nil {
		return nil, fmt.Errorf("tokens file: %w", err)
	}
	var entries []principal
	switch doc.Tokens.Kind {
	case yaml.MappingNode:
		m := map[string]principal{}
		if err := doc.Tokens.Decode(&m); err != nil {
			return nil, fmt.Errorf("tokens file: %w", err)
		}
		for k, p := range m {
			p.Token = k
			entries = append(entries, p)
		}
	case yaml.SequenceNode:
		if err := doc.Tokens.Decode(&entries); err != nil {
			return nil, fmt.Errorf("tokens file: %w", err)
		}
	}
	return entries, nil
}

// digestOf returns the sha256 a principal's token entry stands for.
func digestOf(p principal) ([]byte, bool) {
	if p.Token == "" {
		return nil, false
	}
	if h, ok := strings.CutPrefix(p.Token, "sha256:"); ok {
		d, err := hex.DecodeString(strings.ToLower(h))
		return d, err == nil && len(d) == sha256.Size
	}
	d := sha256.Sum256([]byte(p.Token))
	return d[:], true
}

// ownerDigests returns the sha256 of every owner principal's token. Only a
// person with role owner counts: an agent can never act as the owner.
func ownerDigests(path string) ([][]byte, error) {
	entries, err := loadPrincipals(path)
	if err != nil {
		return nil, err
	}
	var out [][]byte
	for _, p := range entries {
		if p.Kind != "person" || p.Role != "owner" {
			continue
		}
		if d, ok := digestOf(p); ok {
			out = append(out, d)
		}
	}
	return out, nil
}

// nonOwnerDigests returns the sha256 of every other principal's token (agents,
// non-owner people). The terminal answers these with 403 instead of 401: the
// credential is valid, but it is never allowed a shell.
func nonOwnerDigests(path string) [][]byte {
	entries, err := loadPrincipals(path)
	if err != nil {
		return nil
	}
	var out [][]byte
	for _, p := range entries {
		if p.Kind == "person" && p.Role == "owner" {
			continue
		}
		if d, ok := digestOf(p); ok {
			out = append(out, d)
		}
	}
	return out
}

// presented returns the credential from "Authorization: Bearer <token>" or
// HTTP Basic (any user name, the token as password; what a browser can send).
func presented(r *http.Request) string {
	h := r.Header.Get("Authorization")
	if t, ok := strings.CutPrefix(h, "Bearer "); ok {
		return strings.TrimSpace(t)
	}
	if _, p, ok := r.BasicAuth(); ok {
		return p
	}
	return ""
}

// matches compares sha256(token) with every owner digest in constant time.
func matches(token string, owners [][]byte) bool {
	d := sha256.Sum256([]byte(token))
	ok := 0
	for _, o := range owners {
		ok |= subtle.ConstantTimeCompare(d[:], o)
	}
	return ok == 1
}

// limiter refuses a client address for Window after MaxFails failed logins.
type limiter struct {
	mu       sync.Mutex
	fails    map[string][]time.Time
	now      func() time.Time
	maxFails int
	window   time.Duration
}

func clientIP(r *http.Request) string {
	h, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return h
}

func (l *limiter) recent(ip string) []time.Time {
	cut := l.now().Add(-l.window)
	kept := l.fails[ip][:0]
	for _, t := range l.fails[ip] {
		if t.After(cut) {
			kept = append(kept, t)
		}
	}
	l.fails[ip] = kept
	return kept
}

func (l *limiter) blocked(ip string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.recent(ip)) >= l.maxFails
}

func (l *limiter) fail(ip string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if len(l.fails) > 4096 { // bound memory under a spray from many addresses
		l.fails = map[string][]time.Time{}
	}
	l.fails[ip] = append(l.recent(ip), l.now())
}

// lanOnly reports whether the client address is loopback, private
// (RFC 1918, fc00::/7) or link-local: the rescue console is not for the internet.
// meshNets are the mesh's address ranges (core/onemind_core/ca.py MESH_NETS): the CGNAT range
// and the Tailscale ULA. The console is LAN-only, so they are refused even though Go counts the
// ULA (inside fc00::/7) as private.
var meshNets = []*net.IPNet{
	mustCIDR("100.64.0.0/10"),
	mustCIDR("fd7a:115c:a1e0::/48"),
}

func mustCIDR(s string) *net.IPNet {
	_, n, err := net.ParseCIDR(s)
	if err != nil {
		panic(err)
	}
	return n
}

func lanOnly(r *http.Request) bool {
	ip := net.ParseIP(clientIP(r))
	if ip == nil {
		return false
	}
	for _, n := range meshNets {
		if n.Contains(ip) {
			return false
		}
	}
	return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast()
}
