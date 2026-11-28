// SPDX-License-Identifier: Apache-2.0

package update

import (
	"bufio"
	"bytes"
	"fmt"
	"net"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

// DefaultConfigPath is where the box keeps its update settings.
const DefaultConfigPath = "/etc/onemind/update.conf"

// DefaultOfflineGrace and MaxOfflineGrace bound how stale mirror metadata may
// be (Year-1 exit criterion: a box offline 90 days still takes its next update).
// The cap is the one-year root lifetime of os/update/CHANNEL.md.
const (
	DefaultOfflineGrace = 90 * 24 * time.Hour
	MaxOfflineGrace     = 365 * 24 * time.Hour
)

// Channels (os/update/CHANNEL.md).
const (
	ChannelSecurity = "security"
	ChannelStable   = "stable"
	// ChannelCatalog is the signed Market catalog (catalog.go): its own TUF repository
	// and its own image-shipped root, never mixed with the OS channels.
	ChannelCatalog = "catalog"
)

// Policy is the owner's update policy (brief 30 BD-09).
type Policy string

// Policies. Default on both channels: notify (Z-02, founder 2026-11-28); auto is the owner's opt-in.
const (
	PolicyAuto   Policy = "auto"   // install inside the maintenance window
	PolicyNotify Policy = "notify" // report only; the owner runs `onemind update apply`
	PolicyOff    Policy = "off"    // opt-out: check and report, never install on its own
)

// Config is /etc/onemind/update.conf. The file is "key = value" lines;
// '#' starts a comment. Unknown keys are ignored (os/update/CHANNEL.md §4, so
// an older updater still reads a newer image's file) but recorded in Ignored,
// and the service logs them, so a typo stays visible.
type Config struct {
	Channel string // security | stable
	// URL is the channel's TUF metadata base URL (timestamp.json lives at URL/timestamp.json).
	URL string
	// TargetsURL is the base of the flat target files: a bundle is fetched
	// from TargetsURL/<basename(target path)> (CHANNEL.md §3). Default URL.
	// It may instead be a template with {path} {board} {version} {name}
	// {sha256} (e.g. a mirror that keeps the <board>/<version>/ directories).
	TargetsURL string
	Window     Window
	Policy     Policy
	// RequireSnapshot refuses to install when no pre-update restic snapshot
	// could be taken. Default: false on security (install anyway, warn), true on stable.
	RequireSnapshot bool

	ResticBinary       string // empty = restic not configured ("no snapshot")
	ResticRepository   string
	ResticPasswordFile string

	TUFRootDir  string // image-shipped roots: <dir>/<channel>/root.json
	StateDir    string // status.json, TUF cache, postpone-until, lock
	DownloadDir string // bundles (RAUC's data directory)
	GateDir     string // the health gate's state: pending (trial marker), bad-releases
	// ESPMarker is the pre-install handler's copy of the trial marker on the ESP.
	ESPMarker  string
	OSRelease  string // ONEMIND_VERSION / ONEMIND_BOARD
	RAUCConf   string // compatible=
	RAUCBinary string
	// RebootCommand is run (argv, split on spaces) to reboot at a safe point.
	RebootCommand []string
	// RebootInhibitFile: while it exists the reboot waits (mission-safe reboot,
	// BD-09: a robot or field kit creates it while it must not restart).
	RebootInhibitFile string
	CheckInterval     time.Duration
	// OfflineGrace is how long past its signed expiry TUF metadata may be and
	// still verify when it comes from a mirror the owner plugged in (USB stick
	// or LAN share, `--mirror`). Signatures, thresholds and rollback checks are
	// unchanged; only freshness is relaxed, because a box that was offline
	// cannot have fresh metadata. Online checks never use it. Default 90 days.
	OfflineGrace time.Duration
	// Ignored lists the unknown keys found in the file (sorted).
	Ignored []string
}

// Defaults returns the configuration for channel before the file is applied.
func Defaults(channel string) Config {
	c := Config{
		Channel:           channel,
		Window:            Window{Start: 2 * 60, End: 5 * 60},
		TUFRootDir:        "/usr/lib/onemind/tuf",
		StateDir:          "/data/onemind/update",
		DownloadDir:       "/data/rauc",
		GateDir:           "/data/onemind",
		ESPMarker:         "/boot/efi/onemind/pending",
		OSRelease:         "/usr/lib/os-release",
		RAUCConf:          "/etc/rauc/system.conf",
		RAUCBinary:        "/usr/bin/rauc",
		RebootCommand:     []string{"systemctl", "reboot"},
		RebootInhibitFile: "/run/onemind/reboot-inhibit",
		CheckInterval:     time.Hour,
		OfflineGrace:      DefaultOfflineGrace,
	}
	// Z-02 (founder, 2026-11-28): ask first on every channel. Nothing installs by itself until the
	// owner opts in to auto (owner.conf); security keeps installing without a snapshot when one is missing.
	c.Policy, c.RequireSnapshot = PolicyNotify, true
	if channel == ChannelSecurity {
		c.RequireSnapshot = false
	}
	return c
}

// LoadConfig reads and validates the config file at path.
func LoadConfig(path string) (*Config, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	c, err := ParseConfig(b)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return c, nil
}

// ParseConfig parses update.conf content.
func ParseConfig(b []byte) (*Config, error) { return parseConfig(b, false) }

// DefaultCatalogConfigPath is where the box keeps its catalog channel settings.
const DefaultCatalogConfigPath = "/etc/onemind/catalog.conf"

// ParseCatalogConfig parses catalog.conf: the same key = value format with
// channel = catalog (the default when the key is absent). Only url is required.
func ParseCatalogConfig(b []byte) (*Config, error) { return parseConfig(b, true) }

// LoadCatalogConfig reads and validates the catalog config file at path.
func LoadCatalogConfig(path string) (*Config, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	c, err := ParseCatalogConfig(b)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return c, nil
}

func parseConfig(b []byte, catalog bool) (*Config, error) {
	kv := map[string]string{}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for n := 1; sc.Scan(); n++ {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			return nil, fmt.Errorf("line %d: want key = value", n)
		}
		k, v = strings.TrimSpace(k), strings.Trim(strings.TrimSpace(v), `"`)
		if _, dup := kv[k]; dup {
			return nil, fmt.Errorf("line %d: %s set twice", n, k)
		}
		kv[k] = v
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}

	ch := kv["channel"]
	if catalog {
		if ch == "" {
			ch = ChannelCatalog
			kv["channel"] = ch
		}
		if ch != ChannelCatalog {
			return nil, fmt.Errorf("channel must be %q in catalog.conf, got %q", ChannelCatalog, ch)
		}
	} else if ch != ChannelSecurity && ch != ChannelStable {
		return nil, fmt.Errorf("channel must be %q or %q, got %q", ChannelSecurity, ChannelStable, ch)
	}
	c := Defaults(ch)
	if catalog {
		c.StateDir = "/data/onemind/catalog"
	}
	for k, v := range kv {
		var err error
		switch k {
		case "channel":
		case "url":
			c.URL = strings.TrimRight(v, "/")
		case "targets_url":
			c.TargetsURL = v
		case "window":
			c.Window, err = ParseWindow(v)
		case "policy":
			c.Policy = Policy(v)
			if c.Policy != PolicyAuto && c.Policy != PolicyNotify && c.Policy != PolicyOff {
				err = fmt.Errorf("must be auto, notify or off")
			}
		case "require_snapshot":
			c.RequireSnapshot, err = strconv.ParseBool(v)
		case "restic_binary":
			c.ResticBinary = v
		case "restic_repository":
			c.ResticRepository = v
		case "restic_password_file":
			c.ResticPasswordFile = v
		case "tuf_root_dir":
			c.TUFRootDir = v
		case "state_dir":
			c.StateDir = v
		case "download_dir":
			c.DownloadDir = v
		case "gate_dir":
			c.GateDir = v
		case "esp_marker":
			c.ESPMarker = v
		case "os_release":
			c.OSRelease = v
		case "rauc_conf":
			c.RAUCConf = v
		case "rauc_binary":
			c.RAUCBinary = v
		case "reboot_command":
			c.RebootCommand = strings.Fields(v)
			if len(c.RebootCommand) == 0 {
				err = fmt.Errorf("empty")
			}
		case "reboot_inhibit_file":
			c.RebootInhibitFile = v
		case "offline_grace":
			c.OfflineGrace, err = time.ParseDuration(v)
			if err == nil && (c.OfflineGrace < 0 || c.OfflineGrace > MaxOfflineGrace) {
				err = fmt.Errorf("must be between 0 and %s", MaxOfflineGrace)
			}
		case "check_interval":
			c.CheckInterval, err = time.ParseDuration(v)
			if err == nil && c.CheckInterval < time.Minute {
				err = fmt.Errorf("must be at least 1m")
			}
		default:
			c.Ignored = append(c.Ignored, k)
		}
		if err != nil {
			return nil, fmt.Errorf("%s = %q: %w", k, v, err)
		}
	}
	if err := checkURL(c.URL); err != nil {
		return nil, fmt.Errorf("url: %w", err)
	}
	sort.Strings(c.Ignored)
	if c.TargetsURL == "" {
		c.TargetsURL = c.URL
	} else if err := checkURL(strings.NewReplacer("{", "", "}", "").Replace(c.TargetsURL)); err != nil {
		return nil, fmt.Errorf("targets_url: %w", err)
	}
	if (c.ResticBinary != "") != (c.ResticRepository != "") {
		return nil, fmt.Errorf("restic_binary and restic_repository must be set together")
	}
	return &c, nil
}

// checkURL allows https anywhere and plain http only to loopback (a local
// mirror or the test repo). TUF already protects integrity and freshness;
// https adds confidentiality of which version a box runs.
func checkURL(raw string) error {
	if raw == "" {
		return fmt.Errorf("required")
	}
	u, err := url.Parse(raw)
	if err != nil {
		return err
	}
	switch u.Scheme {
	case "https":
		return nil
	case "http":
		h := u.Hostname()
		if h == "localhost" {
			return nil
		}
		if ip := net.ParseIP(h); ip != nil && ip.IsLoopback() {
			return nil
		}
		return fmt.Errorf("plain http is allowed only to loopback")
	}
	return fmt.Errorf("scheme must be https")
}

// ResticConfigured reports whether a pre-update snapshot can be taken.
func (c *Config) ResticConfigured() bool { return c.ResticBinary != "" && c.ResticRepository != "" }
