// SPDX-License-Identifier: Apache-2.0

package flatpak

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeFlatpak is a small stand-in for one installation with a local repository of three apps. It answers the
// commands the Manager sends and records them, so a test sees the exact argument lists.
type fakeFlatpak struct {
	catalog   string // remote-ls output (tab separated)
	installed map[string]bool
	updates   []string
	calls     [][]string
	failOn    string // a sub-command that exits non-zero
}

const catalog = "md.obsidian.Obsidian\tObsidian\tKnowledge base on local Markdown\t1.8.9\n" +
	"org.gimp.GIMP\tGIMP\tCreate images and edit photographs\t2.10\n" +
	"org.example.Notes\tNotes\tA notes app that mentions obsidian in its summary\t1.0\n"

func newFake() *fakeFlatpak { return &fakeFlatpak{catalog: catalog, installed: map[string]bool{}} }

func (f *fakeFlatpak) Run(_ context.Context, args ...string) ([]byte, error) {
	f.calls = append(f.calls, args)
	if len(args) == 0 || args[0] != "--installation="+Installation {
		return nil, errors.New("every call names the box's installation")
	}
	cmd, rest := args[1], args[2:]
	if cmd == f.failOn {
		return []byte("boom " + cmd), errors.New("exit status 1")
	}
	switch cmd {
	case "remote-add":
		return nil, nil
	case "remote-ls":
		if rest[1] == "--updates" {
			return []byte(strings.Join(f.updates, "\n")), nil
		}
		return []byte(f.catalog), nil
	case "list":
		var b strings.Builder
		for id := range f.installed {
			for _, l := range strings.Split(f.catalog, "\n") {
				if strings.HasPrefix(l, id+"\t") {
					b.WriteString(l[:strings.LastIndex(l, "\t")] + "\t" + l[strings.LastIndex(l, "\t")+1:] + "\n")
				}
			}
		}
		out := strings.NewReplacer("Knowledge base on local Markdown\t", "", "Create images and edit photographs\t", "").Replace(b.String())
		return []byte(out), nil
	case "install":
		f.installed[rest[len(rest)-1]] = true
	case "uninstall":
		delete(f.installed, rest[len(rest)-1])
	}
	return nil, nil
}

func box(t *testing.T) (*Manager, *fakeFlatpak) {
	f := newFake()
	dir := t.TempDir()
	return &Manager{Run: f, FilesDir: filepath.Join(dir, "apps"), SessionDir: filepath.Join(dir, "session"),
		Have: func(string) bool { return true }, Chown: func(string, int, int) error { return nil }}, f
}

func TestSearchFindsObsidianByNameFirstThenSummary(t *testing.T) {
	m, _ := box(t)
	hits, err := m.Search(context.Background(), "obsidian")
	if err != nil || len(hits) != 2 || hits[0].ID != "md.obsidian.Obsidian" || hits[1].ID != "org.example.Notes" {
		t.Fatalf("hits %+v err %v", hits, err)
	}
	if hits[0].Summary == "" || hits[0].Version != "1.8.9" || hits[0].Installed {
		t.Fatalf("details lost: %+v", hits[0])
	}
}

func TestSearchRefusesShortQueriesAndAMissingFlatpak(t *testing.T) {
	m, _ := box(t)
	if _, err := m.Search(context.Background(), "o"); err == nil {
		t.Fatal("a one-letter search must be refused")
	}
	m.Have = func(p string) bool { return p != "flatpak" }
	_, err := m.Search(context.Background(), "obsidian")
	if r, ok := IsRefusal(err); !ok || r.Reason != "flatpak_not_installed" {
		t.Fatalf("got %v", err)
	}
}

func TestInstallSandboxesTheAppToItsOwnFolder(t *testing.T) {
	m, f := box(t)
	if err := m.Install(context.Background(), "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	folder := m.Folder("md.obsidian.Obsidian")
	if st, err := os.Stat(folder); err != nil || !st.IsDir() {
		t.Fatalf("granted folder missing: %v", err)
	}
	var override []string
	for _, c := range f.calls {
		if c[1] == "override" {
			override = c
		}
	}
	for _, want := range []string{"--nofilesystem=host", "--nofilesystem=home", "--no-talk-name=org.freedesktop.Flatpak",
		"--filesystem=" + folder + ":rw", "md.obsidian.Obsidian"} {
		if !contains(override, want) {
			t.Errorf("override lacks %s: %v", want, override)
		}
	}
	for _, a := range override {
		if strings.HasPrefix(a, "--filesystem=") && a != "--filesystem="+folder+":rw" {
			t.Errorf("a second folder was granted: %s", a)
		}
	}
	apps, _ := m.Installed(context.Background())
	if len(apps) != 1 || apps[0].Folder != folder || !apps[0].Installed {
		t.Fatalf("installed %+v", apps)
	}
}

func TestAnAppWhoseSandboxFailsIsRemovedAgain(t *testing.T) {
	m, f := box(t)
	f.failOn = "override"
	err := m.Install(context.Background(), "md.obsidian.Obsidian")
	if err == nil || f.installed["md.obsidian.Obsidian"] {
		t.Fatalf("an app with its own permissions must not stay: err=%v installed=%v", err, f.installed)
	}
}

func TestOnlyApplicationIdsReachTheCommandLine(t *testing.T) {
	m, f := box(t)
	for _, bad := range []string{"", "obsidian", "--user", "md.obsidian.Obsidian --system", "../x.y.z", "a.b"} {
		if err := m.Install(context.Background(), bad); err == nil {
			t.Errorf("%q accepted", bad)
		}
	}
	if len(f.calls) != 0 {
		t.Fatalf("flatpak ran for a bad id: %v", f.calls)
	}
}

func TestUpdateAndRemoveNeedAnInstalledAppAndRemoveKeepsTheFolder(t *testing.T) {
	m, f := box(t)
	ctx := context.Background()
	for _, err := range []error{m.Update(ctx, "md.obsidian.Obsidian"), m.Remove(ctx, "md.obsidian.Obsidian")} {
		if r, ok := IsRefusal(err); !ok || r.Reason != "not_installed" {
			t.Fatalf("got %v", err)
		}
	}
	if err := m.Install(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	f.updates = []string{"md.obsidian.Obsidian"}
	if apps, _ := m.Installed(ctx); !apps[0].UpdateAvailable {
		t.Fatal("update not reported")
	}
	if err := m.Update(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	note := filepath.Join(m.Folder("md.obsidian.Obsidian"), "note.md")
	if err := os.WriteFile(note, []byte("mine"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := m.Remove(ctx, "md.obsidian.Obsidian"); err != nil || f.installed["md.obsidian.Obsidian"] {
		t.Fatalf("remove: %v", err)
	}
	if _, err := os.Stat(note); err != nil {
		t.Fatal("removing the app deleted the owner's files")
	}
}

func TestLaunchWritesTheSessionFileOnlyForInstalledApps(t *testing.T) {
	m, _ := box(t)
	ctx := context.Background()
	if r, ok := IsRefusal(m.Launch(ctx, "md.obsidian.Obsidian")); !ok || r.Reason != "not_installed" {
		t.Fatal("launch of an app that is not installed must be refused")
	}
	if err := m.Install(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	if err := m.Launch(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(filepath.Join(m.SessionDir, "launch"))
	if string(b) != "md.obsidian.Obsidian\n" {
		t.Fatalf("launch file %q", b)
	}
}

func contains(l []string, s string) bool {
	for _, x := range l {
		if x == s {
			return true
		}
	}
	return false
}
