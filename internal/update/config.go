// SPDX-License-Identifier: Apache-2.0

package update

import (
	"bufio"
	"bytes"
	"fmt"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

// DefaultConfigPath is where the box keeps its update settings.
const DefaultConfigPath = "/etc/onemind/update.conf"

// Channels (os/update/CHANNEL.md).
const (
	ChannelSecurity = "security"
	ChannelStable   = "stable"
)

// Policy is the owner's update policy (brief 30 BD-09).
type Policy string

// Policies. BD-09 defaults: security channel = auto, stable channel = notify.
const (
	PolicyAuto   Policy = "auto"   // install inside the maintenance window
	PolicyNotify Policy = "notify" // report only; the owner runs `onemind update apply`
	PolicyOff    Policy = "off"    // opt-out: check and report, never install on its own
)

// Config is /etc/onemind/update.conf. The file is "key = value" lines;
// '#' starts a comment. Unknown keys are an error, so a typo cannot silently
// leave a box on a default it was meant to change.
type Config struct {
	Channel string // security | stable
	// URL is the channel's TUF metadata base URL (timestamp.json lives at URL/timestamp.json).
	URL string
	// TargetsURL is where bundles are downloaded from. Default URL + "/targets/".
	// It may be a template with {path} {board} {version} {name} {sha256}
	// (for hosts with flat file names such as GitHub Releases assets).
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
	OSRelease   string // ONEMIND_VERSION / ONEMIND_BOARD
	RAUCConf    string // compatible=
	RAUCBinary  string
	// RebootCommand is run (argv, split on spaces) to reboot at a safe point.
	RebootCommand []string
	// RebootInhibitFile: while it exists the reboot waits (mission-safe reboot,
	// BD-09: a robot or field kit creates it while it must not restart).
	RebootInhibitFile string
	CheckInterval     time.Duration
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
		OSRelease:         "/usr/lib/os-release",
		RAUCConf:          "/etc/rauc/system.conf",
		RAUCBinary:        "/usr/bin/rauc",
		RebootCommand:     []string{"systemctl", "reboot"},
		RebootInhibitFile: "/run/onemind/reboot-inhibit",
		CheckInterval:     time.Hour,
	}
	c.Policy, c.RequireSnapshot = PolicyNotify, true
	if channel == ChannelSecurity {
		c.Policy, c.RequireSnapshot = PolicyAuto, false
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
func ParseConfig(b []byte) (*Config, error) {
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
	if ch != ChannelSecurity && ch != ChannelStable {
		return nil, fmt.Errorf("channel must be %q or %q, got %q", ChannelSecurity, ChannelStable, ch)
	}
	c := Defaults(ch)
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
		case "check_interval":
			c.CheckInterval, err = time.ParseDuration(v)
			if err == nil && c.CheckInterval < time.Minute {
				err = fmt.Errorf("must be at least 1m")
			}
		default:
			err = fmt.Errorf("unknown key")
		}
		if err != nil {
			return nil, fmt.Errorf("%s = %q: %w", k, v, err)
		}
	}
	if err := checkURL(c.URL); err != nil {
		return nil, fmt.Errorf("url: %w", err)
	}
	if c.TargetsURL == "" {
		c.TargetsURL = c.URL + "/targets/"
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
