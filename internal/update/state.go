// SPDX-License-Identifier: Apache-2.0

package update

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// envBadLimit: an "environment-bad" release is re-offered at most this many
// times (brief 30 B4.2 / B5, REC-DEC-45); "image-bad" is never retried.
const envBadLimit = 3

// ReadBox reads the board, RAUC compatible string, booted version and the
// health gate's trial marker. It reads the same files the gate does
// (os/gate/onemind-health-gate): /usr/lib/os-release and <gate_dir>/pending.
func ReadBox(c *Config) (Box, error) {
	var b Box
	osr, err := readKV(c.OSRelease)
	if err != nil {
		return b, fmt.Errorf("os-release: %w", err)
	}
	b.Version, b.Board = osr["ONEMIND_VERSION"], osr["ONEMIND_BOARD"]
	if b.Version == "" || b.Board == "" {
		return b, fmt.Errorf("%s has no ONEMIND_VERSION/ONEMIND_BOARD: not a OneMind image (developer installs use unattended-upgrades, contract §10.1)", c.OSRelease)
	}
	rc, err := readKV(c.RAUCConf)
	if err != nil {
		return b, fmt.Errorf("rauc system.conf: %w", err)
	}
	if b.Compatible = rc["compatible"]; b.Compatible == "" {
		return b, fmt.Errorf("%s: no compatible=", c.RAUCConf)
	}
	m, err := os.ReadFile(filepath.Join(c.GateDir, "pending"))
	switch {
	case err == nil && len(bytes.TrimSpace(m)) > 0:
		b.MarkerPresent = true
		if f := strings.Fields(string(m)); len(f) > 1 {
			b.MarkerVersion = f[1]
		}
	case err != nil && !errors.Is(err, os.ErrNotExist):
		return b, fmt.Errorf("trial marker: %w", err)
	}
	return b, nil
}

func readKV(p string) (map[string]string, error) {
	b, err := os.ReadFile(p)
	if err != nil {
		return nil, err
	}
	kv := map[string]string{}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		k, v, ok := strings.Cut(strings.TrimSpace(sc.Text()), "=")
		if ok && !strings.HasPrefix(k, "#") && !strings.HasPrefix(k, "[") {
			kv[strings.TrimSpace(k)] = strings.Trim(strings.TrimSpace(v), `"'`)
		}
	}
	return kv, sc.Err()
}

// BadReleases is the gate's per-device list (<gate_dir>/bad-releases), lines
// "<time> version=<v> verdict=image-bad|environment-bad".
type BadReleases struct {
	imageBad map[string]bool
	envBad   map[string]int
}

// ReadBadReleases reads the list; a missing file is an empty list.
func ReadBadReleases(c *Config) (BadReleases, error) {
	br := BadReleases{imageBad: map[string]bool{}, envBad: map[string]int{}}
	b, err := os.ReadFile(filepath.Join(c.GateDir, "bad-releases"))
	if errors.Is(err, os.ErrNotExist) {
		return br, nil
	} else if err != nil {
		return br, err
	}
	for _, line := range strings.Split(string(b), "\n") {
		var v, verdict string
		for _, f := range strings.Fields(line) {
			if s, ok := strings.CutPrefix(f, "version="); ok {
				v = s
			} else if s, ok := strings.CutPrefix(f, "verdict="); ok {
				verdict = s
			}
		}
		switch {
		case v == "":
		case verdict == "environment-bad":
			br.envBad[v]++
		default: // image-bad, or anything unknown: never retry
			br.imageBad[v] = true
		}
	}
	return br, nil
}

// Excluded returns why version must not be offered, or "".
func (b BadReleases) Excluded(v string) string {
	if b.imageBad[v] {
		return "gate verdict image-bad (never retried)"
	}
	if n := b.envBad[v]; n >= envBadLimit {
		return fmt.Sprintf("gate verdict environment-bad %d times (limit %d)", n, envBadLimit)
	}
	return ""
}

// Verdict returns the gate's last verdict recorded for v, or "".
func (b BadReleases) Verdict(v string) string {
	if b.imageBad[v] {
		return "image-bad"
	}
	if b.envBad[v] > 0 {
		return "environment-bad"
	}
	return ""
}

// ReadPostpone reads <state_dir>/postpone-until (one RFC 3339 time). Missing = zero.
func ReadPostpone(c *Config) (time.Time, error) {
	b, err := os.ReadFile(filepath.Join(c.StateDir, "postpone-until"))
	if errors.Is(err, os.ErrNotExist) {
		return time.Time{}, nil
	} else if err != nil {
		return time.Time{}, err
	}
	return time.Parse(time.RFC3339, strings.TrimSpace(string(b)))
}

// HistoryEntry is one finished update attempt (for the dashboard's Updates screen).
type HistoryEntry struct {
	At     string `json:"at"`
	From   string `json:"from"`
	To     string `json:"to"`
	Result string `json:"result"` // committed | rolled_back | error
	Detail string `json:"detail,omitempty"`
}

const historyMax = 20

// Status is <state_dir>/status.json. Its first six fields are the heartbeat's
// "update" object; the rest is local detail for `onemind update status`.
type Status struct {
	heartbeat.Update
	Decision      string         `json:"decision,omitempty"`
	Reason        string         `json:"reason,omitempty"`
	TargetVersion string         `json:"target_version,omitempty"` // being installed / last installed
	FromVersion   string         `json:"from_version,omitempty"`   // version the box ran when it installed
	Snapshot      string         `json:"snapshot,omitempty"`       // restic id or "none"
	Warnings      []string       `json:"warnings,omitempty"`
	History       []HistoryEntry `json:"history,omitempty"`
}

func statusPath(c *Config) string { return filepath.Join(c.StateDir, "status.json") }

// LoadStatus reads status.json; a missing file is a fresh idle status.
func LoadStatus(c *Config) (*Status, error) {
	st := &Status{Update: heartbeat.Update{Channel: c.Channel, State: heartbeat.UpdateIdle}}
	b, err := os.ReadFile(statusPath(c))
	if errors.Is(err, os.ErrNotExist) {
		return st, nil
	} else if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(b, st); err != nil {
		return nil, fmt.Errorf("status.json: %w", err)
	}
	st.Channel = c.Channel
	return st, nil
}

// Save writes status.json atomically (readers never see half a file).
func (s *Status) Save(c *Config) error {
	if err := os.MkdirAll(c.StateDir, 0o755); err != nil {
		return err
	}
	b, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	tmp := statusPath(c) + ".tmp"
	if err := os.WriteFile(tmp, append(b, '\n'), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, statusPath(c))
}

func (s *Status) addHistory(e HistoryEntry) {
	s.History = append([]HistoryEntry{e}, s.History...)
	if len(s.History) > historyMax {
		s.History = s.History[:historyMax]
	}
}

// Report returns the heartbeat "update" object from the status file at the
// config's state dir, or nil when there is none (onemindd then omits it).
func Report(c *Config) *heartbeat.Update {
	b, err := os.ReadFile(statusPath(c))
	if err != nil {
		return nil
	}
	var st Status
	if json.Unmarshal(b, &st) != nil || st.State == "" {
		return nil
	}
	u := st.Update
	u.Channel = c.Channel
	return &u
}
