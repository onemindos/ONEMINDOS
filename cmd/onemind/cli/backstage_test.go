// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

const backstageFixture = `apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: fixture-private-name
  links:
    - url: https://example.invalid/fixture-path?param=fixture-query
    - url: https://fixture-user:fixture-value@example.invalid/
    - url: javascript:fixture-inert
    - url: http://example.invalid/fixture-plain-http
spec:
  fixtureKey: fixture-hidden-spec
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: fixture-runbook
  annotations:
    backstage.io/techdocs-ref: "dir:./fixture-runbook-path"
---
- apiVersion: backstage.io/v1alpha1
  kind: Resource
  metadata:
    name: fixture-device
- apiVersion: backstage.io/v1alpha1
  kind: Component
  metadata:
    name: fixture-app
- apiVersion: fixture.invalid/v1
  kind: FixturePrivateKind
  metadata:
    name: fixture-custom
    links:
      - url: https://example.invalid/fixture-custom-url
- apiVersion: backstage.io/v1alpha1
  kind: Component
  metadata:
    name: fixture-ambiguous-a
    name: fixture-ambiguous-b
    links:
      - url: https://example.invalid/fixture-ambiguous-url
`

func invokeBackstage(args []string, stdin string) (int, string, string) {
	var stdout, stderr bytes.Buffer
	code := Run(args, Env{Stdout: &stdout, Stderr: &stderr, Stdin: strings.NewReader(stdin)})
	return code, stdout.String(), stderr.String()
}

func TestBackstagePlanClassifiesEachEntityWithoutEchoingExport(t *testing.T) {
	code, out, errOut := invokeBackstage([]string{"import", "backstage", "--plan", "--json"}, backstageFixture)
	if code != ExitOK || errOut != "" {
		t.Fatalf("plan failed with code %d: %s", code, errOut)
	}
	var plan backstagePlan
	if err := json.Unmarshal([]byte(out), &plan); err != nil {
		t.Fatal(err)
	}
	if plan.MorePages || len(plan.Entries) != 6 {
		t.Fatalf("unexpected plan: %+v", plan)
	}
	want := []struct {
		document, entity         int
		disposition, destination string
		reasonIncludes           string
	}{
		{1, 1, "mapped", "Links", "Catalog hyperlinks"},
		{2, 1, "linked", "documentation", "TechDocs"},
		{3, 1, "archived", "private archive", "device or node"},
		{3, 2, "archived", "private archive", "app match"},
		{3, 3, "archived", "private archive", "API version"},
		{3, 4, "archived", "private archive", "usable catalog envelope"},
	}
	for i, expected := range want {
		got := plan.Entries[i]
		if got.Document != expected.document || got.Entity != expected.entity || got.Disposition != expected.disposition ||
			got.Destination != expected.destination || !strings.Contains(got.Reason, expected.reasonIncludes) {
			t.Errorf("entry %d = %+v, want %+v", i, got, expected)
		}
	}
	if plan.Entries[0].Links != 1 || plan.Entries[0].SkippedLinks != 3 || !plan.Entries[1].Documentation {
		t.Fatalf("unexpected link filtering: %+v", plan.Entries)
	}
	if strings.Contains(out, "fixture-") || strings.Contains(out, "FixturePrivateKind") || strings.Contains(out, "example.invalid") {
		t.Fatal("the plan exposed values from the export")
	}
}

func TestBackstagePlanFileNeverContactsGatewayOrCatalogLinks(t *testing.T) {
	var calls atomic.Int32
	srv := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { calls.Add(1) }))
	defer srv.Close()
	path := filepath.Join(t.TempDir(), "catalog.yaml")
	fixture := strings.ReplaceAll(backstageFixture, "https://example.invalid", srv.URL)
	if err := os.WriteFile(path, []byte(fixture), 0600); err != nil {
		t.Fatal(err)
	}
	code, out, errOut := invokeBackstage([]string{"import", "backstage", "--plan", path, "--hub", srv.URL}, "")
	if code != ExitOK || errOut != "" || !strings.Contains(out, "1/1") || !strings.Contains(out, "No changes applied") {
		t.Fatalf("plan failed with code %d: %s\n%s", code, out, errOut)
	}
	if calls.Load() != 0 || strings.Contains(out, srv.URL) || strings.Contains(out, path) || strings.Contains(out, "fixture-") {
		t.Fatal("the local plan contacted or exposed an input destination")
	}
	actual, err := os.ReadFile(path)
	if err != nil || string(actual) != fixture {
		t.Fatal("the local plan changed the input file")
	}
}

func TestBackstagePlanCatalogJSON(t *testing.T) {
	entities := `[{"apiVersion":"backstage.io/v1alpha1","kind":"User","metadata":{"name":"fixture-user"}}]`
	for _, tc := range []struct {
		payload   string
		morePages bool
	}{
		{entities, false},
		{`{"items":` + entities + `,"totalItems":2,"pageInfo":{"nextCursor":"fixture-cursor"}}`, true},
	} {
		code, out, errOut := invokeBackstage([]string{"import", "backstage", "--plan", "--json", "-"}, tc.payload)
		var plan backstagePlan
		if err := json.Unmarshal([]byte(out), &plan); code != ExitOK || err != nil || errOut != "" {
			t.Fatalf("invalid plan with code %d: %s\n%s", code, out, errOut)
		}
		if plan.MorePages != tc.morePages || len(plan.Entries) != 1 || plan.Entries[0].Disposition != "archived" || strings.Contains(out, "fixture-") {
			t.Fatalf("unexpected JSON plan: %s", out)
		}
	}
}

func TestBackstagePlanRequiresPlanFlagAndRedactsErrors(t *testing.T) {
	code, out, errOut := invokeBackstage([]string{"import", "backstage"}, backstageFixture)
	if code != ExitUsage || out != "" || !strings.Contains(errOut, "--plan is required") {
		t.Fatalf("unexpected refusal: %d %q %q", code, out, errOut)
	}
	code, out, errOut = invokeBackstage([]string{"import", "backstage", "--plan", "--json"}, backstageFixture+"---\n[fixture-invalid")
	if code == ExitOK || out != "" || !strings.Contains(errOut, "invalid Backstage YAML or JSON in document 4") || strings.Contains(errOut, "fixture-") {
		t.Fatalf("unexpected parse error: %d %q %q", code, out, errOut)
	}
	if _, err := readBackstagePlan(strings.NewReader(strings.Repeat(" ", backstageExportLimit+1))); err == nil || !strings.Contains(err.Error(), "exceeds 16 MiB") {
		t.Fatalf("unexpected oversized input result: %v", err)
	}
}
