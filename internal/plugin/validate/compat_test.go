// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"strings"
	"testing"
)

func TestManifestForAPI(t *testing.T) {
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	for _, version := range []string{"0.3", "0.3.0", "0.9.9"} {
		if err := ManifestForAPI(data, version); err != nil {
			t.Fatalf("%s: %v", version, err)
		}
	}
	for _, version := range []string{"", " ", " 0.3", "0.3 ", "invalid", "0.2.9", "1.0.0", "0.3.0-beta.1"} {
		if err := ManifestForAPI(data, version); err == nil {
			t.Fatalf("accepted %q", version)
		}
	}
	invalid := []byte(strings.ReplaceAll(string(data), "nodes:read", "actions:approve"))
	if err := ManifestForAPI(invalid, "0.3"); err == nil {
		t.Fatal("compatibility bypassed manifest validation")
	}
	root := bundle(t)
	if err := DirectoryForAPI(root, "0.3"); err != nil {
		t.Fatal(err)
	}
	if err := DirectoryForAPI(root, "1.0"); err == nil {
		t.Fatal("accepted incompatible bundle")
	}
	if err := DirectoryForAPI(root, ""); err == nil {
		t.Fatal("empty API level bypassed checking")
	}
}
