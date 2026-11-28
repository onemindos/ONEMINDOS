// SPDX-License-Identifier: Apache-2.0

// Package smb turns the gateway's list of approved shares into a Samba
// configuration and keeps Samba's accounts (FILES-SHARE-01, #235, D-017,
// docs/leap/core/FILE-SHARING.md). It runs inside `onemindd host serve`, which
// is root; the gateway never writes a Samba file.
//
// Rules the renderer holds, whatever the gateway sends:
//   - SMB2.10 and newer only (no SMB1), no guest, no anonymous access.
//   - A share is open to its own user only (valid users).
//   - Only LAN, link-local, mesh (CGNAT) and loopback addresses may connect
//     (hosts allow here; the unit's IPAddressAllow repeats it in the kernel).
//   - No symlinks, no wide links, no Unix extensions: nothing leaves the share.
//   - Files are written as the gateway's own Unix user, so the Files service
//     owns, counts and trashes them like any other file.
package smb

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

// Share is one entry of the gateway's desired list (docs/leap/core/FILE-SHARING.md).
type Share struct {
	ID         string `json:"id"`
	Kind       string `json:"kind"`                  // home | timemachine
	Name       string `json:"name"`                  // the SMB share name
	User       string `json:"user"`                  // the SMB account that may open it
	Path       string `json:"path"`                  // below the Files root, no leading slash
	QuotaBytes *int64 `json:"quota_bytes,omitempty"` // timemachine only
}

const (
	KindHome        = "home"
	KindTimeMachine = "timemachine"
	MaxShares       = 64
	MinTMBytes      = int64(1) << 30
)

var (
	idRe   = regexp.MustCompile(`^[A-Za-z0-9_-]{1,40}$`)
	nameRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,39}$`)
	userRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,31}$`)
	dirRe  = regexp.MustCompile(`^[a-z0-9_][a-z0-9_-]{0,47}$`)
)

// AllowedNets are the only peers that may reach Samba: the same list is in
// onemind-smb.service (IPAddressAllow).
var AllowedNets = []string{"127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
	"100.64.0.0/10", "::1", "fe80::/10", "fc00::/7"}

// Validate refuses a share the renderer could be tricked by. The path is the
// Files layout only: home/<dir> or .system/timemachine/<dir>.
func (s Share) Validate() error {
	if !idRe.MatchString(s.ID) {
		return fmt.Errorf("share id %q is not valid", s.ID)
	}
	if !nameRe.MatchString(s.Name) {
		return fmt.Errorf("share name %q is not valid", s.Name)
	}
	if !userRe.MatchString(s.User) {
		return fmt.Errorf("share %s: user %q is not valid", s.Name, s.User)
	}
	if s.User == "admin" || s.User == "root" {
		// admin is the owner's own Unix account (console and SSH); an SMB person of that name would share its shadow line
		return fmt.Errorf("share %s: the name %q is reserved", s.Name, s.User)
	}
	parts := strings.Split(s.Path, "/")
	switch {
	case s.Kind == KindHome && len(parts) == 2 && parts[0] == "home":
	case s.Kind == KindTimeMachine && len(parts) == 3 && parts[0] == ".system" && parts[1] == "timemachine":
	default:
		return fmt.Errorf("share %s: path %q is not a Files home or Time Machine folder", s.Name, s.Path)
	}
	if !dirRe.MatchString(parts[len(parts)-1]) {
		return fmt.Errorf("share %s: folder name %q is not valid", s.Name, parts[len(parts)-1])
	}
	if s.Kind == KindTimeMachine && (s.QuotaBytes == nil || *s.QuotaBytes < MinTMBytes) {
		return fmt.Errorf("share %s: a Time Machine share needs a size limit of at least 1 GiB", s.Name)
	}
	if s.Kind == KindHome && s.QuotaBytes != nil {
		return fmt.Errorf("share %s: only a Time Machine share has a size limit", s.Name)
	}
	return nil
}

// Validate checks the whole list: every share, unique names and paths.
func Validate(list []Share) error {
	if len(list) > MaxShares {
		return fmt.Errorf("at most %d shares", MaxShares)
	}
	names, paths := map[string]bool{}, map[string]bool{}
	for _, s := range list {
		if err := s.Validate(); err != nil {
			return err
		}
		if names[s.Name] || paths[s.Path] {
			return fmt.Errorf("share %s appears twice", s.Name)
		}
		names[s.Name], paths[s.Path] = true, true
	}
	return nil
}

// Users returns the distinct accounts of the list, sorted.
func Users(list []Share) []string {
	seen := map[string]bool{}
	var out []string
	for _, s := range list {
		if !seen[s.User] {
			seen[s.User] = true
			out = append(out, s.User)
		}
	}
	sort.Strings(out)
	return out
}

// Paths are the places Samba lives. State is on /data (the root is read-only).
type Paths struct {
	FilesRoot string // /data/onemind/files
	StateDir  string // /data/onemind/samba
	RunDir    string // /run/onemind-smb
	UnixUser  string // the gateway's Unix user: every file is written as it
}

// DefaultPaths is the image layout.
func DefaultPaths() Paths {
	return Paths{FilesRoot: "/data/onemind/files", StateDir: "/data/onemind/samba", RunDir: "/run/onemind-smb", UnixUser: "onemind"}
}

// RenderConf is smb.conf for the list. The list must have passed Validate.
func RenderConf(list []Share, p Paths) string {
	var b strings.Builder
	w := func(f string, a ...any) { fmt.Fprintf(&b, f+"\n", a...) }
	w("# Written by onemindd host serve (FILES-SHARE-01). Do not edit: it is rewritten from the gateway's approved list.")
	w("[global]")
	w("\tserver role = standalone server")
	w("\tsecurity = user")
	w("\tserver string = OneMind")
	w("\tserver min protocol = SMB2_10")
	w("\tserver smb encrypt = desired")
	w("\tmap to guest = Never")
	w("\tguest ok = no")
	w("\trestrict anonymous = 2")
	w("\tnull passwords = no")
	w("\thosts allow = %s", strings.Join(AllowedNets, " "))
	w("\thosts deny = ALL")
	w("\tdisable netbios = yes")
	w("\tsmb ports = 445")
	w("\tpassdb backend = tdbsam:%s/private/passdb.tdb", p.StateDir)
	w("\tprivate dir = %s/private", p.StateDir)
	w("\tstate directory = %s/state", p.StateDir)
	w("\tcache directory = %s/cache", p.StateDir)
	w("\tlock directory = %s", p.RunDir)
	w("\tpid directory = %s", p.RunDir)
	w("\tncalrpc dir = %s/ncalrpc", p.RunDir)
	w("\tlogging = systemd")
	w("\tload printers = no")
	w("\tprintcap name = /dev/null")
	w("\tdisable spoolss = yes")
	w("\tunix extensions = no")
	w("\twide links = no")
	w("\tfollow symlinks = no")
	if hasTM(list) {
		w("\tvfs objects = catia fruit streams_xattr")
		w("\tfruit:metadata = stream")
		w("\tfruit:model = MacSamba")
		w("\tfruit:posix_rename = yes")
		w("\tfruit:nfs_aces = no")
	}
	for _, s := range sorted(list) {
		w("")
		w("[%s]", s.Name)
		w("\tpath = %s/%s", p.FilesRoot, s.Path)
		w("\tvalid users = %s", s.User)
		w("\tread only = no")
		w("\tbrowseable = yes")
		w("\tforce user = %s", p.UnixUser)
		w("\tcreate mask = 0640")
		w("\tdirectory mask = 0750")
		if s.Kind == KindTimeMachine {
			w("\tvfs objects = catia fruit streams_xattr")
			w("\tfruit:time machine = yes")
			w("\tfruit:time machine max size = %dM", *s.QuotaBytes>>20)
		}
	}
	return b.String()
}

func hasTM(list []Share) bool {
	for _, s := range list {
		if s.Kind == KindTimeMachine {
			return true
		}
	}
	return false
}

func sorted(list []Share) []Share {
	out := append([]Share(nil), list...)
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// RenderAvahi is the mDNS record: SMB always, plus the Time Machine disk
// advertisement when there is such a share ("" when there are no shares).
func RenderAvahi(list []Share) string {
	if len(list) == 0 {
		return ""
	}
	var b strings.Builder
	b.WriteString("<?xml version=\"1.0\" standalone='no'?>\n<!DOCTYPE service-group SYSTEM \"avahi-service.dtd\">\n")
	b.WriteString("<service-group>\n  <name replace-wildcards=\"yes\">%h</name>\n")
	b.WriteString("  <service><type>_smb._tcp</type><port>445</port></service>\n")
	if hasTM(list) {
		b.WriteString("  <service>\n    <type>_adisk._tcp</type>\n    <port>9</port>\n    <txt-record>sys=waMa=0,adVF=0x100</txt-record>\n")
		i := 0
		for _, s := range sorted(list) {
			if s.Kind == KindTimeMachine {
				fmt.Fprintf(&b, "    <txt-record>dk%d=adVN=%s,adVF=0x82</txt-record>\n", i, s.Name)
				i++
			}
		}
		b.WriteString("  </service>\n")
	}
	b.WriteString("</service-group>\n")
	return b.String()
}
