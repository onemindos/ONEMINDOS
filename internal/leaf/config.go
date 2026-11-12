// SPDX-License-Identifier: Apache-2.0

// Package leaf generates and supervises this machine's local NATS leaf node
// (docs/architecture/NETWORKING.md §7, FABRIC §5): a nats-server bound to
// loopback, with its own JetStream domain for the outbox, connected to the
// hub's leaf port over the mesh with TLS that pins the box CA and with the
// node's own credentials. This replaces the v0 shortcut where nodes published
// straight to the hub's NATS with no auth or TLS (hardening item H-06).
//
// The nats-server process itself is run by systemd
// (onemind-nats-leaf.service, §18); this package owns its config file, asks
// systemd to reload it when the file changes, and reports leaf health from the
// server's loopback monitoring endpoint.
package leaf

import (
	"bytes"
	"errors"
	"fmt"
	"net"
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// Defaults (§3 ports table, §7 leaf.conf).
const (
	DefaultListen       = "127.0.0.1:4222"
	DefaultMonitor      = "127.0.0.1:8222"
	DefaultMaxFileStore = "256MB"
)

// Config is everything the node's leaf.conf is rendered from. Paths are
// absolute. Secrets are never in Config: the node's nkey seed lives in its own
// 0600 file (NkeyFile, written by WriteNkeyFile) that leaf.conf includes.
type Config struct {
	// ServerName and Domain are node-<node_id> (§7).
	ServerName string
	Domain     string
	Listen     string // loopback only (H-24); default 127.0.0.1:4222
	Monitor    string // loopback only; default 127.0.0.1:8222, used by Health
	StoreDir   string
	// MaxFileStore caps the outbox on disk (W8-R2); default 256MB.
	MaxFileStore string
	// HubURLs are the hub leaf listeners over the mesh, e.g.
	// tls://100.64.0.1:7422 (example address). Only tls:// is accepted.
	HubURLs []string
	// CAFile pins the box CA: the hub's leaf certificate must chain to it.
	CAFile string
	// CertFile and KeyFile are the node certificate (FABRIC §3) presented to
	// the hub, which requires it (leafnodes tls verify: true). Both or neither.
	CertFile string
	KeyFile  string
	// Exactly one of NkeyFile (the node's nkey seed as a config fragment, R8:
	// hub users are nkey users) or CredsFile (a JWT .creds file, for a later
	// operator-mode hub) authenticates the leaf.
	NkeyFile  string
	CredsFile string
}

var nameRe = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)

// sizeRe matches NATS size values such as 256MB or 1GB.
var sizeRe = regexp.MustCompile(`^[0-9]{1,6}(B|KB|MB|GB|K|M|G)$`)

func (c *Config) withDefaults() Config {
	d := *c
	if d.Listen == "" {
		d.Listen = DefaultListen
	}
	if d.Monitor == "" {
		d.Monitor = DefaultMonitor
	}
	if d.MaxFileStore == "" {
		d.MaxFileStore = DefaultMaxFileStore
	}
	if d.Domain == "" {
		d.Domain = d.ServerName
	}
	return d
}

func loopback(field, hp string) error {
	h, p, err := net.SplitHostPort(hp)
	if err != nil {
		return fmt.Errorf("%s: %w", field, err)
	}
	ip := net.ParseIP(h)
	if ip == nil || !ip.IsLoopback() {
		return fmt.Errorf("%s must be a loopback address (H-24), got %q", field, hp)
	}
	if n, err := strconv.Atoi(p); err != nil || n < 0 || n > 65535 {
		return fmt.Errorf("%s: bad port %q", field, p)
	}
	return nil
}

// safePath refuses anything that is not a plain absolute path, so a value can
// never break out of its quoted string in the rendered config.
func safePath(field, p string, required bool) error {
	if p == "" {
		if required {
			return fmt.Errorf("%s is required", field)
		}
		return nil
	}
	if !filepath.IsAbs(p) || filepath.Clean(p) != p {
		return fmt.Errorf("%s must be a clean absolute path, got %q", field, p)
	}
	if strings.ContainsAny(p, "\"\\'$\n\r\t{}[]#;") {
		return fmt.Errorf("%s contains a character not allowed in a config path: %q", field, p)
	}
	return nil
}

// Validate checks c (with defaults applied).
func (c *Config) Validate() error {
	d := c.withDefaults()
	if !nameRe.MatchString(d.ServerName) {
		return fmt.Errorf("server name must be 1-64 of A-Z a-z 0-9 _ -, got %q", d.ServerName)
	}
	if !nameRe.MatchString(d.Domain) || d.Domain == "hub" {
		return fmt.Errorf("JetStream domain must be a node name other than the hub's, got %q", d.Domain)
	}
	if err := loopback("listen", d.Listen); err != nil {
		return err
	}
	if err := loopback("monitor", d.Monitor); err != nil {
		return err
	}
	if !sizeRe.MatchString(d.MaxFileStore) {
		return fmt.Errorf("max file store must look like 256MB, got %q", d.MaxFileStore)
	}
	if len(d.HubURLs) == 0 {
		return errors.New("at least one hub leaf URL is required")
	}
	for _, s := range d.HubURLs {
		u, err := url.Parse(s)
		if err != nil || u.Scheme != "tls" || u.Host == "" || u.Port() == "" {
			return fmt.Errorf("hub URL must be tls://host:port (no plaintext leaf, H-06), got %q", s)
		}
		if u.User != nil || (u.Path != "" && u.Path != "/") || u.RawQuery != "" {
			return fmt.Errorf("hub URL must not carry credentials, a path or a query, got %q", s)
		}
		if strings.ContainsAny(s, "\"\\'$\n\r\t ") {
			return fmt.Errorf("hub URL contains a forbidden character: %q", s)
		}
	}
	for _, f := range []struct {
		name, v string
		req     bool
	}{{"store dir", d.StoreDir, true}, {"CA file", d.CAFile, true}, {"cert file", d.CertFile, false},
		{"key file", d.KeyFile, false}, {"nkey file", d.NkeyFile, false}, {"creds file", d.CredsFile, false}} {
		if err := safePath(f.name, f.v, f.req); err != nil {
			return err
		}
	}
	if (d.CertFile == "") != (d.KeyFile == "") {
		return errors.New("cert file and key file go together")
	}
	if (d.NkeyFile == "") == (d.CredsFile == "") {
		return errors.New("exactly one of nkey file or creds file is required (per-node leaf credentials, H-06)")
	}
	return nil
}

// Render returns leaf.conf for a file at confPath. The nkey file is included
// by a path relative to confPath's directory, because nats-server resolves
// include paths that way; it must therefore sit in or below that directory.
func (c *Config) Render(confPath string) ([]byte, error) {
	if err := c.Validate(); err != nil {
		return nil, err
	}
	d := c.withDefaults()
	var b bytes.Buffer
	b.WriteString("# Generated by onemindd (internal/leaf). Do not edit: changes are overwritten.\n")
	fmt.Fprintf(&b, "server_name: %q\n", d.ServerName)
	fmt.Fprintf(&b, "listen: %q\n", d.Listen)
	fmt.Fprintf(&b, "http: %q\n", d.Monitor)
	fmt.Fprintf(&b, "jetstream {\n  store_dir: %q\n  domain: %q\n  max_file_store: %s\n}\n", d.StoreDir, d.Domain, d.MaxFileStore)
	b.WriteString("leafnodes {\n  remotes: [\n    {\n")
	quoted := make([]string, len(d.HubURLs))
	for i, u := range d.HubURLs {
		quoted[i] = strconv.Quote(u)
	}
	fmt.Fprintf(&b, "      urls: [%s]\n", strings.Join(quoted, ", "))
	if d.NkeyFile != "" {
		rel, err := filepath.Rel(filepath.Dir(confPath), d.NkeyFile)
		if err != nil || rel == ".." || strings.HasPrefix(rel, "../") {
			return nil, fmt.Errorf("nkey file %q must be in the directory of %q (nats-server include rule)", d.NkeyFile, confPath)
		}
		fmt.Fprintf(&b, "      include %q\n", rel)
	} else {
		fmt.Fprintf(&b, "      credentials: %q\n", d.CredsFile)
	}
	b.WriteString("      tls {\n")
	fmt.Fprintf(&b, "        ca_file: %q\n", d.CAFile)
	if d.CertFile != "" {
		fmt.Fprintf(&b, "        cert_file: %q\n        key_file: %q\n", d.CertFile, d.KeyFile)
	}
	b.WriteString("        timeout: 5\n      }\n    }\n  ]\n}\n")
	return b.Bytes(), nil
}
