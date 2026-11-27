// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestGenerateWritesRootAndSubcommandPages(t *testing.T) {
	t.Setenv("SOURCE_DATE_EPOCH", "1700000000")
	dir := t.TempDir()
	if err := generate(dir, "9.9.9"); err != nil {
		t.Fatal(err)
	}
	root, err := os.ReadFile(filepath.Join(dir, "onemind.1"))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{".TH \"ONEMIND\" \"1\" \"Nov 2023\"", "OneMind OS 9.9.9", "SEE ALSO"} {
		if !strings.Contains(string(root), want) {
			t.Errorf("onemind.1 lacks %q", want)
		}
	}
	if strings.Contains(string(root), "Auto generated") {
		t.Error("the page carries a generation date, so builds would differ")
	}
	pages, _ := filepath.Glob(filepath.Join(dir, "onemind-*.1"))
	if len(pages) < 5 {
		t.Errorf("only %d subcommand pages", len(pages))
	}
}

func TestBadSourceDateEpochIsRefused(t *testing.T) {
	t.Setenv("SOURCE_DATE_EPOCH", "yesterday")
	if err := generate(t.TempDir(), "1"); err == nil {
		t.Fatal("want an error")
	}
}
