// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/unix"
)

// The pinned restic speaks REST over Unix sockets. Serve its repository with
// descriptor-relative, no-follow operations while it reads backup sources and
// writes restore staging as usual. The NAS keeps the ordinary restic layout.
func serveNASRestic(mount, box string, create bool) (string, func(), error) {
	fd, err := openDirNoFollow(mount, false)
	if err != nil {
		return "", nil, err
	}
	for _, part := range []string{"boxes", box, "data"} {
		next, err := nasResticDir(fd, part, create)
		closeDir(fd)
		if err != nil {
			return "", nil, err
		}
		fd = next
	}
	root := os.NewFile(uintptr(fd), "NAS repository")
	control, err := root.SyscallConn()
	if err != nil {
		root.Close()
		return "", nil, err
	}
	dir, err := os.MkdirTemp("", "om-restic-")
	if err != nil {
		root.Close()
		return "", nil, err
	}
	socket := filepath.Join(dir, "repo.sock")
	l, err := net.Listen("unix", socket)
	if err != nil {
		root.Close()
		os.RemoveAll(dir)
		return "", nil, err
	}
	srv := &http.Server{ReadHeaderTimeout: 5 * time.Second, Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// The duplicate remains valid even if the command is canceled and the
		// server closes the original while this request is finishing.
		var dfd int
		var openErr error
		if err := control.Control(func(fd uintptr) {
			dfd, openErr = unix.Openat(int(fd), ".", dirFlags, 0)
		}); err != nil || openErr != nil {
			http.Error(w, "repository unavailable", http.StatusServiceUnavailable)
			return
		}
		defer closeDir(dfd)
		if err := nasResticRequest(dfd, w, r); err != nil {
			status := http.StatusInternalServerError
			switch {
			case errors.Is(err, unix.ENOENT):
				status = http.StatusNotFound
			case errors.Is(err, unix.ENOTDIR), errors.Is(err, unix.ELOOP), errors.Is(err, unix.EACCES), errors.Is(err, unix.EPERM):
				status = http.StatusForbidden
			case errors.Is(err, unix.ENOSPC):
				status = http.StatusInsufficientStorage
			}
			http.Error(w, http.StatusText(status), status)
		}
	})}
	go func() { _ = srv.Serve(l) }()
	return "rest:http+unix://" + socket + ":/", func() {
		_ = l.Close()
		_ = srv.Close()
		_ = root.Close()
		_ = os.RemoveAll(dir)
	}, nil
}

func nasResticDir(fd int, name string, create bool) (int, error) {
	if create {
		err := unix.Mkdirat(fd, name, 0o700)
		if err == nil {
			err = unix.Fsync(fd)
		}
		if err != nil && !errors.Is(err, unix.EEXIST) {
			return -1, err
		}
	}
	return unix.Openat(fd, name, dirFlags, 0)
}

func nasResticRequest(fd int, w http.ResponseWriter, r *http.Request) error {
	if r.Method == http.MethodPost && r.URL.Path == "/" && r.URL.RawQuery == "create=true" {
		return nil // the repository root was created before starting restic init
	}
	if r.URL.Path == "/config" {
		return nasResticObject(fd, "config", false, w, r)
	}
	dir, name, _ := strings.Cut(strings.TrimPrefix(r.URL.Path, "/"), "/")
	switch dir {
	case "data", "keys", "locks", "snapshots", "index":
	default:
		return unix.EACCES
	}
	if name == "" && r.Method == http.MethodGet {
		return nasResticList(fd, dir, w)
	}
	if !fullID(name) {
		return unix.EACCES
	}
	sub, err := nasResticDir(fd, dir, r.Method == http.MethodPost)
	if err != nil {
		return err
	}
	defer closeDir(sub)
	if dir == "data" {
		packDir, err := nasResticDir(sub, name[:2], r.Method == http.MethodPost)
		if err != nil {
			return err
		}
		defer closeDir(packDir)
		sub = packDir
	}
	return nasResticObject(sub, name, dir == "locks", w, r)
}

func nasResticObject(fd int, name string, lock bool, w http.ResponseWriter, r *http.Request) error {
	var st unix.Stat_t
	err := unix.Fstatat(fd, name, &st, unix.AT_SYMLINK_NOFOLLOW)
	if err == nil && st.Mode&unix.S_IFMT != unix.S_IFREG {
		return unix.EACCES
	}
	switch r.Method {
	case http.MethodPost:
		if err != nil && !errors.Is(err, unix.ENOENT) {
			return err
		}
		return nasResticSave(fd, name, r.Body)
	case http.MethodDelete:
		if !lock {
			return unix.EACCES
		}
		if err != nil {
			return err
		}
		return unix.Unlinkat(fd, name, 0)
	case http.MethodGet, http.MethodHead:
		if err != nil {
			return err
		}
		f, err := openNASResticFile(fd, name)
		if err != nil {
			return err
		}
		defer f.Close()
		w.Header().Set("Content-Type", "application/octet-stream")
		http.ServeContent(w, r, name, time.Time{}, f)
		return nil
	default:
		return unix.EACCES
	}
}

func openNASResticFile(fd int, name string) (*os.File, error) {
	raw, err := unix.Openat(fd, name, unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}
	f := os.NewFile(uintptr(raw), name)
	info, err := f.Stat()
	if err == nil && !info.Mode().IsRegular() {
		err = unix.EACCES
	}
	if err != nil {
		f.Close()
		return nil, err
	}
	return f, nil
}

func nasResticSave(fd int, name string, body io.Reader) error {
	tmp := tmpName(".onemind-restic-")
	raw, err := unix.Openat(fd, tmp, unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0o600)
	if err != nil {
		return err
	}
	defer unix.Unlinkat(fd, tmp, 0)
	f := os.NewFile(uintptr(raw), tmp)
	incoming := sha256.New()
	_, err = io.Copy(io.MultiWriter(f, incoming), body)
	if err = errors.Join(err, f.Sync(), f.Close()); err != nil {
		return err
	}
	if err := unix.Linkat(fd, tmp, fd, name, 0); errors.Is(err, unix.EEXIST) {
		// A lost reply can cause restic to resend an immutable object.
		existing, err := openNASResticFile(fd, name)
		if err != nil {
			return err
		}
		sum := sha256.New()
		_, err = io.Copy(sum, existing)
		if err = errors.Join(err, existing.Close()); err != nil {
			return err
		}
		if !bytes.Equal(sum.Sum(nil), incoming.Sum(nil)) {
			return unix.EACCES
		}
	} else if err != nil {
		return err
	}
	return unix.Fsync(fd)
}

type nasResticEntry struct {
	Name string `json:"name"`
	Size int64  `json:"size"`
}

func nasResticList(fd int, name string, w http.ResponseWriter) error {
	entries := []nasResticEntry{}
	if err := nasResticListDir(fd, name, name == "data", &entries); err != nil {
		return err
	}
	w.Header().Set("Content-Type", "application/vnd.x.restic.rest.v2")
	_ = json.NewEncoder(w).Encode(entries)
	return nil
}

func nasResticListDir(parent int, name string, packs bool, entries *[]nasResticEntry) error {
	fd, err := nasResticDir(parent, name, false)
	if err != nil {
		return err
	}
	dir := os.NewFile(uintptr(fd), name)
	defer dir.Close()
	names, err := dir.Readdirnames(-1)
	if err != nil {
		return err
	}
	for _, name := range names {
		if packs {
			if len(name) == 2 && strings.Trim(name, "0123456789abcdef") == "" {
				if err := nasResticListDir(fd, name, false, entries); err != nil && !errors.Is(err, unix.ENOENT) {
					return err
				}
			}
			continue
		}
		if !fullID(name) {
			continue
		}
		var st unix.Stat_t
		err := unix.Fstatat(fd, name, &st, unix.AT_SYMLINK_NOFOLLOW)
		if errors.Is(err, unix.ENOENT) { // a lock can be removed during listing
			continue
		}
		if err != nil {
			return err
		}
		if st.Mode&unix.S_IFMT != unix.S_IFREG {
			return unix.EACCES
		}
		*entries = append(*entries, nasResticEntry{Name: name, Size: st.Size})
	}
	return nil
}
