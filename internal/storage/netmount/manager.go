// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"time"
)

// States a mount reports.
const (
	StateMounted   = "mounted"
	StateFailing   = "failing"
	StateUnmounted = "unmounted"
)

// Status is what GET and PUT answer for one mount.
type Status struct {
	ID       string    `json:"id"`
	State    string    `json:"state"`
	Protocol string    `json:"protocol,omitempty"`
	Access   string    `json:"access,omitempty"`
	Reason   string    `json:"reason,omitempty"`
	Message  string    `json:"message,omitempty"`
	Since    time.Time `json:"since"`
}

func (m *Manager) set(id string, st Status) Status {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.mounts == nil {
		m.mounts = map[string]*Status{}
	}
	if old := m.mounts[id]; old != nil && old.State == st.State && old.Reason == st.Reason {
		st.Since = old.Since
	}
	m.mounts[id] = &st
	return st
}

// update is set for a mount that is still known: a Check that raced an
// Unmount never brings the mount back into the list.
func (m *Manager) update(id string, st Status) Status {
	m.mu.Lock()
	known := m.mounts[id] != nil
	m.mu.Unlock()
	if !known {
		return st
	}
	return m.set(id, st)
}

// fingerprint names what a spec mounts (protocol, host, share, user and
// access) as a keyed hash, so a PUT that changes any of them is told apart
// from one that repeats the mount in place without keeping the fields. The
// password is left out: a new password for the same share does not need a
// remount.
func (m *Manager) fingerprint(s Spec) string {
	m.keyOnce.Do(func() { _, _ = rand.Read(m.key[:]) })
	h := hmac.New(sha256.New, m.key[:])
	for _, v := range []string{s.Protocol, source(s), s.User, s.access()} {
		h.Write([]byte(v))
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil))
}

// appliedIs reports whether the mount in place at id is the one fp names.
func (m *Manager) appliedIs(id, fp string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.applied[id] == fp
}

func (m *Manager) setApplied(id, fp string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.applied == nil {
		m.applied = map[string]string{}
	}
	if fp == "" {
		delete(m.applied, id)
		return
	}
	m.applied[id] = fp
}

// List is every mount this service made or was told about since it started.
func (m *Manager) List() []Status {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]Status, 0, len(m.mounts))
	for _, st := range m.mounts {
		out = append(out, *st)
	}
	return out
}

// healthy is "mounted, the marker hidden, and readable".
func (m *Manager) healthy(ctx context.Context, dir string) (string, string) {
	ok, err := m.mounted(dir)
	if err != nil || !ok {
		return "not_mounted", "The share is not mounted."
	}
	if _, err := os.Lstat(filepath.Join(dir, Marker)); err == nil {
		return "not_mounted", "The mount point still shows its marker; the share is not mounted."
	}
	if err := m.probe(ctx, dir); err != nil {
		return "unreachable", "The NAS does not answer; Files shows this location as failing until it is back."
	}
	return "", ""
}

// Check reads one mount and reports its state. An id this service never
// mounted (or not since it started) is answered but not recorded: a stray
// read never turns into a failing mount in the list.
func (m *Manager) Check(ctx context.Context, id string) (Status, error) {
	if !ValidID(id) {
		return Status{}, refuse("invalid_id", "That is not a mount id.")
	}
	m.mu.Lock()
	prev := m.mounts[id]
	m.mu.Unlock()
	reason, msg := m.healthy(ctx, m.dir(id))
	if prev == nil {
		st := Status{ID: id, State: StateUnmounted, Since: m.now()}
		if reason == "" {
			st.State = StateMounted
		}
		return st, nil
	}
	st := Status{ID: id, State: StateMounted, Protocol: prev.Protocol, Access: prev.Access, Since: m.now()}
	if reason != "" {
		st.State, st.Reason, st.Message = StateFailing, reason, msg
		if prev.State != StateFailing {
			m.log().Warn("network mount not healthy", "id", id, "reason", reason)
		}
	}
	return m.update(id, st), nil
}

// Mount makes sure the share is mounted at <Base>/<id>: a read-only test
// mount that must be readable first, then the mount with the access asked
// for. A healthy mount of exactly this spec (protocol, host, share, user,
// access) is left alone. Anything else at <Base>/<id> is detached first and
// the spec mounted again: a dead mount, another share or user, the other
// access (an owner who narrows rw to ro never keeps a writable mount), or a
// mount this service did not make since it started.
func (m *Manager) Mount(ctx context.Context, id string, s Spec) (st Status, err error) {
	if !ValidID(id) {
		return Status{}, refuse("invalid_id", "That is not a mount id.")
	}
	if err := s.Validate(); err != nil {
		return Status{}, err
	}
	if why := m.Unavailable(s.Protocol); why != "" {
		return Status{}, refuse("client_missing", why)
	}
	m.op.Lock()
	defer m.op.Unlock()
	defer func() {
		if err != nil {
			m.failed(id, err)
		}
	}()
	dir := m.dir(id)
	want := m.fingerprint(s)
	if ok, _ := m.mounted(dir); ok {
		reason, _ := m.healthy(ctx, dir)
		if reason == "" && m.appliedIs(id, want) {
			return m.set(id, Status{ID: id, State: StateMounted, Protocol: s.Protocol, Access: s.access(), Since: m.now()}), nil
		}
		m.setApplied(id, "")
		if reason == "" {
			m.umount(ctx, dir, false) // a live mount of another spec: a clean detach first
		}
		if still, _ := m.mounted(dir); still {
			m.umount(ctx, dir, true)
		}
		if still, _ := m.mounted(dir); still {
			return Status{}, refuse("busy", "The mount in place could not be released; the new one was not made.")
		}
	}
	if err := m.prepare(dir); err != nil {
		return Status{}, err
	}
	cred := ""
	if s.Protocol == SMB {
		f, err := m.writeCreds(s)
		if err != nil {
			return Status{}, err
		}
		defer os.Remove(f)
		cred = f
	}
	if err := m.mountOnce(ctx, dir, s, cred, "ro"); err != nil {
		return Status{}, err
	}
	if reason, msg := m.healthy(ctx, dir); reason != "" {
		m.umount(ctx, dir, true)
		return Status{}, refuse("test_failed", msg)
	}
	if s.access() == "rw" {
		m.umount(ctx, dir, false)
		if still, _ := m.mounted(dir); still { // never stack the rw mount on the test mount
			m.umount(ctx, dir, true)
			return Status{}, refuse("busy", "The test mount could not be released; nothing was mounted.")
		}
		if err := m.mountOnce(ctx, dir, s, cred, "rw"); err != nil {
			return Status{}, err
		}
		if reason, msg := m.healthy(ctx, dir); reason != "" {
			m.umount(ctx, dir, true)
			return Status{}, refuse("test_failed", msg)
		}
	}
	m.setApplied(id, want)
	m.log().Info("network share mounted", "id", id, "spec", s)
	return m.set(id, Status{ID: id, State: StateMounted, Protocol: s.Protocol, Access: s.access(), Since: m.now()}), nil
}

// failed records a Mount that failed after the lock: a mount that was known
// is failing now (whatever was in place was detached or is stuck), and its
// fingerprint is forgotten so the next PUT mounts it again. An id that was
// never known stays out of the list.
func (m *Manager) failed(id string, err error) {
	m.setApplied(id, "")
	m.mu.Lock()
	prev := m.mounts[id]
	m.mu.Unlock()
	if prev == nil {
		return
	}
	st := Status{ID: id, State: StateFailing, Protocol: prev.Protocol, Access: prev.Access,
		Reason: "mount_failed", Message: "The NAS share could not be mounted; see the hub's journal.", Since: m.now()}
	var ref *Refusal
	if errors.As(err, &ref) {
		st.Reason, st.Message = ref.Reason, ref.Message
	}
	m.set(id, st)
}

// Unmount detaches a mount (lazily when the NAS is gone) and forgets it.
// The empty mount point and its marker stay.
func (m *Manager) Unmount(ctx context.Context, id string) error {
	if !ValidID(id) {
		return refuse("invalid_id", "That is not a mount id.")
	}
	m.op.Lock()
	defer m.op.Unlock()
	dir := m.dir(id)
	if ok, _ := m.mounted(dir); ok {
		m.umount(ctx, dir, true)
		if still, _ := m.mounted(dir); still {
			return errors.New("the share is still mounted")
		}
	}
	m.mu.Lock()
	delete(m.mounts, id)
	delete(m.applied, id)
	m.mu.Unlock()
	return nil
}
