// SPDX-License-Identifier: Apache-2.0
package cli

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestSnapshotsListUsesStorageTimeline(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Snapper is a Linux command")
	}
	dir := isolate(t)
	bin := filepath.Join(dir, "snapper")
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))
	script := `#!/bin/sh
[ "$*" = "--no-dbus --utc --iso --jsonout -c storage list --columns number,type,date,cleanup,read-only" ] || exit 3
if [ "$SNAPPER_TEST_FAIL" = yes ]; then
    echo 'Storage unavailable' >&2
    exit 1
fi
cat <<'JSON'
{"storage":[
  {"number":0,"type":"single","date":"","cleanup":"","read-only":false},
  {"number":1,"type":"single","date":"2026-11-21 02:00:00","cleanup":"timeline","read-only":true},
  {"number":2,"type":"single","date":"2026-11-21 03:00:00","cleanup":"timeline","read-only":true},
  {"number":3,"type":"single","date":"2026-11-21 04:00:00","cleanup":"number","read-only":true},
  {"number":4,"type":"single","date":"2026-11-21 05:00:00","cleanup":"timeline","read-only":false}
]}
JSON
`
	if err := os.WriteFile(bin, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	r := run(t, "", false, "snapshots", "--json")
	want := `[{"id":"snapper-2-20261121T030000Z","cadence":"timeline","taken_at":"2026-11-21T03:00:00Z"},{"id":"snapper-1-20261121T020000Z","cadence":"timeline","taken_at":"2026-11-21T02:00:00Z"}]`
	if r.code != 0 || strings.Join(strings.Fields(r.out), "") != want {
		t.Fatalf("snapshots JSON: %+v", r)
	}
	t.Setenv("SNAPPER_TEST_FAIL", "yes")
	r = run(t, "", false, "snapshots", "--json")
	if r.code == 0 || r.out != "" || !strings.Contains(r.errOut, "Storage unavailable") {
		t.Fatalf("snapshots error: %+v", r)
	}
}
