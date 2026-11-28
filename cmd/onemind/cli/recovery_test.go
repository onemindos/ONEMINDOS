// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// kitDiskKeyHere is whether the stub's current kit holds the disk key itself (a later kit only points at the one that does).
var kitDiskKeyHere = true

var (
	testKitKey  = strings.TrimSuffix(strings.Repeat("ABCD-", 13), "-")
	testDiskKey = "disk recovery for tests only"
)

// kitHub answers the kit routes with the shapes of core/onemind_core/routers/backups.py.
func kitHub(t *testing.T, issueStatus int) *int {
	t.Helper()
	isolate(t)
	issues := new(int)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/backups/kit":
			jsonOut(w, 200, map[string]any{"state": "issued", "issued_at": "2026-11-25T10:00:00Z", "confirmed_at": nil,
				"fingerprint": "0123456789abcdef", "positions": []int{2, 9}, "disk_key_included": kitDiskKeyHere,
				"disk_key_kit":           map[string]string{"fingerprint": "fedcba9876543210", "issued_at": "2026-11-20T08:00:00Z"},
				"uncovered_destinations": []string{"dst_usb"}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/backups/kit":
			*issues++
			if issueStatus != 201 {
				jsonOut(w, issueStatus, map[string]string{"error": "unauthenticated", "message": "approvals need a passkey on this box", "reason": "step_up_required"})
				return
			}
			jsonOut(w, 201, map[string]any{"kit": map[string]any{"state": "issued", "fingerprint": "0123456789abcdef",
				"disk_key_included": true, "uncovered_destinations": []string{}},
				"one_time": map[string]any{"owner_key": testKitKey, "disk_recovery_key": testDiskKey,
					"text": "ONEMIND EMERGENCY KIT\n" + testKitKey + "\n" + testDiskKey + "\n"}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return issues
}

func TestRecoveryKitStatusShowsTheStateAndNoKey(t *testing.T) {
	kitHub(t, 201)
	r := run(t, "", false, "recovery", "kit", "status")
	if r.code != 0 || !strings.Contains(r.out, "0123456789abcdef") || !strings.Contains(r.out, "dst_usb") || !strings.Contains(r.out, "disk key in kit: true") {
		t.Fatalf("status %+v", r)
	}
	j := run(t, "", false, "--json", "recovery", "kit", "status")
	if j.code != 0 || !strings.Contains(j.out, `"disk_key_included": true`) {
		t.Fatalf("json status %+v", j)
	}
}

func TestRecoveryKitStatusNamesTheKitThatHoldsTheDiskKey(t *testing.T) {
	kitHub(t, 201)
	kitDiskKeyHere = false
	t.Cleanup(func() { kitDiskKeyHere = true })
	r := run(t, "", false, "recovery", "kit", "status")
	if r.code != 0 || !strings.Contains(r.out, "disk key in kit: false") || !strings.Contains(r.out, "fedcba9876543210") || !strings.Contains(r.out, "keep that page") {
		t.Fatalf("status %+v", r)
	}
}

func TestRecoveryKitIssueWritesAPrivateFileOnceAndNeverOverwrites(t *testing.T) {
	issues := kitHub(t, 201)
	path := filepath.Join(t.TempDir(), "kit.txt")
	r := run(t, "", false, "recovery", "kit", "issue", "--out", path)
	if r.code != 0 || strings.Contains(r.out, testKitKey) || strings.Contains(r.out, testDiskKey) {
		t.Fatalf("issue --out %+v: the keys must go to the file only", r)
	}
	b, err := os.ReadFile(path)
	if err != nil || !strings.Contains(string(b), testKitKey) || !strings.Contains(string(b), testDiskKey) {
		t.Fatalf("file %q %v", b, err)
	}
	if st, _ := os.Stat(path); st.Mode().Perm() != 0o600 {
		t.Errorf("kit file mode %v, want 0600", st.Mode().Perm())
	}
	again := run(t, "", false, "recovery", "kit", "issue", "--out", path)
	if again.code == 0 || !strings.Contains(again.errOut, "nothing was issued") {
		t.Fatalf("overwrite %+v", again)
	}
	if b2, _ := os.ReadFile(path); string(b2) != string(b) {
		t.Error("an existing file was overwritten")
	}
	// The file is opened before the POST so the gateway does not issue a page without a place to save it.
	if *issues != 1 {
		t.Errorf("issues = %d, want 1: an existing --out file must not issue a kit", *issues)
	}
}

func TestRecoveryKitIssueLeavesNoEmptyFileWhenTheGatewayRefuses(t *testing.T) {
	issues := kitHub(t, 401)
	path := filepath.Join(t.TempDir(), "kit.txt")
	if r := run(t, "", false, "recovery", "kit", "issue", "--out", path); r.code == 0 {
		t.Fatalf("a refused issue succeeded %+v", r)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Errorf("an empty kit file was left behind: %v", err)
	}
	if *issues != 1 {
		t.Errorf("issues = %d", *issues)
	}
}

func TestRecoveryKitIssueToTerminalAndRefusedWithoutAPasskey(t *testing.T) {
	kitHub(t, 201)
	if r := run(t, "", false, "recovery", "kit", "issue"); r.code != 0 || !strings.Contains(r.out, testKitKey) {
		t.Fatalf("stdout issue %+v", r)
	}
	kitHub(t, 401)
	r := run(t, "", false, "recovery", "kit", "issue")
	if r.code == 0 || strings.Contains(r.out+r.errOut, testKitKey) {
		t.Fatalf("refused issue %+v", r)
	}
}
