// SPDX-License-Identifier: Apache-2.0

package watchdog

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"os"
	"strings"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/service"
)

// DefaultConfigPath is the watchdog's settings file. Its presence turns the service on.
const DefaultConfigPath = "/etc/onemind/watchdog.json"

// Config is the settings file. The alert key lives in its own file (mode 0600, in the secret
// store); the config only holds the path.
type Config struct {
	// HubTimeoutS is how long the hub may be silent (seconds, min 15, default 60).
	HubTimeoutS int `json:"hub_timeout_s"`
	// Hook is the local siren/speaker program and its fixed arguments (optional).
	Hook []string `json:"hook"`
	// Peers are LAN "host:port" targets for the alert push (optional; port defaults to 7481).
	Peers []string `json:"peers"`
	// KeyFile holds the shared alert key (required when Peers is set or Listen is true).
	KeyFile string `json:"key_file"`
	// Listen makes this machine accept LAN alerts from peers and run its own hook on them.
	Listen bool `json:"listen"`
	// ListenAddr defaults to ":7481".
	ListenAddr string `json:"listen_addr"`
}

// LoadConfig reads and validates the settings file.
func LoadConfig(path string) (Config, error) {
	var c Config
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	dec := json.NewDecoder(strings.NewReader(string(b)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&c); err != nil {
		return c, fmt.Errorf("watchdog config: %w", err)
	}
	return c, c.validate()
}

func (c *Config) validate() error {
	if c.HubTimeoutS != 0 && c.HubTimeoutS < int(minTimeout/time.Second) {
		return fmt.Errorf("watchdog config: hub_timeout_s must be at least %d", int(minTimeout/time.Second))
	}
	if (len(c.Peers) > 0 || c.Listen) && c.KeyFile == "" {
		return errors.New("watchdog config: key_file is required with peers or listen")
	}
	if len(c.Hook) == 0 && len(c.Peers) == 0 {
		return errors.New("watchdog config: set a hook, peers, or both: nothing would be alerted")
	}
	for i, p := range c.Peers {
		if !strings.Contains(p, ":") {
			c.Peers[i] = net.JoinHostPort(p, fmt.Sprint(DefaultPort))
		}
	}
	return nil
}

func readKey(path string) ([]byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, errors.New("alert key unreadable")
	}
	k := []byte(strings.TrimSpace(string(b)))
	if len(k) < 16 {
		return nil, errors.New("alert key too short (16 bytes minimum)")
	}
	return k, nil
}

// Service is the onemindd optional service. natsURL and seedFile are the same values the
// heartbeat agent uses; role is this machine's role (a hub does not watch itself).
func Service(natsURL, seedFile, role string) service.Service {
	return service.Service{
		Name: "watchdog",
		Enabled: func() bool {
			if role == "hub" {
				return false
			}
			_, err := os.Stat(DefaultConfigPath)
			return err == nil
		},
		Run: func(ctx context.Context, log *slog.Logger) error {
			c, err := LoadConfig(DefaultConfigPath)
			if err != nil {
				return err
			}
			return run(ctx, log, c, natsURL, seedFile)
		},
	}
}

func run(ctx context.Context, log *slog.Logger, c Config, natsURL, seedFile string) error {
	var key []byte
	if c.KeyFile != "" {
		var err error
		if key, err = readKey(c.KeyFile); err != nil {
			return err
		}
	}
	var alerters []Alerter
	if len(c.Hook) > 0 {
		alerters = append(alerters, Hook{Command: c.Hook})
	}
	if len(c.Peers) > 0 {
		alerters = append(alerters, LANPush{Peers: c.Peers, Key: key})
	}
	if c.Listen {
		addr := c.ListenAddr
		if addr == "" {
			addr = fmt.Sprintf(":%d", DefaultPort)
		}
		conn, err := net.ListenPacket("udp", addr)
		if err != nil {
			return fmt.Errorf("watchdog listen: %w", err)
		}
		var local []Alerter
		if len(c.Hook) > 0 {
			local = append(local, Hook{Command: c.Hook})
		}
		l := &Listener{Key: key, Alerters: local}
		go l.Serve(ctx, conn, func(e error) { log.Warn("lan alert rejected or failed", "err", e) })
	}
	m := New(Options{Timeout: time.Duration(c.HubTimeoutS) * time.Second, Alerters: alerters, Log: log})
	if natsURL != "" {
		_, closeFn, err := subscribeHub(natsURL, seedFile, m.Heartbeat, log)
		if err != nil {
			return err
		}
		defer closeFn()
	} else {
		log.Warn("watchdog has no NATS URL: it will report the hub down once the timeout passes")
	}
	m.Run(ctx)
	return nil
}

// subscribeHub listens to every node heartbeat and feeds the ones whose role is hub. It keeps
// retrying while the hub or the LAN is away: that is exactly the case being watched.
func subscribeHub(url, seedFile string, onHub func(hubID string), log *slog.Logger) (*nats.Subscription, func(), error) {
	opts := []nats.Option{
		nats.Name("onemindd-watchdog"),
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2 * time.Second),
	}
	if seedFile != "" {
		o, err := nats.NkeyOptionFromSeed(seedFile)
		if err != nil {
			return nil, nil, errors.New("watchdog: NATS seed unreadable")
		}
		opts = append(opts, o)
	}
	nc, err := nats.Connect(url, opts...)
	if err != nil {
		return nil, nil, fmt.Errorf("watchdog: %w", err)
	}
	sub, err := nc.Subscribe("onemind.node.*.status", func(msg *nats.Msg) { HandleHeartbeat(msg.Data, onHub) })
	if err != nil {
		nc.Close()
		return nil, nil, err
	}
	return sub, nc.Close, nil
}

// HandleHeartbeat parses one heartbeat payload and calls onHub when it came from the hub.
func HandleHeartbeat(data []byte, onHub func(hubID string)) {
	var s heartbeat.Status
	if json.Unmarshal(data, &s) != nil || s.Role != "hub" || heartbeat.ValidateNodeID(s.NodeID) != nil {
		return
	}
	onHub(s.NodeID)
}
