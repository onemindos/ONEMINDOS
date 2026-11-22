// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"encoding/json"
	"os"
	"slices"
	"testing"
	"time"
)

// A Kiwix-like app: a small library list and a large, re-downloadable ZIM.
var (
	libraryVol = VolumeRef{Namespace: "app-library", Claim: "data", Volume: "pvc-3333"}
	libDir     = "storage/pvc-3333_app-library_data/"
)

func libraryApp(content string) AppSpec {
	s := AppSpec{ID: "library", Volumes: []VolumeRef{libraryVol}, Content: content}
	if content == ContentExcluded {
		s.Excludes = []string{"*.zim"} // what the gateway sends while the tier is off
	}
	return s
}

func libraryRun(t *testing.T, m *managedFixture, content string) string {
	t.Helper()
	r := m.ok(t, KindRun, map[string]any{"reason": ReasonManual, "apps": []AppSpec{libraryApp(content)}, "units": []string{"app:library"}})
	b, _ := json.Marshal(r.Result)
	var run Run
	_ = json.Unmarshal(b, &run)
	if run.State != StateSucceeded || len(run.Units) != 1 {
		t.Fatalf("run: %+v", run)
	}
	return run.Units[0].SnapshotID
}

func (m *managedFixture) tick() {
	m.clock = m.clock.Add(time.Hour)
	m.signer.now = m.clock
}

func TestPatternMatchReadsRelativePatternsLikeRestic(t *testing.T) {
	cases := []struct {
		pats []string
		p    string
		want bool
	}{
		{[]string{"*.zim"}, "zims/wiki.zim", true},
		{[]string{"*.zim"}, "library.xml", false},
		{[]string{"maps/*.pmtiles"}, "maps/region.pmtiles", true},
		{[]string{"maps/*.pmtiles"}, "other/region.pmtiles", false},
		{[]string{"models/"}, "models/blobs/sha256-ab", true}, // a matched folder takes its contents
		{[]string{"models/"}, "models.json", false},
	}
	for _, c := range cases {
		if got := patternMatch(c.pats, c.p); got != c.want {
			t.Errorf("patternMatch(%v, %q) = %v, want %v", c.pats, c.p, got, c.want)
		}
	}
	for _, bad := range []string{"", "/abs", "../up", "a/**/b", "[x"} {
		if validContentPattern(bad) == nil {
			t.Errorf("pattern %q accepted", bad)
		}
	}
}

func TestContentSizeCountsOnlyMatchedRegularFiles(t *testing.T) {
	m := newManagedFixture(t)
	m.write(libDir+"library.xml", "<library/>")
	m.write(libDir+"zims/wiki.zim", "ZIM-0123456789")
	m.write(libDir+"zims/med.zim", "ZIM-1")
	if err := os.Symlink(m.path(libDir+"zims/wiki.zim"), m.path(libDir+"link.zim")); err != nil {
		t.Fatal(err)
	}
	r := m.ok(t, KindContentSize, map[string]any{"apps": []ContentSizeApp{
		{ID: "library", Volumes: []VolumeRef{libraryVol, {Namespace: "app-library", Claim: "gone", Volume: "pvc-9999"}}, Patterns: []string{"*.zim"}},
	}})
	b, _ := json.Marshal(r.Result)
	var out []ContentSize
	_ = json.Unmarshal(b, &out)
	if len(out) != 1 || out[0].Bytes != int64(len("ZIM-0123456789")+len("ZIM-1")) || out[0].Files != 2 {
		t.Fatalf("size: %+v (a symlink must not be followed or counted)", out)
	}
	if !slices.Equal(out[0].Missing, []string{"app-library/gone"}) {
		t.Fatalf("missing volume not reported: %+v", out[0])
	}
	if code, _, _ := m.do(t, KindContentSize, map[string]any{"apps": []ContentSizeApp{{ID: "library", Volumes: []VolumeRef{libraryVol}, Patterns: []string{"../etc"}}}}); code == 200 {
		t.Fatal("a pattern leaving the volume must be refused")
	}
}

// BAK-03 done-when: a restore with and without the content tier.
func TestAppRestoreWithAndWithoutTheContentTier(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	m.write(libDir+"library.xml", "<library v1/>")
	m.write(libDir+"zims/wiki.zim", "ZIM-v1")

	// Tier off: the snapshot holds the library list, not the ZIM, and says so.
	without := libraryRun(t, m, ContentExcluded)
	// Tier on: the next snapshot holds both.
	m.tick()
	with := libraryRun(t, m, ContentIncluded)
	tags := map[string]string{}
	for _, s := range m.repo.snaps {
		for _, tg := range s.Tags {
			if len(tg) > 8 && tg[:8] == "content=" {
				tags[s.ID] = tg[8:]
			}
		}
	}
	if tags[without] != ContentExcluded || tags[with] != ContentIncluded {
		t.Fatalf("content tags: %v", tags)
	}

	// The library list breaks and the ZIM is lost.
	m.tick()
	m.write(libDir+"library.xml", "BROKEN")
	_ = os.Remove(m.path(libDir + "zims/wiki.zim"))

	// Restore with the content tier: the list and the offline library come back.
	m.ok(t, KindRestore, map[string]any{"scope": "app", "app_id": "library", "snapshot_id": with, "stamp": "20261112T120000Z"})
	if m.read(libDir+"library.xml") != "<library v1/>" || m.read(libDir+"zims/wiki.zim") != "ZIM-v1" {
		t.Fatal("restore with the content tier must bring the content back")
	}
	m.ok(t, KindRestoreFinish, map[string]any{"app_id": "library", "stamp": "20261112T120000Z", "commit": true})

	// Restore without it: the list comes back; the content is not in that
	// snapshot, so the app downloads it again.
	m.write(libDir+"library.xml", "BROKEN")
	m.ok(t, KindRestore, map[string]any{"scope": "app", "app_id": "library", "snapshot_id": without, "stamp": "20261112T121000Z"})
	if m.read(libDir+"library.xml") != "<library v1/>" {
		t.Fatal("restore without the content tier must still bring the app's own data back")
	}
	if _, err := os.Stat(m.path(libDir + "zims/wiki.zim")); !os.IsNotExist(err) {
		t.Fatalf("a snapshot without the content tier must not hold the content: %v", err)
	}
	m.ok(t, KindRestoreFinish, map[string]any{"app_id": "library", "stamp": "20261112T121000Z", "commit": true})
}

func TestGatewayContentValueIsChecked(t *testing.T) {
	m := newManagedFixture(t)
	if code, r, _ := m.do(t, KindRun, map[string]any{"reason": ReasonManual, "apps": []AppSpec{libraryApp("some")}, "units": []string{"app:library"}}); code == 200 && r.State == StateSucceeded {
		t.Fatal("content must be included or excluded")
	}
}
