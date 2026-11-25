// SPDX-License-Identifier: Apache-2.0

package relay

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// DefaultConfigPath is where `onemindd relay init` writes the role's config (relay machine only).
const DefaultConfigPath = "/data/onemind/relay/config.json"

// Route sends TLS connections that ask for Name to Upstream (host:port) without decrypting them.
type Route struct {
	Name     string `json:"name"`
	Upstream string `json:"upstream"`
}

// Config is the relay role. A name that is not listed is closed: default deny. There is no
// catch-all route and no way to serve a page, so the relay exposes no dashboard.
type Config struct {
	Listen   string  `json:"listen"` // public address, default :443
	Routes   []Route `json:"routes"`
	CodeHash string  `json:"code_hash,omitempty"` // sha256 of the pairing code; the code itself is never stored
	SetupFP  string  `json:"setup_fp,omitempty"`  // sha256 of the setup certificate shown in the pairing text
	Paired   bool    `json:"paired,omitempty"`    // set once the owner's hub has paired; the code is then spent
}

var nameRe = regexp.MustCompile(`^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`)

// Validate refuses a config that could forward more than the hub's encrypted mesh traffic.
func (c *Config) Validate() error {
	if _, port, err := net.SplitHostPort(c.Listen); err != nil || !validPort(port) {
		return fmt.Errorf("listen must be host:port, got %q", c.Listen)
	}
	if len(c.Routes) == 0 {
		return errors.New("a relay with no routes forwards nothing; add the hub's control name")
	}
	if len(c.Routes) > 8 {
		return errors.New("too many routes: a relay carries the control and relay names only")
	}
	seen := map[string]bool{}
	for _, r := range c.Routes {
		if !nameRe.MatchString(r.Name) || strings.ContainsAny(r.Name, "*") {
			return fmt.Errorf("route name %q must be one exact DNS name (no wildcards)", r.Name)
		}
		if seen[r.Name] {
			return fmt.Errorf("route name %q is listed twice", r.Name)
		}
		seen[r.Name] = true
		if h, port, err := net.SplitHostPort(r.Upstream); err != nil || h == "" || !validPort(port) {
			return fmt.Errorf("route %q: upstream must be host:port, got %q", r.Name, r.Upstream)
		}
	}
	return nil
}

func validPort(p string) bool { n, err := strconv.Atoi(p); return err == nil && n >= 1 && n <= 65535 }

// Load reads and validates a config file.
func Load(path string) (*Config, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c Config
	dec := json.NewDecoder(strings.NewReader(string(raw)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&c); err != nil {
		return nil, fmt.Errorf("relay config: %w", err)
	}
	return &c, c.Validate()
}

// Save writes the config atomically with mode 0600.
func (c *Config) Save(path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, append(raw, '\n'), 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
