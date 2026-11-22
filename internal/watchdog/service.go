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

// LinkFunc reports this node's leaf link to the hub: "up", "down" or "none" (not checked yet).
// internal/leaf Supervisor.Link is the real one.
type LinkFunc func() string

// Service is the onemindd optional service. link is the leaf supervisor's link state and joined
// says whether `onemind fabric join` ran here; role is this machine's role (a hub does not watch
// itself, and an unjoined machine has no hub to watch).
//
// Why the leaf link and not the hub's status subject: a joined node's NATS URL points at its own
// leaf, and the node's account imports only its own job subjects, so the hub's heartbeat never
// reaches it. The leaf connection to the hub is up exactly while the hub's NATS answers, which
// is what a pulled power cord stops.
func Service(link LinkFunc, joined func() bool, role string) service.Service {
	return service.Service{
		Name: "watchdog",
		Enabled: func() bool {
			if role == "hub" || link == nil || (joined != nil && !joined()) {
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
			return run(ctx, log, c, link)
		},
	}
}

func run(ctx context.Context, log *slog.Logger, c Config, link LinkFunc) error {
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
	go WatchLink(ctx, link, LinkPollEvery, m.Heartbeat)
	m.Run(ctx)
	return nil
}

// LinkPollEvery is how often the leaf link is read. The supervisor itself checks every 10 s.
const LinkPollEvery = 2 * time.Second

// HubLinkID names the hub in alerts: the leaf link does not carry the hub's node id.
const HubLinkID = "hub"

// WatchLink reads the link every period until ctx ends and calls onHub while it is "up". "down"
// and "none" count as silence, so a leaf that never connects alerts after the timeout too.
func WatchLink(ctx context.Context, link LinkFunc, every time.Duration, onHub func(hubID string)) {
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		if link() == "up" {
			onHub(HubLinkID)
		}
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}
