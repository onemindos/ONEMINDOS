// SPDX-License-Identifier: Apache-2.0

// Package netmount mounts a NAS share (SMB3 or NFSv4) on the hub so Files can
// show it as a `net:<id>` location (issue #718, nas-mount-engine).
//
// The gateway decides; this package only does what an owner approved. It gets
// the whole mount (host, share, user, password) in one call over the storage
// socket, and keeps none of it: the password goes into a 0600 credentials
// file on tmpfs that mount.cifs reads and that is deleted before the call
// returns, so it is never in argv (ps, /proc/*/cmdline), in a log line or in
// an error. Rules it keeps whatever the caller sends:
//
//   - SMB is always vers=3 (SMB 3.0 or later; SMB1 is never offered), with a
//     user and password: guest and anonymous access are refused.
//   - NFS is always vers=4 (no v2/v3 fallback).
//   - Admin and hidden shares (C$, ADMIN$) and NAS system exports (/, /etc,
//     /proc ...) are refused; the mount point is always <Base>/<id>.
//   - Every mount is first made read-only and read, then made with the access
//     asked for.
//   - A mount point holds a marker file while nothing is mounted on it. A
//     mount point with anything else in it is refused (data written there
//     while the NAS was away would hide under the mount), and the gateway
//     refuses to touch a `net:` root whose marker it can see.
//   - Check reads the mount with a timeout: a NAS that went away is `failing`,
//     and the same mount reads as `mounted` again when it is back. Mounts are
//     `soft`, so a dead server answers with an error instead of hanging.
package netmount

import (
	"io"
	"log/slog"
	"net"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// Protocols.
const (
	SMB = "smb"
	NFS = "nfs"
)

// Spec is one mount as the gateway sends it. Host, Share, User and Password
// come from the owner's sealed input; they are never logged.
type Spec struct {
	Protocol string `json:"protocol"`
	Host     string `json:"host"`
	Share    string `json:"share"`
	User     string `json:"user,omitempty"`
	Password string `json:"password,omitempty"`
	Access   string `json:"access,omitempty"` // ro (default) | rw
}

// String never shows the host, share, user or password.
func (s Spec) String() string { return "netmount.Spec{" + s.Protocol + " " + s.access() + "}" }

// GoString keeps %#v from printing the fields.
func (s Spec) GoString() string { return s.String() }

// LogValue keeps slog from printing the fields.
func (s Spec) LogValue() slog.Value {
	return slog.GroupValue(slog.String("protocol", s.Protocol), slog.String("access", s.access()))
}

func (s Spec) access() string {
	if s.Access == "" {
		return "ro"
	}
	return s.Access
}

// Refusal is a request this package will not carry out: a stable reason for
// code and a sentence for the owner. It never quotes the request.
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

func refuse(reason, msg string) error { return &Refusal{Reason: reason, Message: msg} }

var (
	idRE    = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,39}$`)
	labelRE = regexp.MustCompile(`^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$`)
	userRE  = regexp.MustCompile(`^([A-Za-z0-9][A-Za-z0-9._-]{0,63}\\)?[A-Za-z0-9._@-]{1,64}$`)
	// An SMB share name and optional folder: no separators, wildcards or option syntax.
	smbPartRE = regexp.MustCompile(`^[^\\/:*?"<>|,=\x00-\x1f\x7f]{1,80}$`)
	nfsPartRE = regexp.MustCompile(`^[A-Za-z0-9._@+ -]{1,255}$`)
	guests    = map[string]bool{"guest": true, "anonymous": true, "nobody": true}
	// NAS system exports (exact, or anything below): never a Files location.
	systemExports = []string{"/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/run", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/var/lib", "/var/run"}
	// Hub folders a mount base may never be.
	systemBases = []string{"/", "/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/run", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/var", "/tmp", "/home", "/data"}
)

// ValidID reports whether id can name a mount (and its folder).
func ValidID(id string) bool { return idRE.MatchString(id) }

func validHost(h string) error {
	if ip := net.ParseIP(h); ip != nil {
		if ip.To4() == nil {
			return refuse("ipv6_literal", "Use the NAS's name instead of an IPv6 address.")
		}
		if ip.IsUnspecified() || ip.IsMulticast() || ip.IsLoopback() {
			return refuse("invalid_host", "That address cannot be a NAS.")
		}
		return nil
	}
	if len(h) > 253 || h == "" {
		return refuse("invalid_host", "The NAS name is not a valid host name.")
	}
	for _, l := range strings.Split(h, ".") {
		if !labelRE.MatchString(l) {
			return refuse("invalid_host", "The NAS name is not a valid host name.")
		}
	}
	if strings.EqualFold(h, "localhost") {
		return refuse("invalid_host", "That address cannot be a NAS.")
	}
	return nil
}

// Validate checks a spec without touching anything.
func (s Spec) Validate() error {
	if err := validHost(s.Host); err != nil {
		return err
	}
	if a := s.access(); a != "ro" && a != "rw" {
		return refuse("invalid_access", "Access must be ro or rw.")
	}
	switch s.Protocol {
	case SMB:
		parts := strings.Split(strings.Trim(s.Share, "/"), "/")
		for _, p := range parts {
			if !smbPartRE.MatchString(p) || p == "." || p == ".." || strings.TrimSpace(p) == "" {
				return refuse("invalid_share", "The share name is not valid.")
			}
		}
		if strings.HasSuffix(parts[0], "$") {
			return refuse("system_share", "Admin and hidden shares (names ending in $) are never mounted.")
		}
		if s.User == "" || s.Password == "" || guests[strings.ToLower(userPart(s.User))] {
			return refuse("guest_refused", "A NAS share needs its own user and password; guest access is refused.")
		}
		if !userRE.MatchString(s.User) {
			return refuse("invalid_user", "The user name is not valid.")
		}
		if len(s.Password) > 256 || strings.ContainsAny(s.Password, "\x00\r\n") {
			return refuse("invalid_password", "The password may not contain line breaks and is at most 256 characters.")
		}
	case NFS:
		if s.User != "" || s.Password != "" {
			return refuse("nfs_no_credentials", "NFS shares use the hub's address, not a user and password.")
		}
		if !strings.HasPrefix(s.Share, "/") || s.Share == "/" {
			return refuse("system_share", "Name an export folder on the NAS, not its root.")
		}
		for _, p := range strings.Split(strings.Trim(s.Share, "/"), "/") {
			if !nfsPartRE.MatchString(p) || p == "." || p == ".." {
				return refuse("invalid_share", "The export path is not valid.")
			}
		}
		clean := filepath.Clean(s.Share)
		for _, sys := range systemExports {
			if clean == sys || strings.HasPrefix(clean, sys+"/") {
				return refuse("system_share", "System folders of the NAS are never mounted.")
			}
		}
	default:
		return refuse("invalid_protocol", "The protocol must be smb or nfs.")
	}
	return nil
}

func userPart(u string) string {
	if i := strings.LastIndex(u, `\`); i >= 0 {
		return u[i+1:]
	}
	return u
}

// MountedIn reports whether dir is a mount point in a mountinfo listing.
func MountedIn(r io.Reader, dir string) (bool, error) {
	b, err := io.ReadAll(io.LimitReader(r, 8<<20))
	if err != nil {
		return false, err
	}
	want := filepath.Clean(dir)
	for _, line := range strings.Split(string(b), "\n") {
		f := strings.Fields(line)
		if len(f) > 4 && unescape(f[4]) == want {
			return true, nil
		}
	}
	return false, nil
}

// unescape undoes mountinfo's octal escapes (\040 for a space).
func unescape(s string) string {
	if !strings.Contains(s, `\`) {
		return s
	}
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] == '\\' && i+4 <= len(s) {
			if n, err := strconv.ParseUint(s[i+1:i+4], 8, 8); err == nil {
				b.WriteByte(byte(n))
				i += 3
				continue
			}
		}
		b.WriteByte(s[i])
	}
	return b.String()
}

// redact takes every secret field out of program output before it is logged.
func redact(s string, sp Spec) string {
	for _, v := range []string{sp.Password, sp.User, sp.Host, sp.Share} {
		if len(v) >= 2 {
			s = strings.ReplaceAll(s, v, "[sealed]")
		}
	}
	return s
}

func tail(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) > n {
		s = "…" + s[len(s)-n:]
	}
	return s
}

// classify turns mount's output into a reason the owner can act on.
func classify(out string) error {
	o := strings.ToLower(out)
	switch {
	case strings.Contains(o, "permission denied") || strings.Contains(o, "logon failure") || strings.Contains(o, "access denied") || strings.Contains(o, "error(13)"):
		return refuse("auth_failed", "The NAS refused the user name or password.")
	case strings.Contains(o, "no such file") || strings.Contains(o, "error(2)") || strings.Contains(o, "bad network name"):
		return refuse("share_not_found", "The NAS has no share or export by that name.")
	case strings.Contains(o, "not supported") || strings.Contains(o, "error(95)") || strings.Contains(o, "protocol"):
		return refuse("protocol_refused", "The NAS does not offer SMB 3 or NFS 4; older versions are refused.")
	case strings.Contains(o, "host is down") || strings.Contains(o, "no route") || strings.Contains(o, "refused") ||
		strings.Contains(o, "timed out") || strings.Contains(o, "unreachable") || strings.Contains(o, "error(112)") ||
		strings.Contains(o, "could not connect") || strings.Contains(o, "error(111)") ||
		strings.Contains(o, "could not resolve") || strings.Contains(o, "resolve address"):
		return refuse("unreachable", "The NAS cannot be reached from the hub.")
	}
	return refuse("mount_failed", "The NAS share could not be mounted; see the hub's journal.")
}
