// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/onemindos/onemindos/internal/service"
)

// DefaultConfPath is where `onemind fabric join` writes the node's leaf.conf.
const DefaultConfPath = "/etc/onemind/nats/leaf.conf"

// DefaultConfigPath is the persisted Config of this node's leaf. `onemind fabric join` writes it
// beside fabric.json (0644: paths and names only, the nkey seed stays in its own 0600 file), and
// onemindd, whose sandbox cannot read /etc/onemind/nats, loads it at start (CORE-NET-12).
const DefaultConfigPath = "/etc/onemind/leaf-config.json"

// DefaultUnit is the leaf's systemd unit (deploy/systemd/onemind-nats-leaf.service).
const DefaultUnit = "onemind-nats-leaf.service"

// SaveConfig writes c as JSON, atomically, after validating it.
func SaveConfig(path string, c *Config) (bool, error) {
	if err := c.Validate(); err != nil {
		return false, err
	}
	raw, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return false, err
	}
	return writeAtomic(path, append(raw, '\n'), 0o644)
}

// LoadConfig reads and validates a Config written by SaveConfig.
func LoadConfig(path string) (*Config, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c Config
	if err := json.Unmarshal(raw, &c); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if err := c.Validate(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return &c, nil
}

// NewSupervisor is the supervisor onemindd runs on a joined node: it loads the persisted Config
// (defaults when there is none yet), watches the loopback monitor, reloads the leaf unit when
// the Config changes and restarts it after repeated failed checks. unit "" means DefaultUnit.
func NewSupervisor(confPath, configPath, unit string, log *slog.Logger) *Supervisor {
	if unit == "" {
		unit = DefaultUnit
	}
	s := &Supervisor{
		ConfPath: confPath, ConfigPath: configPath, Config: &Config{}, ReadOnly: true,
		Reload: SystemdReload(unit), Restart: systemdRestart(unit), Interval: 10 * time.Second, Log: log,
	}
	if c, err := LoadConfig(configPath); err == nil {
		s.Config = c
	} else if !errors.Is(err, os.ErrNotExist) && log != nil {
		log.Warn("nats leaf config not loaded, using defaults", "path", configPath, "err", err)
	}
	return s
}

// Service runs the supervisor inside onemindd. enabled says whether this machine has a leaf.
func (s *Supervisor) Service(enabled func() bool) service.Service {
	return service.Service{
		Name:    "leaf",
		Enabled: enabled,
		Run: func(ctx context.Context, log *slog.Logger) error {
			if s.Log == nil {
				s.Log = log
			}
			s.Run(ctx)
			return nil
		},
	}
}
