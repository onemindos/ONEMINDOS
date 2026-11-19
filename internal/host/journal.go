// SPDX-License-Identifier: Apache-2.0

package host

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// ErrNotFound: no operation with that action id.
var ErrNotFound = errors.New("no such action")

// keep is how many finished operations the journal keeps (one per restart,
// shutdown or install: years of normal use).
const keep = 200

// Store is the journal: one JSON file per action id in a directory on /data,
// each written whole (temp file, fsync, rename, fsync of the directory), so a
// power cut leaves either the old record or the new one.
type Store struct{ dir string }

// OpenStore opens (and creates) the journal directory.
func OpenStore(dir string) (*Store, error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	s := &Store{dir: dir}
	return s, s.prune()
}

func (s *Store) path(id string) string { return filepath.Join(s.dir, id+".json") }

// Put writes op durably.
func (s *Store) Put(op Op) error {
	if !actionIDRe.MatchString(op.ID) {
		return fmt.Errorf("bad action id %q", op.ID)
	}
	b, err := json.MarshalIndent(op, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(s.dir, ".tmp-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err := f.Write(append(b, '\n')); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, s.path(op.ID)); err != nil {
		return err
	}
	d, err := os.Open(s.dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

// Get reads one operation.
func (s *Store) Get(id string) (Op, error) {
	var op Op
	if !actionIDRe.MatchString(id) {
		return op, ErrNotFound
	}
	b, err := os.ReadFile(s.path(id))
	if errors.Is(err, os.ErrNotExist) {
		return op, ErrNotFound
	} else if err != nil {
		return op, err
	}
	return op, json.Unmarshal(b, &op)
}

// List returns every operation, newest first. A record that does not parse is
// skipped (it can only be a foreign file: Put never leaves half a record).
func (s *Store) List() ([]Op, error) {
	ents, err := os.ReadDir(s.dir)
	if err != nil {
		return nil, err
	}
	var out []Op
	for _, e := range ents {
		name := e.Name()
		if !e.Type().IsRegular() || !strings.HasSuffix(name, ".json") {
			continue
		}
		if op, err := s.Get(strings.TrimSuffix(name, ".json")); err == nil {
			out = append(out, op)
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].AcceptedAt.After(out[j].AcceptedAt) })
	return out, nil
}

// prune drops the oldest finished operations beyond keep.
func (s *Store) prune() error {
	all, err := s.List()
	if err != nil {
		return err
	}
	n := 0
	for _, op := range all {
		if !Terminal(op.State) {
			continue
		}
		if n++; n > keep {
			_ = os.Remove(s.path(op.ID))
		}
	}
	return nil
}
