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

var (
	testKitKey  = strings.TrimSuffix(strings.Repeat("ABCD-", 13), "-")
	testDiskKey = "disk recovery for tests only"
)

// kitHub answers POST /v1/backups/kit with the shapes of core/onemind_core/routers/backups.py (#1191).
func kitHub(t *testing.T, issueStatus int) *int {
	t.Helper()
	isolate(t)
	issues := new(int)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		if r.Method != http.MethodPost || r.URL.Path != "/v1/backups/kit" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource"})
			return
		}
		*issues++
		if issueStatus != 201 {
			jsonOut(w, issueStatus, map[string]any{"error": "unauthenticated", "message": "approvals need a passkey on this box",
				"reason": "step_up_required", "details": []map[string]string{{"action_id": "kit-action"}}})
			return
		}
		jsonOut(w, 201, map[string]any{
			"action": map[string]any{"id": "kit-action", "state": "succeeded"},
			"kit":    map[string]any{"state": "issued", "fingerprint": "0123456789abcdef", "positions": []int{2, 9}, "missing_on": []string{}, "disk_key": "included"},
			"one_time": map[string]any{"owner_key": testKitKey, "groups": []string{"ABCD"}, "check": "EFGH", "disk_key": testDiskKey,
				"disk_key_state": "included", "text": "ONEMIND EMERGENCY KIT\n" + testKitKey + "\n" + testDiskKey + "\n"}})
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return issues
}

func TestRecoveryKitIssueWritesAPrivateFileOnceAndNeverOverwrites(t *testing.T) {
	issues := kitHub(t, 201)
	path := filepath.Join(t.TempDir(), "kit.txt")
	r := run(t, "", false, "recovery", "kit", "issue", "--out", path)
	if r.code != 0 || strings.Contains(r.out, testKitKey) || strings.Contains(r.out, testDiskKey) || !strings.Contains(r.out, "0123456789abcdef") {
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
	// The file is opened before the POST: a second kit would replace the console fingerprint and add a restic key
	// nobody holds, so a file that exists must stop the command with the gateway untouched.
	if *issues != 1 {
		t.Errorf("issues = %d, want 1: an existing --out file must not issue a kit", *issues)
	}
}

func TestRecoveryKitIssueJSONWithAFileNeverPrintsTheKeys(t *testing.T) {
	kitHub(t, 201)
	path := filepath.Join(t.TempDir(), "kit.txt")
	r := run(t, "", false, "--json", "recovery", "kit", "issue", "--out", path)
	if r.code != 0 || !strings.Contains(r.out, `"saved_to"`) || strings.Contains(r.out, testKitKey) || strings.Contains(r.out, testDiskKey) {
		t.Fatalf("json issue --out %+v", r)
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

func TestRecoveryKitIssueToTerminalAndStopsAtThePasskey(t *testing.T) {
	kitHub(t, 201)
	if r := run(t, "", false, "recovery", "kit", "issue"); r.code != 0 || !strings.Contains(r.out, testKitKey) {
		t.Fatalf("stdout issue %+v", r)
	}
	kitHub(t, 401)
	r := run(t, "", false, "recovery", "kit", "issue")
	if r.code != ExitUnauthenticated || strings.Contains(r.out+r.errOut, testKitKey) {
		t.Fatalf("refused issue %+v", r)
	}
	if !strings.Contains(r.errOut, "Backups, Emergency Kit") || !strings.Contains(r.errOut, "Nothing was issued") {
		t.Errorf("the refusal must say where the passkey approves the kit: %q", r.errOut)
	}
}
