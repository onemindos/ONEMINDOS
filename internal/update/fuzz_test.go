// SPDX-License-Identifier: Apache-2.0

package update

// Native Go fuzz targets for TUF metadata handling (docs/testing/PROPERTY-AND-FUZZ.md).
// `go test ./...` runs each target on its seed corpus; `go test -fuzz=<Target> -fuzztime=30s
// ./internal/update` explores.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/update/tuftest"
)

// FuzzCompareVersions: the release order the updater uses to refuse downgrades is a total
// preorder. For versions that parse: reflexive, antisymmetric (cmp(a,b) = -cmp(b,a)), transitive
// over three versions, and a leading "v" or "+build" suffix never changes the order.
func FuzzCompareVersions(f *testing.F) {
	for _, s := range [][3]string{
		{"0.1.0", "0.1.1", "0.2.0"}, {"0.1.0-dev", "0.1.0", "0.1.0.0"}, {"1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-beta"},
		{"1.0.0-1", "1.0.0-01", "1.0.0-a"}, {"0.1.20261112025704", "v0.1.20261112025705", "0.1.20261112025704+b7"},
		{"1.0.0-99999999999999999999", "1.0.0-9", "1.0.0-z"}, {"1", "1.0", "1.0.0-0"}, {"", "x", "1..0"},
	} {
		f.Add(s[0], s[1], s[2])
	}
	f.Fuzz(func(t *testing.T, a, b, c string) {
		ab, errA := compareVersions(a, b)
		ba, errB := compareVersions(b, a)
		if (errA == nil) != (errB == nil) {
			t.Fatalf("compare(%q,%q) err=%v but compare(%q,%q) err=%v", a, b, errA, b, a, errB)
		}
		if errA != nil {
			return
		}
		if ab != -ba {
			t.Fatalf("antisymmetry: cmp(%q,%q)=%d cmp(%q,%q)=%d", a, b, ab, b, a, ba)
		}
		if aa, _ := compareVersions(a, a); aa != 0 {
			t.Fatalf("reflexivity: cmp(%q,%q)=%d", a, a, aa)
		}
		if !strings.HasPrefix(a, "v") && !strings.Contains(a, "+") {
			if va, err := compareVersions("v"+a+"+build.7", b); err != nil || va != ab {
				t.Fatalf("prefix v / +build changed the order of %q vs %q: %d vs %d (%v)", a, b, va, ab, err)
			}
		}
		bc, errC := compareVersions(b, c)
		if errC != nil {
			return
		}
		ac, _ := compareVersions(a, c)
		if ab <= 0 && bc <= 0 && ac > 0 {
			t.Fatalf("transitivity: %q <= %q <= %q but %q > %q", a, b, c, a, c)
		}
		if ab >= 0 && bc >= 0 && ac < 0 {
			t.Fatalf("transitivity: %q >= %q >= %q but %q < %q", a, b, c, a, c)
		}
	})
}

// eligible restates CHANNEL.md's offer rule independently of applicable(): a RAUC bundle for
// this board and compatible, at the canonical path, newer than the running version (no
// downgrade), not below its min_from_version, flagged security on the security channel, and
// not refused by the health gate.
func eligible(c *Config, t Target, box Box, bad BadReleases) bool {
	m := t.Meta
	newer, err := compareVersions(m.Version, box.Version)
	if err != nil || newer != 1 {
		return false
	}
	if m.MinFromVersion != "" {
		if mf, err := compareVersions(m.MinFromVersion, box.Version); err != nil || mf == 1 {
			return false
		}
	}
	return strings.HasSuffix(t.Path, ".raucb") && m.Board == box.Board && m.Compatible == box.Compatible &&
		t.Path == fmt.Sprintf("%s/%s/onemind-%s-%s.raucb", m.Board, m.Version, m.Board, m.Version) &&
		(c.Channel != ChannelSecurity || m.Security) && bad.Excluded(m.Version) == ""
}

// FuzzSelect: whatever signed custom metadata a channel carries, Select offers only an eligible
// target (never a downgrade, another board, a non-canonical path, a gate-refused version, or a
// non-security update on the security channel), offers the newest eligible one, explains every
// target it skips, and the chosen bundle downloads into the download directory.
func FuzzSelect(f *testing.F) {
	f.Add([]byte(`{"board":"vm","version":"0.2.0","compatible":"onemind-vm","min_from_version":"0.1.0","security":true}`),
		"vm/0.2.0/onemind-vm-0.2.0.raucb", []byte(`{"board":"vm","version":"0.1.5","compatible":"onemind-vm","security":true}`),
		"0.1.0", true, "0.3.0", uint8(0))
	f.Add([]byte(`{"board":"vm","version":"0.0.9","compatible":"onemind-vm","security":true}`),
		"vm/0.0.9/onemind-vm-0.0.9.raucb", []byte(`{"board":"rpi5","version":"9.0.0","compatible":"onemind-vm"}`),
		"0.1.0", false, "", uint8(1))
	f.Add([]byte(`{"board":"vm","version":"0.2.0-a/b","compatible":"onemind-vm","security":true}`),
		"vm/0.2.0-a/b/onemind-vm-0.2.0-a/b.raucb", []byte(`{"board":"vm","version":"v0.2.0","compatible":"onemind-vm","security":true}`),
		"0.1.0", true, "0.2.0", uint8(2))
	f.Fuzz(func(t *testing.T, meta1 []byte, path1 string, meta2 []byte, boxVersion string, security bool, badVersion string, envBad uint8) {
		var m1, m2 TargetMeta
		if json.Unmarshal(meta1, &m1) != nil || json.Unmarshal(meta2, &m2) != nil {
			return // fetchIndex refuses the whole channel then
		}
		canonical := func(m TargetMeta) string {
			return fmt.Sprintf("%s/%s/onemind-%s-%s.raucb", m.Board, m.Version, m.Board, m.Version)
		}
		idx := &Index{Targets: []Target{
			{Path: path1, Meta: m1},
			{Path: canonical(m2), Meta: m2},
			{Path: "vm/0.1.1/onemind-vm-0.1.1.raucb", Meta: TargetMeta{Board: "vm", Version: "0.1.1", Compatible: "onemind-vm", Security: true}},
		}}
		c := &Config{Channel: ChannelStable}
		if security {
			c.Channel = ChannelSecurity
		}
		box := Box{Board: "vm", Compatible: "onemind-vm", Version: boxVersion}
		bad := BadReleases{imageBad: map[string]bool{}, envBad: map[string]int{}}
		if envBad%3 == 0 {
			bad.imageBad[badVersion] = true
		} else {
			bad.envBad[badVersion] = int(envBad)
		}

		got, skips := Select(c, idx, box, bad)
		want := 0
		for _, tg := range idx.Targets {
			if eligible(c, tg, box, bad) {
				want++
				if got == nil {
					t.Fatalf("nothing offered, but %q is eligible", tg.Path)
				}
				if cmp, _ := compareVersions(tg.Meta.Version, got.Meta.Version); cmp > 0 {
					t.Fatalf("offered %s, but %s is newer and eligible", got.Meta.Version, tg.Meta.Version)
				}
			}
		}
		if len(skips) != len(idx.Targets)-want {
			t.Fatalf("%d targets, %d eligible, %d skipped: %+v", len(idx.Targets), want, len(skips), skips)
		}
		for _, s := range skips {
			if s.Why == "" {
				t.Fatalf("skip without a reason: %+v", s)
			}
		}
		if got == nil {
			return
		}
		if !eligible(c, *got, box, bad) {
			t.Fatalf("offered an ineligible target %+v for box %+v (channel %s)", got, box, c.Channel)
		}
		dir := filepath.Join(t.TempDir(), "rauc")
		if filepath.Dir(filepath.Join(dir, path.Base(got.Path))) != dir {
			t.Fatalf("bundle %q would download outside %s", got.Path, dir)
		}
	})
}

// --- tampered channel metadata ------------------------------------------------------------------

var tufNow = time.Date(2026, 11, 12, 9, 0, 0, 0, time.UTC)

// signedChannel is one published channel: its files, the image's root, and the index a client
// gets from the untouched files.
type signedChannel struct {
	files   map[string][]byte
	rootDir string
	genuine *Index
}

// tufFiles are the files a client fetches (root rotation probe, timestamp, snapshot, targets,
// and their versioned names under consistent_snapshot).
var tufFiles = []string{"timestamp.json", "snapshot.json", "targets.json", "2.root.json", "1.snapshot.json", "1.targets.json"}

func serve(files map[string][]byte) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, ok := files[strings.TrimPrefix(r.URL.Path, "/")]
		if !ok {
			http.NotFound(w, r)
			return
		}
		_, _ = w.Write(b)
	}))
}

func buildChannel(dir string, consistent bool) (*signedChannel, error) {
	repo, err := tuftest.New(tufNow)
	if err != nil {
		return nil, err
	}
	repo.ConsistentSnapshot = consistent
	for _, v := range []string{"0.1.1", "0.2.0"} {
		repo.AddTarget(tuftest.Meta{Board: "vm", Version: v, Compatible: "onemind-vm", Security: true}, []byte("bundle "+v))
	}
	pub := filepath.Join(dir, "pub")
	if err := repo.Publish(pub, 0); err != nil {
		return nil, err
	}
	ch := &signedChannel{files: map[string][]byte{}, rootDir: filepath.Join(dir, "roots")}
	entries, err := os.ReadDir(pub)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".json") {
			if ch.files[e.Name()], err = os.ReadFile(filepath.Join(pub, e.Name())); err != nil {
				return nil, err
			}
		}
	}
	if err := os.MkdirAll(filepath.Join(ch.rootDir, ChannelSecurity), 0o755); err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(ch.rootDir, ChannelSecurity, "root.json"), ch.files["1.root.json"], 0o644); err != nil {
		return nil, err
	}
	srv := serve(ch.files)
	defer srv.Close()
	state, err := os.MkdirTemp(dir, "state")
	if err != nil {
		return nil, err
	}
	c := &Config{Channel: ChannelSecurity, URL: srv.URL, TUFRootDir: ch.rootDir, StateDir: state}
	if ch.genuine, err = fetchIndex(c, srv.Client(), tufNow.Add(time.Hour)); err != nil {
		return nil, fmt.Errorf("untouched channel does not verify: %w", err)
	}
	if len(ch.genuine.Targets) != 2 {
		return nil, fmt.Errorf("untouched channel lists %d targets", len(ch.genuine.Targets))
	}
	return ch, nil
}

// mutate applies one edit to b: 0 overwrite at off, 1 insert at off, 2 delete len(p) bytes at
// off, 3 replace the whole file (an empty p removes it: the server answers 404).
func mutate(b []byte, mode uint8, off uint16, p []byte) ([]byte, bool) {
	if mode%4 == 3 {
		return p, len(p) > 0
	}
	if len(b) == 0 {
		return append([]byte(nil), p...), true
	}
	i := int(off) % (len(b) + 1)
	switch mode % 4 {
	case 0:
		out := append([]byte(nil), b...)
		copy(out[min(i, len(out)):], p)
		return out, true
	case 1:
		return append(append(append([]byte(nil), b[:i]...), p...), b[i:]...), true
	default:
		end := min(i+len(p), len(b))
		return append(append([]byte(nil), b[:i]...), b[end:]...), true
	}
}

// FuzzTUFMetadataTampering: an attacker who controls the channel's server (or the network) edits
// one metadata file the box fetches: overwrites, inserts or deletes bytes, replaces it, or makes
// it disappear. The TUF client in fetchIndex either refuses the channel, or ends with exactly the
// index the publisher signed: no edit can add, drop or change a target, a hash, a length, the
// custom metadata the updater acts on, or the expiry. Rollback and freeze protection beyond one
// fetch are covered by TestReplayedOlderMetadataRefused and TestExpiredTimestampRefused.
func FuzzTUFMetadataTampering(f *testing.F) {
	for i := range tufFiles {
		f.Add(uint8(i), uint8(0), uint16(40), []byte(`9`), false)
		f.Add(uint8(i), uint8(1), uint16(1), []byte(` `), true)
		f.Add(uint8(i), uint8(2), uint16(100), []byte(`xx`), false)
		f.Add(uint8(i), uint8(3), uint16(0), []byte{}, true)
	}
	f.Add(uint8(0), uint8(0), uint16(0), []byte(`{"signed":{"_type":"timestamp","version":99}}`), false)
	f.Add(uint8(2), uint8(1), uint16(12), []byte(`"version":7,`), false) // duplicate key ahead of the real one
	// Each fuzz worker signs its own channels (fresh keys), so inputs describe edits of the signed
	// files rather than whole files, and mean the same thing in every worker.
	var chans [2]*signedChannel // consistent_snapshot false, true
	dir := f.TempDir()
	for i, cs := range []bool{false, true} {
		ch, err := buildChannel(filepath.Join(dir, fmt.Sprint(i)), cs)
		if err != nil {
			f.Fatal(err)
		}
		chans[i] = ch
	}
	f.Fuzz(func(t *testing.T, which, mode uint8, off uint16, p []byte, consistent bool) {
		ch := chans[0]
		if consistent {
			ch = chans[1]
		}
		name := tufFiles[int(which)%len(tufFiles)]
		idx, err := tamperedFetch(t, ch, name, mode, off, p)
		if err == nil && !sameIndex(idx, ch.genuine) {
			t.Fatalf("edited %s (mode %d at %d, %q) was accepted with different content:\n%+v\nwant\n%+v",
				name, mode%4, off, p, idx, ch.genuine)
		}
	})
}

// tamperedFetch serves ch with one file edited and runs the box's TUF client against it.
func tamperedFetch(t *testing.T, ch *signedChannel, name string, mode uint8, off uint16, p []byte) (*Index, error) {
	files := make(map[string][]byte, len(ch.files))
	for k, v := range ch.files {
		files[k] = v
	}
	if edited, keep := mutate(files[name], mode, off, p); keep {
		files[name] = edited
	} else {
		delete(files, name)
	}
	srv := serve(files)
	defer srv.Close()
	c := &Config{Channel: ChannelSecurity, URL: srv.URL, TUFRootDir: ch.rootDir, StateDir: t.TempDir()}
	return fetchIndex(c, srv.Client(), tufNow.Add(time.Hour))
}

func sameIndex(a, b *Index) bool {
	return reflect.DeepEqual(a.Targets, b.Targets) && a.ConsistentSnapshot == b.ConsistentSnapshot &&
		a.TargetsExpires.Equal(b.TargetsExpires)
}

// The tampering target is only meaningful if its harness accepts what it should: an untouched
// channel and a whitespace-only edit verify, a one-byte change to signed content does not.
func TestTUFTamperingHarness(t *testing.T) {
	for _, consistent := range []bool{false, true} {
		ch, err := buildChannel(t.TempDir(), consistent)
		if err != nil {
			t.Fatal(err)
		}
		snap, targets := "snapshot.json", "targets.json"
		if consistent {
			snap, targets = "1.snapshot.json", "1.targets.json"
		}
		for _, name := range []string{"timestamp.json", snap, targets} {
			if idx, err := tamperedFetch(t, ch, name, 1, 0, nil); err != nil || !sameIndex(idx, ch.genuine) {
				t.Fatalf("untouched %s: %v", name, err)
			}
			if idx, err := tamperedFetch(t, ch, name, 1, 1, []byte(" \n ")); err != nil || !sameIndex(idx, ch.genuine) {
				t.Fatalf("whitespace in %s: %v", name, err)
			}
			at := bytes.Index(ch.files[name], []byte(`"version":`)) + len(`"version":`)
			if _, err := tamperedFetch(t, ch, name, 0, uint16(at), []byte("7")); err == nil {
				t.Fatalf("a changed version in %s verified", name)
			}
		}
	}
}
