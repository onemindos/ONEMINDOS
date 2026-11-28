// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

// kitDiskKeyHere is whether the stub's current kit holds the disk key itself (a later kit only points at the one that does).
var kitDiskKeyHere = true

var (
	testKitKey  = strings.TrimSuffix(strings.Repeat("ABCD-", 13), "-")
	testDiskKey = "disk recovery for tests only"
)

// kitHub answers the kit routes with the shapes of core/onemind_core/routers/backups.py.
type kitHubState struct {
	issues, collections atomic.Int32
	approved            atomic.Bool
}

func kitHub(t *testing.T, deliveryStatus int) *kitHubState {
	t.Helper()
	isolate(t)
	state := &kitHubState{}
	var mu sync.Mutex
	var key string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
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
		case r.Method == http.MethodGet && r.URL.Path == "/v1/actions/a_kit":
			actionState := "awaiting_approval"
			if state.approved.Load() {
				actionState = "succeeded"
			}
			jsonOut(w, 200, map[string]any{"id": "a_kit", "type": "backup.kit.issue", "state": actionState, "idempotency_key": key})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/backups/kit":
			t.Error("the CLI must not use the issue shortcut or any token-only delivery")
			jsonOut(w, 422, map[string]string{"error": "conflict", "message": "unexpected"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/backups/kit/request":
			if r.ContentLength > 0 || r.Header.Get("Idempotency-Key") == "" {
				t.Error("kit request must carry an Idempotency-Key and no body (no delivery token)")
			}
			state.issues.Add(1)
			key = r.Header.Get("Idempotency-Key")
			jsonOut(w, 202, map[string]any{"id": "a_kit", "type": "backup.kit.issue", "state": "awaiting_approval", "idempotency_key": key})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/backups/kit/a_kit/claim":
			if !state.approved.Load() {
				t.Error("claimed before approval")
			}
			if state.collections.Add(1) != 1 && deliveryStatus == 201 {
				jsonOut(w, 409, map[string]string{"error": "stale_precondition", "message": "the kit was already collected"})
				return
			}
			if deliveryStatus != 201 {
				jsonOut(w, deliveryStatus, map[string]string{"error": "unavailable", "message": "delivery was interrupted"})
				return
			}
			jsonOut(w, 200, map[string]any{"action": map[string]string{"id": "a_kit"}, "kit": map[string]any{"state": "issued", "fingerprint": "0123456789abcdef",
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
	return state
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

func TestRecoveryKitIssueOnlyFilesAPendingRequestOnABoxWithoutPasskeys(t *testing.T) {
	state := kitHub(t, 201)
	receipt := filepath.Join(t.TempDir(), "receipt.json")
	r := run(t, "", false, "--json", "recovery", "kit", "issue", "--receipt", receipt)
	if r.code != 0 || !strings.Contains(r.out, `"awaiting_approval"`) || strings.Contains(r.out, "delivery_token") || strings.Contains(r.out, testKitKey) {
		t.Fatalf("issue %+v", r)
	}
	if st, err := os.Stat(receipt); err != nil || st.Mode().Perm() != 0o600 {
		t.Fatalf("private receipt missing or has incorrect permissions: %v %v", st, err)
	}
	if r := run(t, "", false, "recovery", "kit", "collect", receipt); r.code != ExitPending || strings.Contains(r.out, testKitKey) {
		t.Fatalf("collected pending kit %+v", r)
	}
	if state.issues.Load() != 1 || state.collections.Load() != 0 {
		t.Fatal("request performed extra POSTs")
	}
}

func requestKit(t *testing.T, state *kitHubState) string {
	t.Helper()
	receipt := filepath.Join(t.TempDir(), "receipt.json")
	if r := run(t, "", false, "recovery", "kit", "issue", "--receipt", receipt); r.code != 0 {
		t.Fatalf("request %+v", r)
	}
	state.approved.Store(true)
	return receipt
}

func TestRecoveryKitCollectWritesAPrivateFileOnceAndNeverOverwrites(t *testing.T) {
	state := kitHub(t, 201)
	receipt := requestKit(t, state)
	path := filepath.Join(t.TempDir(), "kit.txt")
	r := run(t, "", false, "recovery", "kit", "collect", receipt, "--out", path)
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
	again := run(t, "", false, "recovery", "kit", "collect", receipt, "--out", path)
	if again.code == 0 || !strings.Contains(again.errOut, "nothing was collected") {
		t.Fatalf("overwrite %+v", again)
	}
	if b2, _ := os.ReadFile(path); string(b2) != string(b) {
		t.Error("an existing file was overwritten")
	}
	// The file is opened before the POST so the gateway does not issue a page without a place to save it.
	if got := state.collections.Load(); got != 1 {
		t.Errorf("collections = %d, want 1: an existing --out file must not consume the kit", got)
	}
}

func TestRecoveryKitCollectLeavesNoEmptyFileAndDoesNotRetry(t *testing.T) {
	for _, status := range []int{http.StatusUnauthorized, http.StatusServiceUnavailable} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			state := kitHub(t, status)
			receipt := requestKit(t, state)
			path := filepath.Join(t.TempDir(), "kit.txt")
			if r := run(t, "", false, "recovery", "kit", "collect", receipt, "--out", path); r.code == 0 {
				t.Fatalf("a refused collection succeeded %+v", r)
			}
			if _, err := os.Stat(path); !os.IsNotExist(err) {
				t.Errorf("an empty kit file was left behind: %v", err)
			}
			if got := state.collections.Load(); got != 1 {
				t.Errorf("collections = %d, want exactly one attempt", got)
			}
		})
	}
}

func TestRecoveryKitCollectToTerminalOnlyOnce(t *testing.T) {
	receipt := requestKit(t, kitHub(t, 201))
	if r := run(t, "", false, "recovery", "kit", "collect", receipt); r.code != 0 || !strings.Contains(r.out, testKitKey) {
		t.Fatalf("stdout issue %+v", r)
	}
	r := run(t, "", false, "recovery", "kit", "collect", receipt)
	if r.code == 0 || strings.Contains(r.out+r.errOut, testKitKey) {
		t.Fatalf("refused issue %+v", r)
	}
}
