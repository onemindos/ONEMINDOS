// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// The box's name, kept on the data partition (P-05). The root is read-only and /etc/hostname is in it, so
// systemd-hostnamed could not save a name there; the name the owner approved lives here instead and
// `onemindd host apply-hostname` puts it back at every boot (before avahi starts, so <name>.local follows).
const (
	DefaultHostnameFile = "/data/onemind/etc/hostname"
	// /etc/hosts is a file bind mount of this one on the image (os/rootfs/layers/base/etc/fstab).
	DefaultHostsSource = "/data/state/etc-hosts"
	// k3s names its node after the host name. A rename would make the next boot a new node, and the local-path
	// volumes belong to the old one, so the first rename pins the old name here (k3s.service reads it as an
	// EnvironmentFile; os/gate/onemind-k3s-check reads it too).
	DefaultK3sEnv = "/data/onemind/etc/k3s.env"
	// The old names the box keeps answering to over mDNS (one per line), published by onemind-mdns-aliases.service.
	DefaultAliasesFile = "/data/onemind/etc/mdns-aliases"
)

var nodeNameRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$`)

// Runner runs one command; tests replace it.
type Runner func(ctx context.Context, name string, args ...string) ([]byte, error)

func execRunner(ctx context.Context, name string, args ...string) ([]byte, error) {
	return exec.CommandContext(ctx, name, args...).CombinedOutput()
}

// SystemHostname renames the box: it writes the name where the next boot reads it, starts
// onemind-hostname.service to switch the running name, rewrites the 127.0.1.1 line of the hosts file
// and restarts avahi so <name>.local answers at once. onemind-host.service has ProtectHostname=yes, so it
// cannot call sethostname itself: the helper unit does it for the whole box.
type SystemHostname struct {
	File    string // DefaultHostnameFile
	K3sEnv  string // DefaultK3sEnv
	Aliases string // DefaultAliasesFile
	Hosts   string // the hosts file to rewrite in place (default DefaultHostsSource, the file /etc/hosts is a bind mount of)
	Run     Runner
	NoMDNS  bool // tests: do not restart avahi
}

func (h SystemHostname) run() Runner {
	if h.Run != nil {
		return h.Run
	}
	return execRunner
}

// Set implements Hostnamer.
func (h SystemHostname) Set(ctx context.Context, name string) error {
	if !hostnameRe.MatchString(name) {
		return fmt.Errorf("%q is not a DNS label", name)
	}
	file := h.File
	if file == "" {
		file = DefaultHostnameFile
	}
	if err := h.pinNodeName(file); err != nil {
		return fmt.Errorf("keeping the Kubernetes node's name: %w", err)
	}
	aliasFile := h.Aliases
	if aliasFile == "" {
		aliasFile = DefaultAliasesFile
	}
	prevName, hadName := readOptional(file)
	prevAliases, hadAliases := readOptional(aliasFile)
	// The names the box answered to until now keep answering (onemind.local, the old <name>.local), because
	// passkeys, join codes, the certificate and the apps all use them. They are published as mDNS aliases.
	current, _ := CurrentHostname(file)
	aliases := MergeAliases(strings.Split(string(prevAliases), "\n"), current, name)
	if err := WriteFileAtomic(file, []byte(name+"\n"), 0o644); err != nil {
		return fmt.Errorf("saving the name on the data partition: %w", err)
	}
	// Any failure from here on puts the saved name (and the alias list) back, so the next boot does not apply a
	// name the owner was told failed. The running name is switched back too when it was already changed.
	applied := false
	rollback := func() {
		restoreOptional(file, prevName, hadName)
		restoreOptional(aliasFile, prevAliases, hadAliases)
		if applied && hadName {
			rctx, rcancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer rcancel()
			_, _ = h.run()(rctx, "systemctl", "start", "onemind-hostname.service")
		}
	}
	if err := WriteFileAtomic(aliasFile, []byte(strings.Join(aliases, "\n")+"\n"), 0o644); err != nil {
		rollback()
		return fmt.Errorf("saving the old names: %w", err)
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	// onemind-hostname.service reads the saved name and sets the kernel host name (this unit's own sandbox has a
	// private host name, so it cannot; hostnamed would also keep the static name from /etc/hostname).
	if out, err := h.run()(ctx, "systemctl", "start", "onemind-hostname.service"); err != nil {
		rollback()
		return fmt.Errorf("applying the name: %w: %s", err, strings.TrimSpace(string(out)))
	}
	applied = true
	// /etc/hosts is a bind mount of the data partition's file and this unit's root is read-only (ProtectSystem=strict),
	// so the source file is rewritten: same inode, so /etc/hosts shows it at once. No such file (a board without the
	// bind): nothing to fix, the name still works without the 127.0.1.1 line.
	hosts := h.Hosts
	if hosts == "" {
		hosts = DefaultHostsSource
		if _, err := os.Stat(hosts); err != nil {
			hosts = ""
		}
	}
	if hosts != "" {
		prevHosts, hadHosts := readOptional(hosts)
		if err := RewriteLoopbackName(hosts, name); err != nil {
			restoreOptional(hosts, prevHosts, hadHosts)
			rollback()
			return fmt.Errorf("updating the hosts file: %w", err)
		}
	}
	// From here the box is renamed: the kernel name, the saved name and the hosts file agree. mDNS trouble is only
	// a warning, because failing the op now would tell the owner the rename failed while the box has the new name.
	if !h.NoMDNS {
		// avahi reads the host name when it starts. try-restart: a box without avahi is not an error.
		if out, err := h.run()(ctx, "systemctl", "try-restart", "avahi-daemon.service"); err != nil {
			log.Printf("host: renamed to %s, but avahi did not restart (%v: %s); other devices see the new name after the next boot",
				name, err, strings.TrimSpace(string(out)))
		}
		// The alias publisher re-reads its list: restart (not try-restart) so a first rename starts it.
		if out, err := h.run()(ctx, "systemctl", "restart", "onemind-mdns-aliases.service"); err != nil {
			log.Printf("host: renamed to %s, but the old names are not published (%v: %s)", name, err, strings.TrimSpace(string(out)))
		}
	}
	return nil
}

// readOptional returns a file's content and whether it existed.
func readOptional(path string) ([]byte, bool) {
	b, err := os.ReadFile(path)
	return b, err == nil
}

// restoreOptional puts a file back as it was: the old content, or no file when there was none.
func restoreOptional(path string, content []byte, existed bool) {
	if existed {
		if err := os.WriteFile(path, content, 0o644); err != nil {
			log.Printf("host: could not restore %s: %v", path, err)
		}
		return
	}
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		log.Printf("host: could not remove %s: %v", path, err)
	}
}

// pinNodeName writes K3S_NODE_NAME=<the name the box has now> unless a pin already exists, before the name changes.
func (h SystemHostname) pinNodeName(file string) error {
	path := h.K3sEnv
	if path == "" {
		path = DefaultK3sEnv
	}
	if _, err := os.Stat(path); err == nil {
		return nil // pinned by an earlier rename: the node keeps that name
	}
	old, err := CurrentHostname(file)
	if err != nil {
		return err
	}
	old = strings.ToLower(old)
	if !nodeNameRe.MatchString(old) {
		return fmt.Errorf("the current host name %q is not a Kubernetes node name", old)
	}
	return WriteFileAtomic(path, []byte("K3S_NODE_NAME="+old+"\n"), 0o644)
}

// Reload implements Hostnamer: the gateway reads the box name when it starts (its certificate lists <name>.local, and
// the join QR names it), so it is restarted once the answer is journaled. try-restart: no gateway, no error.
func (h SystemHostname) Reload(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	if out, err := h.run()(ctx, "systemctl", "try-restart", "onemind-gateway.service"); err != nil {
		return fmt.Errorf("systemctl try-restart onemind-gateway: %w: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// ApplyHostname is `onemindd host apply-hostname`, run at boot by onemind-data-layout.service (a drop-in)
// before avahi: it sets the running name from the saved file and fixes /etc/hosts's source. No file, or a
// file that is not a DNS label: nothing changes (the image's own name stays).
func ApplyHostname(file, hostsSource string, set func(string) error) (string, error) {
	if file == "" {
		file = DefaultHostnameFile
	}
	if hostsSource == "" {
		hostsSource = DefaultHostsSource
	}
	b, err := os.ReadFile(file)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}
	name := strings.TrimSpace(string(b))
	if !hostnameRe.MatchString(name) {
		return "", fmt.Errorf("%s does not hold a DNS label; the image's name is kept", file)
	}
	if err := set(name); err != nil {
		return "", err
	}
	if _, err := os.Stat(hostsSource); err == nil {
		if err := RewriteLoopbackName(hostsSource, name); err != nil {
			return name, err
		}
	}
	return name, nil
}

// CurrentHostname is the name the box has now, as the owner set it. onemind-host.service sits in its own
// UTS namespace (ProtectHostname=yes), so os.Hostname() there still shows the name it started with.
func CurrentHostname(file string) (string, error) {
	if file == "" {
		file = DefaultHostnameFile
	}
	if b, err := os.ReadFile(file); err == nil {
		if n := strings.TrimSpace(string(b)); hostnameRe.MatchString(n) {
			return n, nil
		}
	}
	return os.Hostname()
}

// RewriteLoopbackName points the 127.0.1.1 line of an /etc/hosts file at name (added if missing). The file
// is rewritten in place: on the image it is a file bind mount, which a rename cannot replace.
func RewriteLoopbackName(path, name string) error {
	old, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	var out []string
	done := false
	for _, line := range strings.Split(strings.TrimRight(string(old), "\n"), "\n") {
		f := strings.Fields(line)
		if len(f) > 0 && f[0] == "127.0.1.1" {
			if !done {
				out = append(out, "127.0.1.1\t"+name)
				done = true
			}
			continue
		}
		if line != "" || len(out) > 0 {
			out = append(out, line)
		}
	}
	if !done {
		out = append(out, "127.0.1.1\t"+name)
	}
	next := strings.Join(out, "\n") + "\n"
	if next == string(old) {
		return nil
	}
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_TRUNC|os.O_CREATE, 0o644)
	if err != nil {
		return err
	}
	if _, err := f.WriteString(next); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

// WriteFileAtomic writes data to path through a temporary file and a rename, creating the directory.
func WriteFileAtomic(path string, data []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".tmp-"+filepath.Base(path))
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(mode); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), path)
}
