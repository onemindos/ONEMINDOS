// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"time"
)

// Target kinds (BACKUPS.md §4).
const (
	KindUSB  = "usb"  // local path on a disk found by filesystem UUID
	KindNode = "node" // another OneMind node running rest-server
	KindS3   = "s3"   // any S3-compatible endpoint
)

// Config is the agent's settings file (default /data/onemind/backup/agent.json).
// The gateway coordinator (BACKUPS.md K3) writes it; secrets are never inline,
// only paths to files in the secret store.
type Config struct {
	BoxID      string `json:"box_id"`  // instance id, tag box=<id>
	NodeID     string `json:"node_id"` // restic --host, tag node=<id>
	Generation int    `json:"generation"`

	StateDir   string `json:"state_dir"`   // state.json and hook staging
	ScratchDir string `json:"scratch_dir"` // verified-restore scratch space

	Restic        ResticConfig `json:"restic"`
	SQLite3Binary string       `json:"sqlite3_binary"` // for online SQLite copies

	// DeviceKeyFile holds the repository device key (BACKUPS.md §5.1).
	DeviceKeyFile string `json:"device_key_file"`

	Schedule  Schedule  `json:"schedule"`
	Retention Retention `json:"retention"`
	Targets   []Target  `json:"targets"`
	Units     UnitsSpec `json:"units"`
}

// ResticConfig locates the pinned restic binary.
type ResticConfig struct {
	Binary   string `json:"binary"`
	CacheDir string `json:"cache_dir"`
	// SkipPinCheck allows an unpinned binary (tests and development only).
	SkipPinCheck bool `json:"skip_pin_check"`
}

// Schedule sets when jobs run (BACKUPS.md §3). Minute < 0 means "derive a
// fixed minute from the box id", so boxes sharing a target do not all start
// on the hour.
type Schedule struct {
	Minute          int          `json:"minute"`
	MaintenanceHour int          `json:"maintenance_hour"` // daily check, off-site run
	VerifyWeekday   time.Weekday `json:"verify_weekday"`   // weekly verified restore and prune
	VerifyMinAge    Duration     `json:"verify_min_age"`   // newest snapshot at least this old
}

// Retention is the grandfather-father-son ladder applied after every run.
type Retention struct {
	Hourly  int `json:"hourly"`
	Daily   int `json:"daily"`
	Weekly  int `json:"weekly"`
	Monthly int `json:"monthly"`
}

// Target is one backup destination. Exactly the fields of its kind are used.
type Target struct {
	ID      string `json:"id"`
	Kind    string `json:"kind"`
	Name    string `json:"name"`
	Primary bool   `json:"primary"`

	// usb: the disk is mounted at MountRoot/<USBUUID>; the repository is
	// the "onemind-restic" directory on it.
	USBUUID          string `json:"usb_uuid,omitempty"`
	MountRoot        string `json:"mount_root,omitempty"`          // default /run/onemind/backup
	AllowNonMountDir bool   `json:"allow_non_mount_dir,omitempty"` // tests only

	// node: rest-server URL including the per-box repository path.
	URL          string `json:"url,omitempty"`
	CAFile       string `json:"ca_file,omitempty"`
	User         string `json:"user,omitempty"`
	PasswordFile string `json:"password_file,omitempty"`
	AppendOnly   bool   `json:"append_only,omitempty"`

	// s3
	Endpoint      string `json:"endpoint,omitempty"` // https://host[:port]
	Bucket        string `json:"bucket,omitempty"`
	Prefix        string `json:"prefix,omitempty"`
	Region        string `json:"region,omitempty"`
	AccessKeyFile string `json:"access_key_file,omitempty"`
	SecretKeyFile string `json:"secret_key_file,omitempty"`
}

// UnitsSpec says what each unit contains (BACKUPS.md §2).
type UnitsSpec struct {
	System *SystemSpec `json:"system,omitempty"`
	K3s    *K3sSpec    `json:"k3s,omitempty"`
	Apps   []AppSpec   `json:"apps,omitempty"`
	Node   *PathsSpec  `json:"node,omitempty"`
}

// PathsSpec is a set of directories or files copied as they are.
type PathsSpec struct {
	Paths    []string `json:"paths"`
	Excludes []string `json:"excludes,omitempty"`
}

// SQLiteFile is a database copied with the SQLite online backup into the
// unit's staging directory under Name, then integrity-checked.
type SQLiteFile struct {
	Path string `json:"path"`
	Name string `json:"name"`
}

// CommandHook runs Argv and stores its stdout as Name in the staging
// directory (for example pg_dump for a gateway on PostgreSQL).
type CommandHook struct {
	Name string   `json:"name"`
	Argv []string `json:"argv"`
}

// SystemSpec is the hub's `system` unit.
type SystemSpec struct {
	PathsSpec
	SQLite   []SQLiteFile  `json:"sqlite,omitempty"`   // the gateway database
	Commands []CommandHook `json:"commands,omitempty"` // gateway DB dump on PostgreSQL
	AuditLog string        `json:"audit_log,omitempty"`
}

// K3sSpec is the hub's `k3s` unit: the datastore plus token and config files.
type K3sSpec struct {
	PathsSpec
	StateDB string `json:"state_db"`
	Version string `json:"version"`
}

// AppSpec is one `app:<id>` unit on this node.
type AppSpec struct {
	ID       string       `json:"id"`
	Revision string       `json:"revision,omitempty"`
	Paths    []string     `json:"paths"`
	Excludes []string     `json:"excludes,omitempty"`
	SQLite   []SQLiteFile `json:"sqlite,omitempty"`
}

// Duration is a time.Duration that reads "1h" style strings from JSON.
type Duration struct{ time.Duration }

// UnmarshalJSON implements json.Unmarshaler.
func (d *Duration) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return err
	}
	v, err := time.ParseDuration(s)
	d.Duration = v
	return err
}

// MarshalJSON implements json.Marshaler.
func (d Duration) MarshalJSON() ([]byte, error) { return json.Marshal(d.String()) }

// DefaultConfig returns the documented defaults (BACKUPS.md §3).
func DefaultConfig() Config {
	return Config{
		StateDir:      "/data/onemind/backup",
		ScratchDir:    "/data/onemind/scratch",
		Restic:        ResticConfig{Binary: "/usr/lib/onemind/restic", CacheDir: "/var/cache/onemind-backup"},
		SQLite3Binary: "/usr/bin/sqlite3",
		DeviceKeyFile: "/data/onemind/secrets/backup-device.key",
		Schedule:      Schedule{Minute: -1, MaintenanceHour: 3, VerifyWeekday: time.Sunday, VerifyMinAge: Duration{time.Hour}},
		Retention:     Retention{Hourly: 24, Daily: 7, Weekly: 4, Monthly: 12},
	}
}

// LoadConfig reads a JSON settings file over the defaults and validates it.
func LoadConfig(path string) (Config, error) {
	c := DefaultConfig()
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	if err := json.Unmarshal(b, &c); err != nil {
		return c, fmt.Errorf("%s: %w", path, err)
	}
	return c, c.Validate()
}

// tagValueRe is the charset allowed in ids that end up in restic tags.
// restic splits tag lists on ',' and OneMind tags use '=' as separator.
var tagValueRe = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

// Validate checks the settings without touching the system.
func (c *Config) Validate() error {
	for name, v := range map[string]string{"box_id": c.BoxID, "node_id": c.NodeID} {
		if !tagValueRe.MatchString(v) {
			return fmt.Errorf("%s %q must be 1-128 characters of A-Z a-z 0-9 . _ : -", name, v)
		}
	}
	for name, p := range map[string]string{"state_dir": c.StateDir, "scratch_dir": c.ScratchDir,
		"restic.binary": c.Restic.Binary, "device_key_file": c.DeviceKeyFile} {
		if !filepath.IsAbs(p) {
			return fmt.Errorf("%s must be an absolute path, got %q", name, p)
		}
	}
	if c.Schedule.Minute > 59 || c.Schedule.MaintenanceHour < 0 || c.Schedule.MaintenanceHour > 23 {
		return fmt.Errorf("schedule: minute must be -1..59 and maintenance_hour 0..23")
	}
	r := c.Retention
	if r.Hourly < 0 || r.Daily < 0 || r.Weekly < 0 || r.Monthly < 0 || r.Hourly+r.Daily+r.Weekly+r.Monthly == 0 {
		return fmt.Errorf("retention: counts must be >= 0 and keep at least one snapshot")
	}
	seen, primaries := map[string]bool{}, 0
	for i := range c.Targets {
		t := &c.Targets[i]
		if err := t.validate(); err != nil {
			return fmt.Errorf("target %q: %w", t.ID, err)
		}
		if seen[t.ID] {
			return fmt.Errorf("target id %q used twice", t.ID)
		}
		seen[t.ID] = true
		if t.Primary {
			primaries++
		}
	}
	if len(c.Targets) > 0 && primaries != 1 {
		return fmt.Errorf("exactly one target must be primary, found %d", primaries)
	}
	for _, a := range c.Units.Apps {
		if !tagValueRe.MatchString(a.ID) || (a.Revision != "" && !tagValueRe.MatchString(a.Revision)) {
			return fmt.Errorf("app %q: id and revision must be tag-safe", a.ID)
		}
	}
	if k := c.Units.K3s; k != nil && k.Version != "" && !tagValueRe.MatchString(k.Version) {
		return fmt.Errorf("k3s version %q is not tag-safe", k.Version)
	}
	return nil
}

func (t *Target) validate() error {
	if !tagValueRe.MatchString(t.ID) {
		return fmt.Errorf("id must be tag-safe")
	}
	switch t.Kind {
	case KindUSB:
		if !regexp.MustCompile(`^[A-Za-z0-9-]{1,64}$`).MatchString(t.USBUUID) {
			return fmt.Errorf("usb_uuid must be a filesystem UUID")
		}
		if t.MountRoot == "" {
			t.MountRoot = "/run/onemind/backup"
		}
	case KindNode:
		if len(t.URL) < 9 || t.URL[:8] != "https://" {
			return fmt.Errorf("node url must be https:// (fabric TLS)")
		}
		if t.User == "" || t.PasswordFile == "" {
			return fmt.Errorf("node target needs user and password_file")
		}
	case KindS3:
		if t.Endpoint == "" || t.Bucket == "" || t.AccessKeyFile == "" || t.SecretKeyFile == "" {
			return fmt.Errorf("s3 target needs endpoint, bucket, access_key_file and secret_key_file")
		}
	default:
		return fmt.Errorf("kind must be usb, node or s3, got %q", t.Kind)
	}
	return nil
}

// Primary returns the primary target.
func (c *Config) Primary() (Target, bool) {
	for _, t := range c.Targets {
		if t.Primary {
			return t, true
		}
	}
	return Target{}, false
}

// Target returns the target with id.
func (c *Config) Target(id string) (Target, bool) {
	for _, t := range c.Targets {
		if t.ID == id {
			return t, true
		}
	}
	return Target{}, false
}

// RunMinute is the minute past the hour the hourly run starts.
func (c *Config) RunMinute() int {
	if c.Schedule.Minute >= 0 {
		return c.Schedule.Minute
	}
	h := sha256.Sum256([]byte("onemind-backup-minute:" + c.BoxID))
	return int(binary.BigEndian.Uint32(h[:4]) % 60)
}
