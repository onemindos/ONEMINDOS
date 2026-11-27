// SPDX-License-Identifier: Apache-2.0

package update

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// TestSignedChannelSequence: the channel sequence of test/qemu/CRITERIA-UPDATE-SIGNED.md through the box's own
// verifier (go-tuf) and selection, with one state directory kept across the steps as on a box: C1 offers V2, CK
// (signed by keys the root does not trust) is refused, C2 offers V3 to a box on V2, C1 again (a replay of older
// metadata) is refused, and CO (newer metadata listing only V1) offers nothing, "not newer than 2". The channels
// come from test/qemu/usrepo.py; os/update/tests/test_tuf_usrepo.py makes them with throwaway keys and runs this
// test with ONEMIND_US_CHANNELS (the channels directory) and ONEMIND_US_COMPATIBLE. Skipped without them.
func TestSignedChannelSequence(t *testing.T) {
	dir, compat := os.Getenv("ONEMIND_US_CHANNELS"), os.Getenv("ONEMIND_US_COMPATIBLE")
	if dir == "" || compat == "" {
		t.Skip("set by os/update/tests/test_tuf_usrepo.py")
	}
	root, err := os.ReadFile(filepath.Join(dir, "C1", "1.root.json"))
	if err != nil {
		t.Fatal(err)
	}
	tmp := t.TempDir()
	roots := filepath.Join(tmp, "roots")
	if err := os.MkdirAll(filepath.Join(roots, ChannelSecurity), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(roots, ChannelSecurity, "root.json"), root, 0o644); err != nil {
		t.Fatal(err)
	}
	var mu sync.Mutex
	current := "C1"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		ch := current
		mu.Unlock()
		name := filepath.Base(r.URL.Path)
		p := filepath.Join(dir, ch, name)
		if _, err := os.Stat(p); err != nil {
			p = filepath.Join(dir, "files", name)
		}
		http.ServeFile(w, r, p)
	}))
	defer srv.Close()
	c := &Config{Channel: ChannelSecurity, URL: srv.URL, TargetsURL: srv.URL, TUFRootDir: roots,
		StateDir: filepath.Join(tmp, "state")}
	step := func(ch, booted string) (*Target, []Skip, error) {
		mu.Lock()
		current = ch
		mu.Unlock()
		idx, err := fetchIndex(c, srv.Client(), time.Time{})
		if err != nil {
			return nil, nil, err
		}
		cand, skips := Select(c, idx, Box{Board: "x86_64-efi", Compatible: compat, Version: booted}, BadReleases{})
		return cand, skips, nil
	}
	if cand, _, err := step("C1", "1"); err != nil || cand == nil || cand.Meta.Version != "2" {
		t.Fatalf("C1 on V1: want V2 offered, got %v, %v", cand, err)
	}
	if _, _, err := step("CK", "1"); err == nil {
		t.Fatal("CK (signed by untrusted keys) was accepted")
	}
	if cand, _, err := step("C2", "2"); err != nil || cand == nil || cand.Meta.Version != "3" {
		t.Fatalf("C2 on V2: want V3 offered, got %v, %v", cand, err)
	}
	if _, _, err := step("C1", "2"); err == nil {
		t.Fatal("C1 replayed after C2 (older metadata) was accepted")
	}
	cand, skips, err := step("CO", "2")
	if err != nil || cand != nil {
		t.Fatalf("CO on V2: want nothing offered, got %v, %v", cand, err)
	}
	found := false
	for _, s := range skips {
		if strings.HasSuffix(s.Path, ".raucb") && s.Why == "not newer than 2" {
			found = true
		}
	}
	if !found {
		t.Fatalf("CO: no 'not newer than 2' skip for the V1 bundle: %v", skips)
	}
}
