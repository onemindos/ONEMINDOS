// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/storage"
)

// replay serves internal/storage/testdata recordings: prefix for findmnt
// and btrfs, the blank inventory for lsblk, no SMART (virtio).
type replay struct{ prefix string }

func (r replay) Run(_ context.Context, name string, args ...string) ([]byte, int, error) {
	file := map[string]string{
		"lsblk": "blank.lsblk.json", "findmnt": r.prefix + ".findmnt.json", "smartctl": "virtio.smartctl.json",
	}[name]
	if name == "btrfs" {
		file = r.prefix + map[string]string{"show": ".show.txt", "df": ".df.txt", "stats": ".stats.txt"}[args[1]]
	}
	b, err := os.ReadFile(filepath.Join("..", "..", "..", "internal", "storage", "testdata", file))
	if name == "smartctl" {
		return b, 1, err
	}
	return b, 0, err
}

func runStorage(t *testing.T, prefix string, args ...string) string {
	t.Helper()
	old := newStorageCollector
	newStorageCollector = func() *storage.Collector { return &storage.Collector{Run: replay{prefix}} }
	t.Cleanup(func() { newStorageCollector = old })
	var out bytes.Buffer
	if err := storageCmd(args, &out); err != nil {
		t.Fatalf("%v: %v", args, err)
	}
	return out.String()
}

func TestStorageCLI(t *testing.T) {
	for _, tc := range []struct {
		prefix string
		args   []string
		want   []string
	}{
		{"unprotected", []string{"disks"}, []string{"/dev/vda", "system", "/dev/vdb", "unused"}},
		{"unprotected", []string{"health"}, []string{"unknown", "Unable to detect device type"}},
		{"degraded-written", []string{"status"}, []string{"DEGRADED (mounted degraded)", "MISSING", "Data      single", "reconnect -> scrub -> soft-convert"}},
		{"repaired", []string{"status", "--json"}, []string{`"state": "protected"`}},
		{"unprotected", []string{"plan", "protect", "--device", "/dev/vdc"}, []string{"WILL ERASE: /dev/vdc", "btrfs device add /dev/vdc1 /data", "# ERASES DATA", "plan_sha256:"}},
		{"unprotected", []string{"plan", "create", "--device", "/dev/vda"}, []string{"[FAIL] not-system:/dev/vda", "BLOCKED"}},
		{"returned", []string{"plan", "repair", "--json"}, []string{`"kind": "repair"`, `"blocked": false`}},
	} {
		out := runStorage(t, tc.prefix, tc.args...)
		for _, w := range tc.want {
			if !strings.Contains(out, w) {
				t.Errorf("%v: missing %q in\n%s", tc.args, w, out)
			}
		}
	}
	if err := storageCmd([]string{"plan", "protect"}, &bytes.Buffer{}); err == nil {
		t.Error("protect without --device accepted")
	}
}
