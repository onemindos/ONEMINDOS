// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"golang.org/x/sys/unix"
)

// Symlink-safe file writing for restores.
//
// A restore runs as root while the app it restores may still be running as an
// ordinary user. If the restore resolved paths by name, the app could swap a
// directory for a symlink between the "is it safe?" check and the write, and
// root would then write into another app's volume or the k3s datastore (a
// time-of-check/time-of-use race). So nothing here ever uses a path string
// after it has been checked: every directory on the way is opened one step at
// a time with O_NOFOLLOW (a symlink makes the open fail), and every later
// operation names a file relative to the directory handle we already hold
// (openat, renameat, unlinkat). Swapping the path afterwards has no effect on
// where the bytes land.

// testHookAfterOpen runs after the destination directory is opened and before
// anything is written. Tests use it to simulate an app swapping a path.
var testHookAfterOpen func()

const dirFlags = unix.O_RDONLY | unix.O_DIRECTORY | unix.O_NOFOLLOW | unix.O_CLOEXEC

func errSymlinkPath(path string) error {
	return fmt.Errorf("%s goes through a symlink or a non-directory; refusing to restore", path)
}

// openDirNoFollow opens the absolute directory path one component at a time
// without following symlinks. With create it makes missing directories (0755).
func openDirNoFollow(path string, create bool) (int, error) {
	if !filepath.IsAbs(path) {
		return -1, fmt.Errorf("%s is not an absolute path", path)
	}
	fd, err := unix.Open("/", dirFlags, 0)
	if err != nil {
		return -1, err
	}
	for _, comp := range strings.Split(filepath.Clean(path), "/") {
		if comp == "" {
			continue
		}
		if comp == "." || comp == ".." {
			unix.Close(fd)
			return -1, fmt.Errorf("%s has a %q component", path, comp)
		}
		next, err := unix.Openat(fd, comp, dirFlags, 0)
		if errors.Is(err, unix.ENOENT) && create {
			if merr := unix.Mkdirat(fd, comp, 0o755); merr != nil && !errors.Is(merr, unix.EEXIST) {
				unix.Close(fd)
				return -1, merr
			}
			next, err = unix.Openat(fd, comp, dirFlags, 0)
		}
		unix.Close(fd)
		if err != nil {
			if errors.Is(err, unix.ELOOP) || errors.Is(err, unix.ENOTDIR) {
				return -1, errSymlinkPath(path)
			}
			return -1, err
		}
		fd = next
	}
	return fd, nil
}

// safeParent refuses a destination that is a symlink or whose existing
// ancestors include one. It is an early, friendly check: the writes below
// re-verify by holding the directory open.
func safeParent(dest string) error {
	var st unix.Stat_t
	if err := unix.Lstat(dest, &st); err == nil && st.Mode&unix.S_IFMT == unix.S_IFLNK {
		return fmt.Errorf("%s is a symlink; refusing to restore over it", dest)
	}
	fd, err := openDirNoFollow(filepath.Dir(dest), false)
	if errors.Is(err, unix.ENOENT) {
		return nil // the missing part is created without following anything
	}
	if err != nil {
		return err
	}
	unix.Close(fd)
	return nil
}

func tmpName(prefix string) string {
	var b [6]byte
	_, _ = rand.Read(b[:])
	return prefix + hex.EncodeToString(b[:])
}

// checkDestAt refuses a destination that is a symlink or (when notDir) a directory.
func checkDestAt(dfd int, name string, notDir bool) (exists bool, err error) {
	var st unix.Stat_t
	err = unix.Fstatat(dfd, name, &st, unix.AT_SYMLINK_NOFOLLOW)
	if errors.Is(err, unix.ENOENT) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	switch st.Mode & unix.S_IFMT {
	case unix.S_IFLNK:
		return true, fmt.Errorf("%s is a symlink; refusing to restore over it", name)
	case unix.S_IFDIR:
		if notDir {
			return true, fmt.Errorf("%s is now a directory; restore it as a directory or move it first", name)
		}
	}
	return true, nil
}

// writeFileAt creates a file next to name inside dfd, fills it with fill,
// gives it mode and mtime, and renames it over name.
func writeFileAt(dfd int, name string, mode os.FileMode, mtime time.Time, fill func(*os.File) error) error {
	tmp := tmpName(".onemind-restore-")
	fd, err := unix.Openat(dfd, tmp, unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0o600)
	if err != nil {
		return err
	}
	f := os.NewFile(uintptr(fd), tmp)
	fail := func(err error) error {
		f.Close()
		_ = unix.Unlinkat(dfd, tmp, 0)
		return err
	}
	if err := fill(f); err != nil {
		return fail(err)
	}
	if err := f.Sync(); err != nil {
		return fail(err)
	}
	if err := f.Chmod(mode.Perm()); err != nil {
		return fail(err)
	}
	if err := f.Close(); err != nil {
		_ = unix.Unlinkat(dfd, tmp, 0)
		return err
	}
	ts := []unix.Timespec{unix.NsecToTimespec(mtime.UnixNano()), unix.NsecToTimespec(mtime.UnixNano())}
	if err := unix.UtimesNanoAt(dfd, tmp, ts, unix.AT_SYMLINK_NOFOLLOW); err != nil {
		_ = unix.Unlinkat(dfd, tmp, 0)
		return err
	}
	if _, err := checkDestAt(dfd, name, true); err != nil {
		_ = unix.Unlinkat(dfd, tmp, 0)
		return err
	}
	if err := unix.Renameat(dfd, tmp, dfd, name); err != nil {
		_ = unix.Unlinkat(dfd, tmp, 0)
		return err
	}
	return nil
}

// removeAllAt deletes name inside dfd, never following a symlink.
func removeAllAt(dfd int, name string) error {
	var st unix.Stat_t
	if err := unix.Fstatat(dfd, name, &st, unix.AT_SYMLINK_NOFOLLOW); err != nil {
		if errors.Is(err, unix.ENOENT) {
			return nil
		}
		return err
	}
	if st.Mode&unix.S_IFMT != unix.S_IFDIR {
		return unix.Unlinkat(dfd, name, 0)
	}
	fd, err := unix.Openat(dfd, name, dirFlags, 0)
	if err != nil {
		return err
	}
	d := os.NewFile(uintptr(fd), name)
	names, err := d.Readdirnames(-1)
	if err != nil {
		d.Close()
		return err
	}
	for _, n := range names {
		if err := removeAllAt(int(d.Fd()), n); err != nil {
			d.Close()
			return err
		}
	}
	d.Close()
	return unix.Unlinkat(dfd, name, unix.AT_REMOVEDIR)
}

// copyTreeAt copies the trusted staging tree src into the directory dfd,
// creating everything relative to dfd without following symlinks. Symlinks
// in the snapshot are recreated as symlinks, never followed.
func copyTreeAt(src string, dfd int) error {
	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}
	for _, e := range entries {
		sp := filepath.Join(src, e.Name())
		fi, err := os.Lstat(sp)
		if err != nil {
			return err
		}
		st, _ := fi.Sys().(*syscall.Stat_t)
		ts := []unix.Timespec{unix.NsecToTimespec(fi.ModTime().UnixNano()), unix.NsecToTimespec(fi.ModTime().UnixNano())}
		switch {
		case fi.Mode()&os.ModeSymlink != 0:
			target, err := os.Readlink(sp)
			if err != nil {
				return err
			}
			if err := unix.Symlinkat(target, dfd, e.Name()); err != nil {
				return err
			}
			chownAt(dfd, e.Name(), st, unix.AT_SYMLINK_NOFOLLOW)
		case fi.IsDir():
			if err := unix.Mkdirat(dfd, e.Name(), 0o700); err != nil {
				return err
			}
			sub, err := unix.Openat(dfd, e.Name(), dirFlags, 0)
			if err != nil {
				return err
			}
			err = copyTreeAt(sp, sub)
			if err == nil {
				err = unix.Fchmod(sub, uint32(fi.Mode().Perm()))
			}
			unix.Close(sub)
			if err != nil {
				return err
			}
			chownAt(dfd, e.Name(), st, unix.AT_SYMLINK_NOFOLLOW)
			_ = unix.UtimesNanoAt(dfd, e.Name(), ts, unix.AT_SYMLINK_NOFOLLOW)
		case fi.Mode().IsRegular():
			in, err := os.Open(sp)
			if err != nil {
				return err
			}
			fd, err := unix.Openat(dfd, e.Name(), unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0o600)
			if err != nil {
				in.Close()
				return err
			}
			out := os.NewFile(uintptr(fd), e.Name())
			_, err = io.Copy(out, in)
			in.Close()
			if err == nil {
				err = out.Chmod(fi.Mode().Perm())
			}
			if cerr := out.Close(); err == nil {
				err = cerr
			}
			if err != nil {
				return err
			}
			chownAt(dfd, e.Name(), st, unix.AT_SYMLINK_NOFOLLOW)
			_ = unix.UtimesNanoAt(dfd, e.Name(), ts, unix.AT_SYMLINK_NOFOLLOW)
		}
		// sockets, devices and pipes are not restored
	}
	return nil
}

// chownAt gives the entry the staging copy's owner (best effort: only root
// can, and the restore runs as root).
func chownAt(dfd int, name string, st *syscall.Stat_t, flags int) {
	if st != nil {
		_ = unix.Fchownat(dfd, name, int(st.Uid), int(st.Gid), flags)
	}
}

func closeDir(fd int) { _ = unix.Close(fd) }

func renameAt(dfd int, from, to string) error { return unix.Renameat(dfd, from, dfd, to) }

// mkdirAt makes a new private directory name inside dfd and opens it.
func mkdirAt(dfd int, name string) (int, error) {
	if err := unix.Mkdirat(dfd, name, 0o700); err != nil {
		return -1, err
	}
	return unix.Openat(dfd, name, dirFlags, 0)
}

// setDirMeta gives the directory open as fd (named name inside dfd) its final mode and mtime.
func setDirMeta(fd, dfd int, name string, mode os.FileMode, mtime time.Time) error {
	if err := unix.Fchmod(fd, uint32(mode.Perm())); err != nil {
		return err
	}
	ts := []unix.Timespec{unix.NsecToTimespec(mtime.UnixNano()), unix.NsecToTimespec(mtime.UnixNano())}
	_ = unix.UtimesNanoAt(dfd, name, ts, unix.AT_SYMLINK_NOFOLLOW)
	return nil
}

// metaAt reads name's owner, mode and mtime inside dfd without following a symlink.
func metaAt(dfd int, name string) (dirMeta, error) {
	var st unix.Stat_t
	if err := unix.Fstatat(dfd, name, &st, unix.AT_SYMLINK_NOFOLLOW); err != nil {
		return dirMeta{}, err
	}
	if st.Mode&unix.S_IFMT == unix.S_IFLNK {
		return dirMeta{}, fmt.Errorf("%s is a symlink; refusing to restore over it", name)
	}
	return dirMeta{
		mode:  os.FileMode(st.Mode & 0o777),
		mtime: time.Unix(st.Mtim.Sec, st.Mtim.Nsec),
		uid:   int(st.Uid), gid: int(st.Gid),
		isDir: st.Mode&unix.S_IFMT == unix.S_IFDIR,
	}, nil
}

// applyMetaFd gives the open file or directory fd the owner and mode in m.
// As root a failed chown is real; unprivileged tests cannot chown.
func applyMetaFd(fd int, m dirMeta) error {
	if err := unix.Fchown(fd, m.uid, m.gid); err != nil && os.Geteuid() == 0 {
		return err
	}
	return unix.Fchmod(fd, uint32(m.mode.Perm()))
}
