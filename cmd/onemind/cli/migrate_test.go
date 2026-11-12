// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

const testPlan = "mig_01J0000000000000000000000A"

const goodKubeconfig = `apiVersion: v1
kind: Config
current-context: old
clusters:
- name: old
  cluster: {server: "https://old.example.test:6443", certificate-authority-data: "eA=="}
users:
- name: m
  user: {token: "generated-at-test-time"}
contexts:
- name: old
  context: {cluster: old, user: m, namespace: legacy}
`

func writeTemp(t *testing.T, name, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

type fakeHub struct {
	mu       sync.Mutex
	requests []string
	bodies   []map[string]any
	polls    int
}

func (f *fakeHub) handler(t *testing.T) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		if r.Header.Get("Authorization") != "Bearer owner-test" {
			w.WriteHeader(401)
			io.WriteString(w, `{"error":"unauthenticated","message":"unknown token"}`)
			return
		}
		f.requests = append(f.requests, r.Method+" "+r.URL.Path)
		var body map[string]any
		if r.Body != nil {
			_ = json.NewDecoder(r.Body).Decode(&body)
		}
		f.bodies = append(f.bodies, body)
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/v1/migrate/plans":
			w.WriteHeader(201)
			io.WriteString(w, `{"id":"`+testPlan+`","app_id":"notes","name":"Notes","namespace":"legacy","state":"planned","next":"import",
"report":{"blocking":0,"counts":{"fixed":2,"move":1,"drop":1,"skip":1,"note":0,"ok":3,"fail":0},
"findings":[{"level":"move","kind":"Secret","name":"notes-env","message":"values are never imported (API_KEY)","hint":"set them on the box"},
{"level":"fixed","kind":"PersistentVolumeClaim","name":"notes-data","message":"storage class fast-ssd → onemind-local","hint":null}],
"volumes":[{"pvc":"notes-data","size":"2Gi"}],"hosts":["notes.example.test"],"warnings":["plain http"]},"copies":[]}`)
		case r.Method == "POST" && strings.HasPrefix(r.URL.Path, "/v1/migrate/plans/"):
			w.WriteHeader(202)
			io.WriteString(w, `{"id":"a-1","type":"migrate.`+filepath.Base(r.URL.Path)+`","state":"awaiting_approval"}`)
		case r.Method == "GET" && r.URL.Path == "/v1/actions/a-1":
			f.polls++
			state := "awaiting_approval"
			if f.polls > 1 {
				state = "succeeded"
			}
			io.WriteString(w, `{"id":"a-1","type":"migrate.copy","state":"`+state+`","result":{"message":"copied 1 volume(s)"}}`)
		case r.Method == "GET" && r.URL.Path == "/v1/migrate/plans":
			io.WriteString(w, `[{"id":"`+testPlan+`","app_id":"notes","namespace":"legacy","state":"running","next":"cutover","report":{"blocking":0}}]`)
		default:
			w.WriteHeader(404)
			io.WriteString(w, `{"error":"not_found","message":"no such resource"}`)
		}
	})
}

func runCLI(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	code := Run(args, Env{Stdout: &out, Stderr: &errb})
	return code, out.String(), errb.String()
}

func TestMigratePlanPrintsReport(t *testing.T) {
	hub := &fakeHub{}
	srv := httptest.NewServer(hub.handler(t))
	defer srv.Close()
	t.Setenv("ONEMIND_TOKEN", "owner-test")
	kc := writeTemp(t, "kc", goodKubeconfig)
	code, out, errOut := runCLI(t, "migrate", "plan", "--hub", srv.URL, "--kubeconfig", kc, "--namespace", "legacy", "--app", "notes")
	if code != 0 {
		t.Fatalf("exit %d: %s", code, errOut)
	}
	for _, want := range []string{testPlan, "MOVE", "Secret/notes-env", "↳ set them on the box", "FIXED",
		"1 volume(s) to copy", "notes-data (2Gi)", "0 blocking", "onemind migrate import " + testPlan, "plain http"} {
		if !strings.Contains(out, want) {
			t.Errorf("output lacks %q:\n%s", want, out)
		}
	}
	body := hub.bodies[0]
	if body["kubeconfig"] != goodKubeconfig || body["namespace"] != "legacy" || body["app_id"] != "notes" {
		t.Errorf("unexpected body %v", body)
	}
	if _, ok := body["context"]; ok {
		t.Error("empty --context must not be sent")
	}
}

func TestMigrateRefusesKubeconfigWithFilesOrExec(t *testing.T) {
	t.Setenv("ONEMIND_TOKEN", "owner-test")
	for _, bad := range []string{
		strings.Replace(goodKubeconfig, `certificate-authority-data: "eA=="`, `certificate-authority: /etc/ca.crt`, 1),
		strings.Replace(goodKubeconfig, `{token: "generated-at-test-time"}`, "\n    exec: {command: aws}", 1),
	} {
		kc := writeTemp(t, "kc", bad)
		code, _, errOut := runCLI(t, "migrate", "plan", "--hub", "http://127.0.0.1:1", "--kubeconfig", kc, "--namespace", "x")
		if code != 1 || !strings.Contains(errOut, "self-contained") {
			t.Errorf("exit %d, %q", code, errOut)
		}
	}
}

func TestMigrateStepsSendTheRightBodies(t *testing.T) {
	hub := &fakeHub{}
	srv := httptest.NewServer(hub.handler(t))
	defer srv.Close()
	t.Setenv("ONEMIND_TOKEN", "owner-test")
	kc := writeTemp(t, "kc", goodKubeconfig)
	pollInterval = time.Millisecond
	cases := []struct {
		args []string
		path string
		want map[string]any
	}{
		{[]string{"migrate", "import", testPlan, "--hub", srv.URL}, "/import", map[string]any{}},
		{[]string{"migrate", "copy", "--hub", srv.URL, testPlan, "--kubeconfig", kc, "--pvc", "b", "--pvc", "a"}, "/copy",
			map[string]any{"kubeconfig": goodKubeconfig, "pvcs": []any{"a", "b"}}},
		{[]string{"migrate", "cutover", testPlan, "--hub", srv.URL, "--kubeconfig", kc, "--stop-old"}, "/cutover",
			map[string]any{"kubeconfig": goodKubeconfig, "stop_old": true}},
		{[]string{"migrate", "revert", testPlan, "--hub", srv.URL}, "/revert", map[string]any{}},
	}
	for _, c := range cases {
		code, out, errOut := runCLI(t, c.args...)
		if code != 0 || !strings.Contains(out, "awaiting_approval") {
			t.Fatalf("%v: exit %d %s %s", c.args, code, out, errOut)
		}
		last := hub.requests[len(hub.requests)-1]
		if last != "POST /v1/migrate/plans/"+testPlan+c.path {
			t.Errorf("request %q", last)
		}
		gotJSON, _ := json.Marshal(hub.bodies[len(hub.bodies)-1])
		wantJSON, _ := json.Marshal(c.want)
		if string(gotJSON) != string(wantJSON) {
			t.Errorf("%s body %s, want %s", c.path, gotJSON, wantJSON)
		}
	}
	// copy and cutover need a kubeconfig; a bad plan id is refused before any request.
	if code, _, errOut := runCLI(t, "migrate", "copy", testPlan, "--hub", srv.URL); code != 1 || !strings.Contains(errOut, "--kubeconfig") {
		t.Errorf("copy without kubeconfig: %d %s", code, errOut)
	}
	if code, _, _ := runCLI(t, "migrate", "show", "../etc", "--hub", srv.URL); code != 1 {
		t.Error("bad plan id accepted")
	}
}

func TestMigrateWait(t *testing.T) {
	hub := &fakeHub{}
	srv := httptest.NewServer(hub.handler(t))
	defer srv.Close()
	t.Setenv("ONEMIND_TOKEN", "owner-test")
	pollInterval = time.Millisecond
	kc := writeTemp(t, "kc", goodKubeconfig)
	code, out, errOut := runCLI(t, "migrate", "copy", testPlan, "--hub", srv.URL, "--kubeconfig", kc, "--wait")
	if code != 0 || !strings.Contains(out, "succeeded") || !strings.Contains(out, "copied 1 volume(s)") {
		t.Fatalf("exit %d\n%s\n%s", code, out, errOut)
	}
}

func TestMigrateListAndAuth(t *testing.T) {
	hub := &fakeHub{}
	srv := httptest.NewServer(hub.handler(t))
	defer srv.Close()
	t.Setenv("ONEMIND_TOKEN", "owner-test")
	code, out, _ := runCLI(t, "migrate", "list", "--hub", srv.URL)
	if code != 0 || !strings.Contains(out, testPlan) || !strings.Contains(out, "cutover") {
		t.Fatalf("exit %d\n%s", code, out)
	}
	t.Setenv("ONEMIND_TOKEN", "wrong")
	code, _, errOut := runCLI(t, "migrate", "list", "--hub", srv.URL)
	if code != 1 || !strings.Contains(errOut, "unauthenticated") {
		t.Errorf("exit %d %s", code, errOut)
	}
}

func TestMigrateRoleIsNamespacedAndMinimal(t *testing.T) {
	code, out, _ := runCLI(t, "migrate", "role", "--namespace", "legacy")
	if code != 0 {
		t.Fatal(code)
	}
	for _, bad := range []string{"secrets", "ClusterRole", "create", "patch", "\"*\""} {
		if strings.Contains(strings.Split(out, "# Secrets are never read")[1], bad) {
			t.Errorf("read role contains %q", bad)
		}
	}
	_, full, _ := runCLI(t, "migrate", "role", "--namespace", "legacy", "--copy", "--cutover")
	for _, want := range []string{"onemind-migrate-copy", "pods/log", "deployments/scale", "verbs: [patch]", "namespace: legacy"} {
		if !strings.Contains(full, want) {
			t.Errorf("full role lacks %q", want)
		}
	}
	if code, _, _ := runCLI(t, "migrate", "role", "--namespace", "Bad_NS"); code != 1 {
		t.Error("bad namespace accepted")
	}
}
