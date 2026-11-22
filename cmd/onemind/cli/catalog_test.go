// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/update/tuftest"
)

func catalogBundle(t *testing.T) []byte {
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	body := "id: newapp\n"
	if err := tw.WriteHeader(&tar.Header{Name: "apps/newapp/onemind.app.yaml", Typeflag: tar.TypeReg, Mode: 0o644, Size: int64(len(body))}); err != nil {
		t.Fatal(err)
	}
	tw.Write([]byte(body))
	tw.Close()
	gz.Close()
	return buf.Bytes()
}

func TestCatalogSyncAndStatus(t *testing.T) {
	isolate(t)
	dir := t.TempDir()
	repo, err := tuftest.New(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	repo.AddRaw("catalog/catalog-3.1.tar.gz", tuftest.Meta{Version: "3.1"}, catalogBundle(t))
	served := filepath.Join(dir, "repo")
	if err := repo.Publish(served, 0); err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.FileServer(http.Dir(served)))
	defer srv.Close()
	root, _ := repo.RootJSON()
	rootPath := filepath.Join(dir, "tuf", "catalog", "root.json")
	os.MkdirAll(filepath.Dir(rootPath), 0o755)
	os.WriteFile(rootPath, root, 0o644)
	conf := filepath.Join(dir, "catalog.conf")
	os.WriteFile(conf, []byte("url = "+srv.URL+"\ntuf_root_dir = "+filepath.Join(dir, "tuf")+"\nstate_dir = "+filepath.Join(dir, "state")+"\n"), 0o644)

	if r := run(t, "", false, "catalog", "status", "--config", conf); r.code != 0 || !strings.Contains(r.out, "none yet") {
		t.Fatalf("status before sync: %+v", r)
	}
	if r := run(t, "", false, "catalog", "sync", "--config", conf); r.code != 0 || !strings.Contains(r.out, "catalog 3.1: updated") {
		t.Fatalf("sync: %+v", r)
	}
	if r := run(t, "", false, "catalog", "status", "--config", conf, "--json"); r.code != 0 || !strings.Contains(r.out, `"version": "3.1"`) {
		t.Fatalf("status after sync: %+v", r)
	}
	if _, err := os.Stat(filepath.Join(dir, "state", "current", "apps", "newapp", "onemind.app.yaml")); err != nil {
		t.Fatal(err)
	}
	// A tampered bundle: the CLI fails and says the box keeps its catalog.
	repo.AddRaw("catalog/catalog-3.2.tar.gz", tuftest.Meta{Version: "3.2"}, catalogBundle(t))
	repo.Publish(served, 0)
	os.WriteFile(filepath.Join(served, "catalog-3.2.tar.gz"), []byte("evil"), 0o644)
	if r := run(t, "", false, "catalog", "sync", "--config", conf); r.code == 0 {
		t.Fatalf("tampered sync succeeded: %+v", r)
	}
}
