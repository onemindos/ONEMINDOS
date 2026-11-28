// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"regexp"
	"strconv"
	"strings"
)

const (
	maxCopyBundle = 640 << 10 // fits the signed job envelope after base64
	maxCopyRecord = 32 << 10
)

var (
	copyID                = regexp.MustCompile("^[0-9a-f]{32}$").MatchString
	fullID                = regexp.MustCompile("^[0-9a-f]{64}$").MatchString
	errSovereignRetention = errors.New("a sovereign repository keeps its snapshots")
)

func copyBoxID(box string) bool {
	return len(box) <= 80 && tagValueRe.MatchString(box) && box != "." && box != ".."
}

type copyJob struct {
	Operation         string   `json:"operation"`
	TargetID          string   `json:"target_id"`
	BoxID             string   `json:"box_id"`
	CopyID            string   `json:"copy_id,omitempty"`
	RunID             string   `json:"run_id,omitempty"`
	Generation        int      `json:"generation,omitempty"`
	Repository        string   `json:"repository,omitempty"`
	Snapshots         []string `json:"snapshots,omitempty"`
	RecoveryKey       string   `json:"recovery_key,omitempty"`
	AttachRecoveryKey bool     `json:"attach_recovery_key,omitempty"`
	Record            []byte   `json:"record,omitempty"`
	Bundle            []byte   `json:"bundle,omitempty"`
}

type copyBackup struct {
	Repository string         `json:"repository"`
	Snapshots  []SnapshotInfo `json:"snapshots"`
	Generation int            `json:"generation"`
}

func (a *Agent) sovereignCopy(ctx context.Context, p copyJob) (any, error) {
	if !copyBoxID(p.BoxID) || (p.CopyID != "" && !copyID(p.CopyID)) {
		return nil, errors.New("invalid copy namespace")
	}
	if p.Operation == "publish" && (p.CopyID == "" || len(p.Bundle) == 0 || len(p.Bundle) > maxCopyBundle ||
		len(p.Record) == 0 || len(p.Record) > maxCopyRecord) {
		return nil, errors.New("invalid copy ID, record or bundle")
	}
	if err := a.acquire(ctx, "sovereign copy"); err != nil {
		return nil, err
	}
	defer a.release()
	t, ok := a.target(p.TargetID)
	if !ok || !t.Sovereign {
		return nil, errors.New("no such sovereign destination")
	}
	local := p.Operation == "prepare" || p.Operation == "publish"
	c := a.conf()
	if local && p.BoxID != c.BoxID {
		return nil, errors.New("a copy can only be published by its source box")
	}
	if p.Operation == "prepare" || p.Operation == "check" || p.Operation == "publish" {
		if p.Operation != "prepare" {
			if p.RecoveryKey == "" || strings.ContainsAny(p.RecoveryKey, "\r\n") {
				return nil, errors.New("the owner recovery key is required")
			}
			if !fullID(p.Repository) {
				return nil, errors.New("a valid repository ID is required")
			}
		}
		if p.Operation == "prepare" {
			p.Generation = c.Generation
		}
		if local && (p.Generation != c.Generation || a.Store.View().FencedBy > c.Generation) {
			return nil, errors.New("the source generation is no longer current")
		}
		c.BoxID = p.BoxID
		// A healthy local cache cannot stand in for bytes on the destination.
		c.Restic.CacheDir = ""
		repo, err := NewRestic(&c, t, nil)
		if err != nil {
			return nil, err
		}
		if !local {
			repo.Flags = append(repo.Flags, "--no-lock")
		}
		if t.Kind == KindUSB {
			if mounted, err := a.IsMount(t.MountRoot + "/" + t.USBUUID); !t.AllowNonMountDir && (err != nil || !mounted) {
				return nil, errors.New("backup destination is not mounted")
			}
		}
		if local {
			gen, err := a.newestFence(ctx, repo)
			if err != nil || gen > c.Generation {
				return nil, errors.New("cannot confirm that the source generation is current")
			}
		}
		if p.RecoveryKey != "" {
			recovery := *repo
			recovery.Env = append([]string(nil), repo.Env...)
			recovery.useRecoveryKey(p.RecoveryKey)
			if p.Operation == "publish" && p.AttachRecoveryKey {
				if err := attachCopyKey(ctx, repo, &recovery, p); err != nil {
					return nil, err
				}
			}
			repo = &recovery
		}
		point, err := repo.checkCopy(ctx, p)
		if err != nil {
			return nil, err
		}
		if p.Operation != "publish" {
			return point, nil
		}
	}
	store, err := a.openCopyStore(t, p.BoxID, p.Operation == "publish")
	if p.Operation == "list" && errors.Is(err, os.ErrNotExist) {
		return []string{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer store.close()
	if p.Operation == "list" {
		return store.records(ctx)
	}
	if p.CopyID == "" {
		return nil, errors.New("copy_id is required")
	}
	dir := p.CopyID + "/"
	switch p.Operation {
	case "record":
		return store.get(ctx, dir+"complete.json", maxCopyRecord)
	case "bundle":
		return store.get(ctx, dir+"box.omb", maxCopyBundle)
	case "publish":
		if err := putVerified(ctx, store, dir+"box.omb", p.Bundle); err != nil {
			return nil, err
		}
		return nil, putVerified(ctx, store, dir+"complete.json", p.Record)
	default:
		return nil, errors.New("unknown copy operation")
	}
}

func (r *Restic) useRecoveryKey(key string) {
	for i, setting := range r.Env {
		if strings.HasPrefix(setting, "RESTIC_PASSWORD_FILE=") {
			r.Env[i] = "RESTIC_PASSWORD=" + key
			return
		}
	}
}

// Publication can attach the already-confirmed kit to a destination added
// after kit issuance. Only the signed publish job can add the key.
func attachCopyKey(ctx context.Context, device, recovery *Restic, p copyJob) error {
	_, err := recovery.repositoryID(ctx)
	if err == nil {
		return nil
	}
	var resticErr *ResticError
	if !errors.As(err, &resticErr) || resticErr.ExitCode != exitWrongKey {
		return errors.New("cannot open the copy repository with this key")
	}
	id, err := device.repositoryID(ctx)
	if err != nil || id != p.Repository {
		return errors.New("copy repository identity does not match")
	}
	// Restic opens this password file once. Pipe the new key so the agent
	// leaves no plaintext kit file behind if it is interrupted.
	if err := device.addKey(ctx, "/dev/stdin", strings.NewReader(p.RecoveryKey+"\n")); err != nil {
		return errors.New("cannot attach the owner recovery key to this destination")
	}
	return nil
}

// putVerified handles retries after a lost reply and never replaces an object.
func putVerified(ctx context.Context, store copyStore, key string, data []byte) error {
	if err := store.put(ctx, key, data); err != nil && !errors.Is(err, os.ErrExist) {
		return err
	}
	got, err := store.get(ctx, key, int64(len(data)))
	if err == nil && bytes.Equal(got, data) {
		return nil
	}
	return fmt.Errorf("copy object %s could not be published and read back: %w",
		key, errors.Join(err, errors.New("bytes do not match")))
}

func (r *Restic) repositoryID(ctx context.Context) (string, error) {
	raw, err := r.output(ctx, "copy config", "cat", "config")
	if err != nil {
		return "", err
	}
	var config struct{ ID string }
	if json.Unmarshal(raw, &config) != nil || !fullID(config.ID) {
		return "", errors.New("invalid copy repository identity")
	}
	return config.ID, nil
}

func (r *Restic) checkCopy(ctx context.Context, p copyJob) (copyBackup, error) {
	id, err := r.repositoryID(ctx)
	if err != nil {
		return copyBackup{}, errors.New("cannot open the copy repository with this key")
	}
	if p.Repository != "" && p.Repository != id {
		return copyBackup{}, errors.New("copy repository identity does not match")
	}
	filter := []string{"onemind", "box=" + p.BoxID}
	snaps, err := r.Snapshots(ctx, filter)
	if err != nil {
		return copyBackup{}, errors.New("cannot list copy snapshots")
	}
	wanted := map[string]bool{}
	for _, id := range p.Snapshots {
		if !fullID(id) || wanted[id] {
			return copyBackup{}, errors.New("invalid copy snapshot list")
		}
		wanted[id] = true
	}
	out := copyBackup{Repository: id, Generation: p.Generation}
	hasSystem := false
	for _, s := range snaps {
		if !wanted[s.ID] || s.Tag("unit") == "" || s.Tag("unit") == "fence" ||
			s.Tag("gen") != strconv.Itoa(p.Generation) || s.Tag("run") != p.RunID {
			continue
		}
		out.Snapshots = append(out.Snapshots, toInfo(s))
		hasSystem = hasSystem || s.Tag("unit") == "system"
	}
	if !hasSystem || len(out.Snapshots) != len(wanted) {
		return copyBackup{}, errors.New("one or more required copy snapshots are missing")
	}
	// Dump reads and authenticates every blob reachable by each required
	// snapshot. Damage confined to a newer copy need not hide an older copy.
	if p.Operation != "prepare" {
		for _, s := range out.Snapshots {
			if _, err := r.run(ctx, "check copy data", nil, io.Discard, "dump", s.ID, "/"); err != nil {
				return copyBackup{}, errors.New("a required copy snapshot failed its data check")
			}
		}
	}
	return out, nil
}
