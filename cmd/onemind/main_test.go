package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// fakeGateway implements just enough of contract §3 GET /v1/nodes.
func fakeGateway(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.Header.Get("Authorization") != "Bearer good" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthenticated","message":"missing or unknown token"}`))
			return
		}
		if r.URL.Path != "/v1/nodes" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		_, _ = w.Write([]byte(`[
		 {"schema":"onemind.node.status/v1","node_id":"3f9c2a1b7d4e","hostname":"beelink","role":"hub","board":"x86_64-efi","arch":"amd64",
		  "os":{"id":"debian","version_id":"13","pretty":"Debian GNU/Linux 13 (trixie)"},"k3s":{"present":true,"role":"server","ready":true},
		  "status":"online","last_seen":"2026-11-11T22:00:00Z"},
		 {"schema":"onemind.node.status/v1","node_id":"0a1b2c3d4e5f","hostname":"pi5","role":"node","board":"rpi5","arch":"arm64",
		  "os":{"id":"debian","version_id":"13"},"k3s":{"present":false,"role":null,"ready":false},
		  "status":"stale","last_seen":"2026-11-11T21:59:20Z"}]`))
	}))
}

func TestNodesTable(t *testing.T) {
	gw := fakeGateway(t)
	defer gw.Close()
	var out, errb bytes.Buffer
	if code := run([]string{"nodes", "--hub", gw.URL, "--token", "good"}, &out, &errb); code != 0 {
		t.Fatalf("exit %d: %s", code, errb.String())
	}
	s := out.String()
	for _, want := range []string{"NODE_ID", "3f9c2a1b7d4e", "beelink", "x86_64-efi", "ready", "online", "pi5", "rpi5", "stale", "debian 13"} {
		if !strings.Contains(s, want) {
			t.Errorf("table missing %q:\n%s", want, s)
		}
	}
}

func TestNodesJSONAndEnvToken(t *testing.T) {
	gw := fakeGateway(t)
	defer gw.Close()
	t.Setenv("ONEMIND_TOKEN", "good")
	var out, errb bytes.Buffer
	if code := run([]string{"nodes", "--hub", gw.URL, "--json"}, &out, &errb); code != 0 {
		t.Fatalf("exit %d: %s", code, errb.String())
	}
	var v []map[string]any
	if err := json.Unmarshal(out.Bytes(), &v); err != nil || len(v) != 2 {
		t.Fatalf("json = %v %s", err, out.String())
	}
}

func TestNodesUnauthenticated(t *testing.T) {
	gw := fakeGateway(t)
	defer gw.Close()
	t.Setenv("ONEMIND_TOKEN", "")
	var out, errb bytes.Buffer
	if code := run([]string{"nodes", "--hub", gw.URL, "--token", "bad"}, &out, &errb); code != 1 {
		t.Fatalf("exit %d, want 1", code)
	}
	if !strings.Contains(errb.String(), "401 unauthenticated") {
		t.Fatalf("stderr = %q", errb.String())
	}
}

func TestNodeInfoFixture(t *testing.T) {
	var out, errb bytes.Buffer
	if code := run([]string{"node", "info", "--root", "../../internal/detect/testdata/jetson", "--arch", "arm64"}, &out, &errb); code != 0 {
		t.Fatalf("exit %d: %s", code, errb.String())
	}
	var m map[string]any
	if err := json.Unmarshal(out.Bytes(), &m); err != nil {
		t.Fatal(err)
	}
	if m["board"] != "jetson-orin" || m["schema"] != "onemind.node.status/v1" {
		t.Fatalf("node info = %v", m)
	}
}

func TestNodeInfoRejectsBadEnv(t *testing.T) {
	for _, c := range []struct{ k, v string }{
		{"ONEMIND_NODE_ROLE", "worker"},
		{"ONEMIND_NODE_ID", "bad.id"},
	} {
		t.Run(c.k, func(t *testing.T) {
			t.Setenv(c.k, c.v)
			var out, errb bytes.Buffer
			code := run([]string{"node", "info", "--root", "../../internal/detect/testdata/jetson", "--arch", "arm64"}, &out, &errb)
			if code != 1 || !strings.Contains(errb.String(), c.k) || out.Len() != 0 {
				t.Fatalf("exit %d, stderr %q, stdout %q", code, errb.String(), out.String())
			}
		})
	}
}

func TestNodeInfoFromAgent(t *testing.T) {
	ag := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/node" {
			w.WriteHeader(404)
			return
		}
		_, _ = w.Write([]byte(`{"schema":"onemind.node.status/v1","node_id":"3f9c2a1b7d4e"}`))
	}))
	defer ag.Close()
	var out, errb bytes.Buffer
	if code := run([]string{"node", "info", "--agent", ag.URL}, &out, &errb); code != 0 {
		t.Fatalf("exit %d: %s", code, errb.String())
	}
	if !strings.Contains(out.String(), "3f9c2a1b7d4e") {
		t.Fatalf("out = %s", out.String())
	}
}

func TestUsage(t *testing.T) {
	var out, errb bytes.Buffer
	if code := run(nil, &out, &errb); code != 2 || !strings.Contains(errb.String(), "usage") {
		t.Fatalf("exit %d %q", code, errb.String())
	}
}
