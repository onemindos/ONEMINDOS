// SPDX-License-Identifier: Apache-2.0

package update

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/update/tuftest"
)

type tarEntry struct {
	name, body string
	typ        byte
	link       string
}

func catalogTar(t *testing.T, es ...tarEntry) []byte {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	for _, e := range es {
		typ := e.typ
		if typ == 0 {
			typ = tar.TypeReg
		}
		h := &tar.Header{Name: e.name, Typeflag: typ, Mode: 0o644, Size: int64(len(e.body)), Linkname: e.link}
		if typ != tar.TypeReg {
			h.Size = 0
		}
		if err := tw.WriteHeader(h); err != nil {
			t.Fatal(err)
		}
		if typ == tar.TypeReg {
			tw.Write([]byte(e.body))
		}
	}
	tw.Close()
	gz.Close()
	return buf.Bytes()
}

func goodTar(t *testing.T, apps ...string) []byte {
	var es []tarEntry
	for _, a := range apps {
		es = append(es, tarEntry{name: "apps/" + a + "/onemind.app.yaml", body: "id: " + a + "\n"},
			tarEntry{name: "apps/" + a + "/scan.json", body: "{}"})
	}
	return catalogTar(t, es...)
}

type catFixture struct {
	t      *testing.T
	dir    string
	served string
	repo   *tuftest.Repo
	cfg    *Config
	hc     *http.Client
}

func newCatFixture(t *testing.T) *catFixture {
	t.Helper()
	f := &catFixture{t: t, dir: t.TempDir()}
	f.served = filepath.Join(f.dir, "repo")
	var err error
	if f.repo, err = tuftest.New(time.Now()); err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.FileServer(http.Dir(f.served)))
	t.Cleanup(srv.Close)
	f.hc = srv.Client()
	f.setRoot(f.repo)
	text := "url = " + srv.URL + "\ntuf_root_dir = " + filepath.Join(f.dir, "tuf") + "\nstate_dir = " + filepath.Join(f.dir, "state") + "\n"
	if f.cfg, err = ParseCatalogConfig([]byte(text)); err != nil {
		t.Fatal(err)
	}
	return f
}

func (f *catFixture) setRoot(r *tuftest.Repo) {
	b, err := r.RootJSON()
	if err != nil {
		f.t.Fatal(err)
	}
	p := filepath.Join(f.dir, "tuf", "catalog", "root.json")
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		f.t.Fatal(err)
	}
	if err := os.WriteFile(p, b, 0o644); err != nil {
		f.t.Fatal(err)
	}
}

func (f *catFixture) add(version string, content []byte) {
	f.repo.AddRaw("catalog/catalog-"+version+".tar.gz", tuftest.Meta{Version: version}, content)
}

func (f *catFixture) publish() {
	if err := f.repo.Publish(f.served, 0); err != nil {
		f.t.Fatal(err)
	}
}

func (f *catFixture) sync() (*CatalogResult, error) {
	return SyncCatalog(context.Background(), f.cfg, f.hc, time.Now())
}

func (f *catFixture) active() string {
	a, err := CatalogStatus(f.cfg)
	if err != nil {
		f.t.Fatal(err)
	}
	return a.Version
}

func (f *catFixture) manifest(app string) string {
	b, err := os.ReadFile(filepath.Join(f.cfg.StateDir, "current", "apps", app, "onemind.app.yaml"))
	if err != nil {
		return ""
	}
	return string(b)
}

func TestCatalogNewAppArrivesWithoutOSUpdate(t *testing.T) {
	f := newCatFixture(t)
	f.add("1.1", goodTar(t, "alpha"))
	f.publish()
	res, err := f.sync()
	if err != nil || res.Decision != "updated" || res.Apps != 1 {
		t.Fatalf("sync = %+v, %v", res, err)
	}
	if f.manifest("alpha") == "" || f.manifest("beta") != "" {
		t.Fatal("alpha should be live, beta not yet")
	}
	// Same version again: nothing to do.
	if res, err = f.sync(); err != nil || res.Decision != "up-to-date" {
		t.Fatalf("second sync = %+v, %v", res, err)
	}
	// The channel adds an app; the box gets it on the next sync.
	f.add("1.2", goodTar(t, "alpha", "beta"))
	f.publish()
	if res, err = f.sync(); err != nil || res.Decision != "updated" || res.Apps != 2 {
		t.Fatalf("sync = %+v, %v", res, err)
	}
	if f.manifest("beta") == "" || f.active() != "1.2" {
		t.Fatal("beta should be live at 1.2")
	}
}

func TestCatalogTamperedBundleRefused(t *testing.T) {
	f := newCatFixture(t)
	f.add("1.1", goodTar(t, "alpha"))
	f.publish()
	if _, err := f.sync(); err != nil {
		t.Fatal(err)
	}
	f.add("1.2", goodTar(t, "alpha", "beta"))
	f.publish()
	// A mirror swaps the tarball after signing: same name, other bytes, same length is not needed.
	evil := goodTar(t, "alpha", "evil")
	if err := os.WriteFile(filepath.Join(f.served, "catalog-1.2.tar.gz"), evil, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := f.sync(); err == nil {
		t.Fatal("tampered catalog was accepted")
	}
	if f.active() != "1.1" || f.manifest("evil") != "" || f.manifest("beta") != "" {
		t.Fatal("a refused catalog must leave the active one untouched")
	}
}

func TestCatalogWrongRootRefused(t *testing.T) {
	f := newCatFixture(t)
	other, err := tuftest.New(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	f.setRoot(other) // the image trusts a different key set than the one signing the channel
	f.add("1.1", goodTar(t, "alpha"))
	f.publish()
	if _, err := f.sync(); err == nil || f.active() != "" {
		t.Fatalf("a catalog signed by an unknown root was accepted (err=%v)", err)
	}
}

func TestCatalogRollbackRefused(t *testing.T) {
	f := newCatFixture(t)
	f.add("2.0", goodTar(t, "alpha"))
	f.publish()
	if _, err := f.sync(); err != nil {
		t.Fatal(err)
	}
	// A channel that now only offers an older (still validly signed) catalog must not downgrade us.
	f.repo.RemoveTarget("catalog/catalog-2.0.tar.gz")
	f.add("1.0", goodTar(t, "old"))
	f.publish()
	res, err := f.sync()
	if err != nil || res.Decision != "up-to-date" || f.active() != "2.0" || f.manifest("old") != "" {
		t.Fatalf("sync = %+v, %v, active %s", res, err, f.active())
	}
}

func TestCatalogUnsafeArchivesRefused(t *testing.T) {
	cases := map[string][]tarEntry{
		"symlink":       {{name: "apps/a/onemind.app.yaml", body: "x"}, {name: "apps/a/link", typ: tar.TypeSymlink, link: "/etc/passwd"}},
		"dotdot":        {{name: "apps/../../etc/x", body: "x"}},
		"absolute":      {{name: "/etc/x", body: "x"}},
		"outside apps":  {{name: "evil/onemind.app.yaml", body: "x"}},
		"no manifest":   {{name: "apps/a/scan.json", body: "{}"}},
		"empty":         {},
		"duplicate":     {{name: "apps/a/onemind.app.yaml", body: "x"}, {name: "apps/a/onemind.app.yaml", body: "y"}},
		"hardlink":      {{name: "apps/a/onemind.app.yaml", body: "x"}, {name: "apps/a/h", typ: tar.TypeLink, link: "apps/a/onemind.app.yaml"}},
		"folder escape": {{name: "apps/a/../b/onemind.app.yaml", body: "x"}},
	}
	for name, es := range cases {
		t.Run(name, func(t *testing.T) {
			f := newCatFixture(t)
			f.add("1.1", catalogTar(t, es...))
			f.publish()
			if _, err := f.sync(); err == nil {
				t.Fatal("unsafe catalog accepted")
			}
			if f.active() != "" {
				t.Fatal("nothing may be activated")
			}
			if _, err := os.Lstat(filepath.Join(f.cfg.StateDir, "current")); err == nil {
				t.Fatal("current symlink must not exist")
			}
		})
	}
}

func TestCatalogKeepsTwoReleases(t *testing.T) {
	f := newCatFixture(t)
	for _, v := range []string{"1.1", "1.2", "1.3"} {
		f.add(v, goodTar(t, "alpha"))
		f.publish()
		if _, err := f.sync(); err != nil {
			t.Fatal(err)
		}
	}
	ents, _ := os.ReadDir(filepath.Join(f.cfg.StateDir, "releases"))
	var names []string
	for _, e := range ents {
		names = append(names, e.Name())
	}
	if strings.Join(names, ",") != "1.2,1.3" {
		t.Fatalf("releases = %v", names)
	}
}

func TestCatalogConfigRules(t *testing.T) {
	if _, err := ParseCatalogConfig([]byte("channel = stable\nurl = https://x.example\n")); err == nil {
		t.Fatal("catalog.conf must not name an OS channel")
	}
	if _, err := ParseConfig([]byte("channel = catalog\nurl = https://x.example\n")); err == nil {
		t.Fatal("update.conf must not accept the catalog channel")
	}
	if _, err := ParseCatalogConfig([]byte("url = http://example.com\n")); err == nil {
		t.Fatal("plain http to a remote host must be refused")
	}
}
