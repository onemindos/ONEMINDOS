// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"strings"
	"testing"
)

func TestSupportedLifecycleRequestGrants(t *testing.T) {
	b, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	for _, action := range []string{"install", "remove", "start", "stop", "restart", "update", "configure"} {
		if err := Manifest([]byte(strings.ReplaceAll(string(b), "actions:request:app.install", "actions:request:app."+action))); err != nil {
			t.Fatalf("%s: %v", action, err)
		}
	}
}

func TestReviewUpdateDeclarationChanges(t *testing.T) {
	old := eventManifest(t, []string{}, []string{}, []string{"events:subscribe:onemind.>"})
	next := eventManifest(t, []string{}, []string{"onemind.node.*.status"}, []string{"events:subscribe:onemind.>"})
	if d, err := Compare(old, next); err != nil || !d.WidensGrants {
		t.Fatalf("subscription: %+v %v", d, err)
	}
	old = uiManifest(t, uiDeclarations, false)
	next = uiManifest(t, strings.ReplaceAll(uiDeclarations, "id: reset", "id: reset-again"), false)
	if d, err := Compare(old, next); err != nil || !d.WidensGrants {
		t.Fatalf("alert: %+v %v", d, err)
	}
	if d, err := Compare(old, []byte(strings.ReplaceAll(string(old), "manifests/", "other/"))); err != nil || !d.WidensGrants {
		t.Fatalf("workload: %+v %v", d, err)
	}
}
