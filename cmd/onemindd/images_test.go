// SPDX-License-Identifier: Apache-2.0

package main

import (
	"path/filepath"
	"testing"

	"github.com/onemindos/onemindos/internal/imagegc"
)

func TestImagesSubcommandAndReport(t *testing.T) {
	if subcommands["images"] == nil {
		t.Fatal("onemindd images must be registered")
	}
	p := filepath.Join(t.TempDir(), "report.json")
	read := imagesReport(p)
	if read() != nil {
		t.Fatal("no cleaner on this node: the heartbeat must omit images")
	}
	if err := imagegc.WriteReport(p, &imagegc.Report{BudgetPct: 80, WarnPct: 70, DiskUsedPct: 72.5, LastResult: "succeeded"}); err != nil {
		t.Fatal(err)
	}
	if r := read(); r == nil || r.DiskUsedPct != 72.5 || r.WarnPct != 70 {
		t.Fatalf("report %+v", r)
	}
	if rc := runImages([]string{"-no-such-flag"}); rc != 2 {
		t.Fatalf("bad flag = %d, want 2", rc)
	}
}
