// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// Unit is something backed up and restored as one piece; each run makes
// one restic snapshot per unit (BACKUPS.md §2).
type Unit struct {
	Name     string   // system, k3s, app:<id>, node:<id>
	Paths    []string // copied as they are
	Excludes []string
	Tags     []string // extra key=value tags, e.g. app=<id>, rev=<r>, k3s=<v>
	// Hooks write consistent copies (database dumps, the audit log) into the
	// unit's staging directory, which is then backed up with Paths. A hook
	// error fails the unit and no snapshot is written.
	Hooks []Hook
}

// Hook prepares a consistent copy of something before the snapshot.
type Hook interface {
	// Prepare writes into staging and may return extra tags.
	Prepare(ctx context.Context, staging string) (tags []string, err error)
	// VerifyRestored checks the hook's file in a restored staging directory.
	VerifyRestored(ctx context.Context, staging string, snap Snapshot) error
}

// BuildUnits turns the settings into the units this node backs up, in run
// order: system and k3s first, then apps, then the node unit.
func BuildUnits(c *Config, r Runner) []Unit {
	if r == nil {
		r = ExecRunner{}
	}
	var units []Unit
	if s := c.Units.System; s != nil {
		u := Unit{Name: "system", Paths: s.Paths, Excludes: s.Excludes}
		for _, f := range s.SQLite {
			u.Hooks = append(u.Hooks, &SQLiteHook{Binary: c.SQLite3Binary, Path: f.Path, Name: f.Name, Runner: r})
		}
		for _, h := range s.Commands {
			u.Hooks = append(u.Hooks, &CommandOutputHook{Name: h.Name, Argv: h.Argv, Runner: r})
		}
		if s.AuditLog != "" {
			u.Hooks = append(u.Hooks, &AuditLogHook{Path: s.AuditLog})
		}
		units = append(units, u)
	}
	if k := c.Units.K3s; k != nil {
		u := Unit{Name: "k3s", Paths: k.Paths, Excludes: k.Excludes}
		if k.Version != "" {
			u.Tags = append(u.Tags, "k3s="+k.Version)
		}
		if k.StateDB != "" {
			u.Hooks = append(u.Hooks, &SQLiteHook{Binary: c.SQLite3Binary, Path: k.StateDB, Name: "state.db", Runner: r})
		}
		units = append(units, u)
	}
	for _, a := range c.Units.Apps {
		u := Unit{Name: "app:" + a.ID, Paths: a.Paths, Excludes: a.Excludes, Tags: []string{"app=" + a.ID}}
		if a.Revision != "" {
			u.Tags = append(u.Tags, "rev="+a.Revision)
		}
		for _, f := range a.SQLite {
			u.Hooks = append(u.Hooks, &SQLiteHook{Binary: c.SQLite3Binary, Path: f.Path, Name: f.Name, Runner: r})
		}
		units = append(units, u)
	}
	if n := c.Units.Node; n != nil {
		units = append(units, Unit{Name: "node:" + c.NodeID, Paths: n.Paths, Excludes: n.Excludes})
	}
	return units
}

// stagingName makes a unit name safe as a directory name.
func stagingName(unit string) string { return strings.NewReplacer(":", "_", "/", "_").Replace(unit) }

func safeFileName(name string) error {
	if name == "" || name != filepath.Base(name) || strings.HasPrefix(name, ".") || strings.ContainsAny(name, `'"\`) {
		return fmt.Errorf("hook output name %q must be a plain file name", name)
	}
	return nil
}

// SQLiteHook copies a live SQLite database with the online backup API
// (`sqlite3 <db> ".backup <copy>"`) and requires `PRAGMA integrity_check`
// on the copy to say "ok". A raw file copy of a database being written can
// be torn; the online backup cannot (BACKUPS.md §2, k3s row).
type SQLiteHook struct {
	Binary, Path, Name string
	Runner             Runner
}

// Prepare implements Hook.
func (h *SQLiteHook) Prepare(ctx context.Context, staging string) ([]string, error) {
	if err := safeFileName(h.Name); err != nil {
		return nil, err
	}
	if _, err := os.Stat(h.Path); err != nil {
		return nil, fmt.Errorf("sqlite %s: %w", h.Name, err)
	}
	dst := filepath.Join(staging, h.Name)
	if strings.ContainsAny(dst, `'"`) {
		return nil, fmt.Errorf("staging path %q cannot hold quotes", dst)
	}
	if stderr, _, err := h.Runner.Run(ctx, h.Binary, []string{h.Path, ".backup '" + dst + "'"}, nil, nil, io.Discard); err != nil {
		return nil, fmt.Errorf("sqlite online backup of %s: %v: %s", h.Name, err, lastLine(stderr))
	}
	return nil, h.integrity(ctx, dst)
}

func (h *SQLiteHook) integrity(ctx context.Context, db string) error {
	var out bytes.Buffer
	stderr, _, err := h.Runner.Run(ctx, h.Binary, []string{db, "PRAGMA integrity_check;"}, nil, nil, &out)
	if err != nil {
		return fmt.Errorf("integrity check of %s: %v: %s", h.Name, err, lastLine(stderr))
	}
	if got := strings.TrimSpace(out.String()); got != "ok" {
		return fmt.Errorf("integrity check of %s failed: %s", h.Name, lastLine([]byte(got)))
	}
	return nil
}

// VerifyRestored implements Hook.
func (h *SQLiteHook) VerifyRestored(ctx context.Context, staging string, _ Snapshot) error {
	return h.integrity(ctx, filepath.Join(staging, h.Name))
}

// CommandOutputHook stores a command's stdout as Name (for example pg_dump).
type CommandOutputHook struct {
	Name   string
	Argv   []string
	Runner Runner
}

// Prepare implements Hook.
func (h *CommandOutputHook) Prepare(ctx context.Context, staging string) ([]string, error) {
	if err := safeFileName(h.Name); err != nil {
		return nil, err
	}
	if len(h.Argv) == 0 {
		return nil, fmt.Errorf("hook %s has no command", h.Name)
	}
	f, err := os.OpenFile(filepath.Join(staging, h.Name), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	stderr, _, err := h.Runner.Run(ctx, h.Argv[0], h.Argv[1:], nil, nil, f)
	if err != nil {
		return nil, fmt.Errorf("hook %s: %v: %s", h.Name, err, lastLine(stderr))
	}
	return nil, f.Sync()
}

// VerifyRestored implements Hook: the dump must be non-empty.
func (h *CommandOutputHook) VerifyRestored(_ context.Context, staging string, _ Snapshot) error {
	fi, err := os.Stat(filepath.Join(staging, h.Name))
	if err != nil {
		return err
	}
	if fi.Size() == 0 {
		return fmt.Errorf("hook output %s is empty", h.Name)
	}
	return nil
}

// AuditLogHook copies the gateway's hash-chained audit log
// (core/onemind_core/audit.py), drops a half-written last line, checks that
// every line links to the one before (prev_hash = previous hash, seq + 1),
// and tags the snapshot with the head hash. Recomputing each hash needs the
// gateway's canonical JSON; the gateway's verifier does that on restore.
type AuditLogHook struct{ Path string }

const auditCopyName = "audit.jsonl"

// Prepare implements Hook.
func (h *AuditLogHook) Prepare(_ context.Context, staging string) ([]string, error) {
	b, err := os.ReadFile(h.Path)
	if err != nil {
		return nil, fmt.Errorf("audit log: %w", err)
	}
	if i := bytes.LastIndexByte(b, '\n'); i >= 0 {
		b = b[:i+1]
	} else {
		b = nil
	}
	head, err := auditChainHead(b)
	if err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(staging, auditCopyName), b, 0o600); err != nil {
		return nil, err
	}
	if head == "" {
		return nil, nil
	}
	return []string{"audit_head=" + head}, nil
}

// VerifyRestored implements Hook.
func (h *AuditLogHook) VerifyRestored(_ context.Context, staging string, snap Snapshot) error {
	b, err := os.ReadFile(filepath.Join(staging, auditCopyName))
	if err != nil {
		return err
	}
	head, err := auditChainHead(b)
	if err != nil {
		return err
	}
	if want := snap.Tag("audit_head"); want != head {
		return fmt.Errorf("restored audit head %q does not match tagged head %q", head, want)
	}
	return nil
}

func auditChainHead(b []byte) (string, error) {
	sc := bufio.NewScanner(bytes.NewReader(b))
	sc.Buffer(make([]byte, 64<<10), 16<<20)
	var prev string
	var prevSeq int64
	n := 0
	for sc.Scan() {
		n++
		var rec struct {
			Seq      int64  `json:"seq"`
			PrevHash string `json:"prev_hash"`
			Hash     string `json:"hash"`
		}
		if err := json.Unmarshal(sc.Bytes(), &rec); err != nil {
			return "", fmt.Errorf("audit log line %d: %v", n, err)
		}
		if len(rec.Hash) != 64 || !tagValueRe.MatchString(rec.Hash) {
			return "", fmt.Errorf("audit log line %d: bad hash", n)
		}
		if n > 1 && (rec.PrevHash != prev || rec.Seq != prevSeq+1) {
			return "", fmt.Errorf("audit log line %d: chain broken", n)
		}
		prev, prevSeq = rec.Hash, rec.Seq
	}
	return prev, sc.Err()
}
