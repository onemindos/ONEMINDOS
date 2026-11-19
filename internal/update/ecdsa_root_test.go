// SPDX-License-Identifier: Apache-2.0

package update

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// TestRotatedECDSARootAccepted: a box that ships only the version-1 root (ed25519 keys) follows the
// signed rotation to a version-2 root whose keys are ECDSA P-256 (hardware tokens, REL-02, #272)
// and then accepts a release signed by the online keys. The repository comes from
// os/update/tests/test_tuf_hsm.py, which makes it at test time with SoftHSM keys and runs this test
// with ONEMIND_TUF_REPO (the channel directory) and ONEMIND_TUF_TRUSTED_ROOT (the v1 root.json).
// Without those variables it is skipped.
func TestRotatedECDSARootAccepted(t *testing.T) {
	repo, trusted := os.Getenv("ONEMIND_TUF_REPO"), os.Getenv("ONEMIND_TUF_TRUSTED_ROOT")
	if repo == "" || trusted == "" {
		t.Skip("set by os/update/tests/test_tuf_hsm.py")
	}
	root, err := os.ReadFile(trusted)
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	roots := filepath.Join(dir, "roots")
	if err := os.MkdirAll(filepath.Join(roots, ChannelSecurity), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(roots, ChannelSecurity, "root.json"), root, 0o644); err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.FileServer(http.Dir(repo)))
	defer srv.Close()
	c := &Config{Channel: ChannelSecurity, URL: srv.URL, TargetsURL: srv.URL,
		TUFRootDir: roots, StateDir: filepath.Join(dir, "state")}
	idx, err := fetchIndex(c, srv.Client(), time.Time{})
	if err != nil {
		t.Fatalf("the box refused the rotated channel: %v", err)
	}
	if len(idx.Targets) == 0 {
		t.Fatal("no targets after the rotation")
	}
}
