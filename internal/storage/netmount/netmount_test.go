// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"bytes"
	"errors"
	"log/slog"
	"strings"
	"testing"
)

const secret = "hunter2-Sealed!"

func smbSpec() Spec {
	return Spec{Protocol: SMB, Host: "nas.example", Share: "family", User: "alex", Password: secret}
}

func reason(err error) string {
	var r *Refusal
	if errors.As(err, &r) {
		return r.Reason
	}
	return ""
}

func TestValidateRefusesGuestSystemPathsAndInjection(t *testing.T) {
	smb := func(mut func(*Spec)) Spec { s := smbSpec(); mut(&s); return s }
	nfs := func(share string) Spec { return Spec{Protocol: NFS, Host: "192.0.2.10", Share: share} }
	for name, tc := range map[string]struct {
		s    Spec
		want string
	}{
		"no user":          {smb(func(s *Spec) { s.User = "" }), "guest_refused"},
		"no password":      {smb(func(s *Spec) { s.Password = "" }), "guest_refused"},
		"guest":            {smb(func(s *Spec) { s.User = "Guest" }), "guest_refused"},
		"domain guest":     {smb(func(s *Spec) { s.User = `WORK\anonymous` }), "guest_refused"},
		"admin share":      {smb(func(s *Spec) { s.Share = "C$" }), "system_share"},
		"ipc share":        {smb(func(s *Spec) { s.Share = "IPC$/x" }), "system_share"},
		"option in share":  {smb(func(s *Spec) { s.Share = "a,vers=1.0" }), "invalid_share"},
		"dotdot share":     {smb(func(s *Spec) { s.Share = "a/../b" }), "invalid_share"},
		"option in host":   {smb(func(s *Spec) { s.Host = "nas,vers=1.0" }), "invalid_host"},
		"loopback":         {smb(func(s *Spec) { s.Host = "127.0.0.1" }), "invalid_host"},
		"ipv6":             {smb(func(s *Spec) { s.Host = "fd00::5" }), "ipv6_literal"},
		"newline password": {smb(func(s *Spec) { s.Password = "a\nusername=root" }), "invalid_password"},
		"bad access":       {smb(func(s *Spec) { s.Access = "rwx" }), "invalid_access"},
		"protocol":         {smb(func(s *Spec) { s.Protocol = "afp" }), "invalid_protocol"},
		"nfs root":         {nfs("/"), "system_share"},
		"nfs etc":          {nfs("/etc/ssl"), "system_share"},
		"nfs proc":         {nfs("/proc"), "system_share"},
		"nfs relative":     {nfs("volume1"), "system_share"},
		"nfs password":     {Spec{Protocol: NFS, Host: "nas", Share: "/volume1/x", Password: "p"}, "nfs_no_credentials"},
	} {
		if got := reason(tc.s.Validate()); got != tc.want {
			t.Errorf("%s: got %q, want %q", name, got, tc.want)
		}
	}
	for _, ok := range []Spec{smbSpec(), {Protocol: NFS, Host: "nas.lan", Share: "/volume1/photos", Access: "rw"}} {
		if err := ok.Validate(); err != nil {
			t.Errorf("%v refused: %v", ok, err)
		}
	}
}

func TestSpecNeverPrintsItsFields(t *testing.T) {
	s := smbSpec()
	var logs bytes.Buffer
	slog.New(slog.NewTextHandler(&logs, nil)).Info("x", "spec", s)
	for _, out := range []string{s.String(), s.GoString(), logs.String()} {
		for _, v := range []string{secret, "nas.example", "family", "alex"} {
			if strings.Contains(out, v) {
				t.Errorf("%q shows %q", out, v)
			}
		}
	}
}

func TestClassifyNamesTheReasonAndRedactHidesTheSecrets(t *testing.T) {
	for out, want := range map[string]string{
		"mount error(13): Permission denied":                "auth_failed",
		"mount error(2): No such file or directory":         "share_not_found",
		"mount error(95): Operation not supported":          "protocol_refused",
		"mount error(112): Host is down":                    "unreachable",
		"mount error(111): could not connect to 192.0.2.10": "unreachable",
		"mount.nfs: access denied by server":                "auth_failed",
		"something else":                                    "mount_failed",
	} {
		if got := reason(classify(out)); got != want {
			t.Errorf("%q: got %q, want %q", out, got, want)
		}
	}
	out := redact("mount error(13) for //nas.example/family user alex password="+secret, smbSpec())
	for _, v := range []string{secret, "nas.example", "family", "alex"} {
		if strings.Contains(out, v) {
			t.Errorf("redacted output %q still shows %q", out, v)
		}
	}
	if got := tail("  "+strings.Repeat("x", 20)+"end  ", 5); got != "…xxend" {
		t.Errorf("tail: %q", got)
	}
}

func TestMountedInReadsMountinfo(t *testing.T) {
	info := "36 35 98:0 / /data rw - btrfs /dev/x rw\n40 36 0:50 / /data/onemind/net/my\\040nas rw - cifs //n/s rw\n"
	for dir, want := range map[string]bool{"/data/onemind/net/my nas": true, "/data/onemind/net/my": false, "/data/": true} {
		if got, _ := MountedIn(strings.NewReader(info), dir); got != want {
			t.Errorf("%q: %v", dir, got)
		}
	}
}
