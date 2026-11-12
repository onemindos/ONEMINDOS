// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"gopkg.in/yaml.v3"
)

// Config is ~/.config/onemind/config.yaml (CLI.md §5). It never holds a secret.
type Config struct {
	Schema         string              `yaml:"schema"`
	CurrentContext string              `yaml:"current-context,omitempty"`
	Contexts       map[string]*Context `yaml:"contexts,omitempty"`
	path           string
}

// Context is one box.
type Context struct {
	Hub           string `yaml:"hub"`
	Principal     string `yaml:"principal,omitempty"`
	CAFingerprint string `yaml:"ca-fingerprint,omitempty"`
	Credential    string `yaml:"credential,omitempty"` // file (keychain: follow-up)
	InsecureHTTP  bool   `yaml:"insecure-http,omitempty"`
	Agent         bool   `yaml:"agent,omitempty"` // the credential is an agent token (onemind mcp login)
	BoxVersion    string `yaml:"box-version,omitempty"`
}

// Credentials is credentials.yaml next to the config, mode 0600.
type Credentials struct {
	Schema string            `yaml:"schema"`
	Tokens map[string]string `yaml:"tokens"`
}

const (
	configSchema = "onemind.cli.config/v1"
	credsSchema  = "onemind.cli.credentials/v1"
)

func configPath(flag string) (string, error) {
	if flag != "" {
		return flag, nil
	}
	if x := os.Getenv("XDG_CONFIG_HOME"); x != "" {
		return filepath.Join(x, "onemind", "config.yaml"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "onemind", "config.yaml"), nil
}

func loadConfig(flag string) (*Config, error) {
	p, err := configPath(flag)
	if err != nil {
		return nil, err
	}
	c := &Config{Schema: configSchema, Contexts: map[string]*Context{}, path: p}
	raw, err := os.ReadFile(p)
	if errors.Is(err, os.ErrNotExist) {
		return c, nil
	}
	if err != nil {
		return nil, err
	}
	if err := yaml.Unmarshal(raw, c); err != nil {
		return nil, fmt.Errorf("%s: %w", p, err)
	}
	if c.Contexts == nil {
		c.Contexts = map[string]*Context{}
	}
	return c, nil
}

func (c *Config) save() error {
	c.Schema = configSchema
	if err := os.MkdirAll(filepath.Dir(c.path), 0o700); err != nil {
		return err
	}
	raw, err := yaml.Marshal(c)
	if err != nil {
		return err
	}
	return writeFile0600(c.path, raw)
}

func (c *Config) names() []string {
	out := make([]string, 0, len(c.Contexts))
	for n := range c.Contexts {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}

func (c *Config) credsPath() string { return filepath.Join(filepath.Dir(c.path), "credentials.yaml") }

func (c *Config) loadCreds() (*Credentials, error) {
	cr := &Credentials{Schema: credsSchema, Tokens: map[string]string{}}
	raw, err := os.ReadFile(c.credsPath())
	if errors.Is(err, os.ErrNotExist) {
		return cr, nil
	}
	if err != nil {
		return nil, err
	}
	if err := yaml.Unmarshal(raw, cr); err != nil {
		return nil, fmt.Errorf("%s: %w", c.credsPath(), err)
	}
	if cr.Tokens == nil {
		cr.Tokens = map[string]string{}
	}
	return cr, nil
}

func (c *Config) saveCreds(cr *Credentials) error {
	cr.Schema = credsSchema
	if err := os.MkdirAll(filepath.Dir(c.path), 0o700); err != nil {
		return err
	}
	raw, err := yaml.Marshal(cr)
	if err != nil {
		return err
	}
	return writeFile0600(c.credsPath(), raw)
}

// writeFile0600 writes atomically with mode 0600 (also tightening an existing file).
func writeFile0600(path string, data []byte) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), ".tmp-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), path)
}
