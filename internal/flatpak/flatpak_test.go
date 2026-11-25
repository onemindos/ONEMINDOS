// SPDX-License-Identifier: Apache-2.0

package flatpak

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// fakeFlatpak is a small stand-in for one installation with a local repository of three apps. It answers the
// commands the Manager sends and records them, so a test sees the exact argument lists.
type fakeFlatpak struct {
	catalog   string // remote-ls output (tab separated)
	installed map[string]bool
	updates   []string
	calls     [][]string
	failOn    string            // a sub-command that exits non-zero
	runtimes  map[string]string // app id -> its runtime ref
	prepared  [][2]string       // Prepare calls: app dir, granted folder
	prepErr   error
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
		if contains(rest, "--updates") {
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
		var lines []string
		for _, l := range strings.Split(strings.TrimSpace(out), "\n") {
			if l != "" {
				lines = append(lines, l+"\t"+f.runtimes[strings.SplitN(l, "\t", 2)[0]])
			}
		}
		return []byte(strings.Join(lines, "\n")), nil
	case "install":
		f.installed[rest[len(rest)-1]] = true
	case "uninstall":
		delete(f.installed, rest[len(rest)-1])
	}
	return nil, nil
}

// Prepare stands in for the unit that makes the folder: the Manager itself never touches /data.
func (f *fakeFlatpak) Prepare(_ context.Context, appDir, folder string) error {
	f.prepared = append(f.prepared, [2]string{appDir, folder})
	if f.prepErr != nil {
		return f.prepErr
	}
	return os.MkdirAll(folder, 0o755)
}

func box(t *testing.T) (*Manager, *fakeFlatpak) {
	f := newFake()
	dir := t.TempDir()
	return &Manager{Run: f, FilesDir: filepath.Join(dir, "apps"), SessionDir: filepath.Join(dir, "session"),
		Have: func(string) bool { return true }}, f
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

func TestTheFolderIsMadeByThePrepareUnitNotByTheManager(t *testing.T) {
	m, f := box(t)
	if err := m.Install(context.Background(), "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	want := [2]string{filepath.Join(m.FilesDir, "md.obsidian.Obsidian"), m.Folder("md.obsidian.Obsidian")}
	if len(f.prepared) != 1 || f.prepared[0] != want {
		t.Fatalf("prepare calls %v, want %v", f.prepared, want)
	}
	// The Manager runs inside the capability-less host service: it creates nothing under the apps folder itself.
	if _, err := os.Stat(filepath.Join(m.FilesDir)); err != nil {
		t.Fatalf("the fake made the folder, so this is only a guard: %v", err)
	}
	src, _ := os.ReadFile("flatpak.go")
	for _, banned := range []string{"os.Chown(", "os.Lchown(", "syscall.Chown(", "os.MkdirAll(m.FilesDir", "os.MkdirAll(folder"} {
		if strings.Contains(string(src), banned) {
			t.Errorf("flatpak.go calls %s in the host service, which has no CAP_CHOWN", banned)
		}
	}
}

func TestAFolderThatCannotBeMadeRemovesTheApp(t *testing.T) {
	m, f := box(t)
	f.prepErr = errors.New("boom")
	if err := m.Install(context.Background(), "md.obsidian.Obsidian"); err == nil || f.installed["md.obsidian.Obsidian"] {
		t.Fatalf("err=%v installed=%v", err, f.installed)
	}
}

func TestSandboxLimitsAnAppToItsOneFolder(t *testing.T) {
	args := SandboxArgs("/data/onemind/desktop-apps/a.b.C/files")
	idx := func(s string) int {
		for i, a := range args {
			if a == s {
				return i
			}
		}
		return -1
	}
	reset, grant := idx("--nofilesystem=host:reset"), idx("--filesystem=/data/onemind/desktop-apps/a.b.C/files:rw")
	if reset < 0 || grant < 0 || reset > grant {
		t.Fatalf("host:reset must come first and the folder grant after it: %v", args)
	}
	for _, want := range []string{"--nosocket=session-bus", "--nosocket=system-bus", "--nosocket=ssh-auth", "--nosocket=pcsc",
		"--nosocket=cups", "--nosocket=gpg-agent", "--nodevice=all", "--no-talk-name=org.freedesktop.Flatpak"} {
		if idx(want) < 0 {
			t.Errorf("missing %s", want)
		}
	}
	n := 0
	for _, a := range args {
		if strings.HasPrefix(a, "--filesystem=") {
			n++
		}
	}
	if n != 1 {
		t.Errorf("%d filesystem grants, want exactly one", n)
	}
}

func TestSystemdUnitsAreHardenedAndGivenOnlyWhatTheirWorkNeeds(t *testing.T) {
	r := SystemdRunner{Dir: "/data/onemind/flatpak", FilesDir: "/data/onemind/desktop-apps"}
	fp := strings.Join(r.flatpakArgs("update", "x.y.Z"), " ")
	for _, want := range []string{"ProtectKernelTunables=yes", "ProtectControlGroups=yes", "ProtectKernelModules=yes", "ProtectKernelLogs=yes",
		"RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK", "PrivateDevices=yes", "CapabilityBoundingSet=~CAP_SYS_MODULE",
		"CAP_SYS_PTRACE", "ReadWritePaths=/data/onemind/flatpak", "-- /usr/bin/flatpak update x.y.Z"} {
		if !strings.Contains(fp, want) {
			t.Errorf("flatpak unit lacks %q", want)
		}
	}
	pp := strings.Join(r.prepareArgs("/data/onemind/desktop-apps/x.y.Z", "/data/onemind/desktop-apps/x.y.Z/files"), " ")
	for _, want := range []string{"CapabilityBoundingSet=CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE", "PrivateNetwork=yes", "RestrictNamespaces=yes",
		"ReadWritePaths=/data/onemind/desktop-apps", "install -d -o 0 -g 0 -m 0755", "-o 1000 -g 1000 -m 0755", "[ -L"} {
		if !strings.Contains(pp, want) {
			t.Errorf("prepare unit lacks %q", want)
		}
	}
	if strings.Contains(pp, "/data/onemind/flatpak") {
		t.Error("the folder step must not be able to write the Flatpak installation")
	}
}

func TestUpdateAnswersAreCachedAndForgottenAfterAChange(t *testing.T) {
	m, f := box(t)
	now := time.Unix(1_000_000, 0)
	m.Now = func() time.Time { return now }
	ctx := context.Background()
	if err := m.Install(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	asks := func() int {
		n := 0
		for _, c := range f.calls {
			if c[1] == "remote-ls" && contains(c, "--updates") {
				n++
			}
		}
		return n
	}
	f.calls = nil
	for i := 0; i < 5; i++ {
		_, _ = m.Installed(ctx)
	}
	if asks() != 1 {
		t.Fatalf("remote asked %d times for 5 polls", asks())
	}
	now = now.Add(updateTTL + time.Second)
	_, _ = m.Installed(ctx)
	if asks() != 2 {
		t.Fatalf("cache never expires: %d", asks())
	}
	if err := m.Update(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	_, _ = m.Installed(ctx)
	if asks() != 3 {
		t.Fatalf("an update must forget the cache: %d", asks())
	}
}

func TestARuntimeOnlyUpdateShowsOnItsApps(t *testing.T) {
	m, f := box(t)
	ctx := context.Background()
	f.runtimes = map[string]string{"md.obsidian.Obsidian": "org.freedesktop.Platform/x86_64/24.08", "org.gimp.GIMP": "org.gnome.Platform/x86_64/47"}
	for _, id := range []string{"md.obsidian.Obsidian", "org.gimp.GIMP"} {
		if err := m.Install(ctx, id); err != nil {
			t.Fatal(err)
		}
	}
	f.updates = []string{"org.freedesktop.Platform"}
	apps, _ := m.Installed(ctx)
	got := map[string]bool{}
	for _, a := range apps {
		got[a.ID] = a.UpdateAvailable
	}
	if !got["md.obsidian.Obsidian"] || got["org.gimp.GIMP"] {
		t.Fatalf("runtime update not attributed to the right app: %v", got)
	}
}

func TestUnusedRuntimesAreRemovedAfterARemove(t *testing.T) {
	m, f := box(t)
	ctx := context.Background()
	if err := m.Install(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	if err := m.Remove(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	for _, c := range f.calls {
		if c[1] == "uninstall" && contains(c, "--unused") {
			return
		}
	}
	t.Fatal("uninstall --unused never ran")
}

func TestAFailedUpdateAskIsRememberedBrieflyAndGivesNoUpdates(t *testing.T) {
	m, f := box(t)
	now := time.Unix(2_000_000, 0)
	m.Now = func() time.Time { return now }
	ctx := context.Background()
	if err := m.Install(ctx, "md.obsidian.Obsidian"); err != nil {
		t.Fatal(err)
	}
	m.forgetUpdates()
	f.failOn = "remote-ls"
	f.calls = nil
	asks := func() int {
		n := 0
		for _, c := range f.calls {
			if c[1] == "remote-ls" {
				n++
			}
		}
		return n
	}
	for i := 0; i < 4; i++ {
		apps, err := m.Installed(ctx)
		if err != nil || len(apps) != 1 || apps[0].UpdateAvailable {
			t.Fatalf("offline list: %v %+v", err, apps)
		}
	}
	if asks() != 1 {
		t.Fatalf("an offline box asked %d times for 4 polls", asks())
	}
	now = now.Add(updateFailTTL + time.Second)
	_, _ = m.Installed(ctx)
	if asks() != 2 {
		t.Fatalf("a failed ask is never retried: %d", asks())
	}
}
