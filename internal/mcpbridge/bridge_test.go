// SPDX-License-Identifier: Apache-2.0

package mcpbridge

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

const token = "agent-token-0123456789abcdef"

// fakeGateway echoes requests as results, 202s notifications, and records protocol headers.
func fakeGateway(t *testing.T, versions *[]string) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+token {
			w.WriteHeader(401)
			fmt.Fprint(w, `{"error":"unauthenticated","message":"unknown token"}`)
			return
		}
		if versions != nil {
			*versions = append(*versions, r.Header.Get("MCP-Protocol-Version"))
		}
		var m map[string]any
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &m)
		if _, ok := m["id"]; !ok {
			w.WriteHeader(202)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		if m["method"] == "initialize" {
			fmt.Fprintf(w, `{"jsonrpc":"2.0","id":%v,"result":{"protocolVersion":"2025-06-18"}}`, m["id"])
			return
		}
		if m["method"] == "stream" {
			w.Header().Set("Content-Type", "text/event-stream")
			fmt.Fprintf(w, "event: message\ndata: {\"jsonrpc\":\"2.0\",\ndata: \"id\":%v,\"result\":{}}\n\n", m["id"])
			return
		}
		fmt.Fprintf(w, "{\"jsonrpc\": \"2.0\",\n \"id\": %v, \"result\": {\"echo\": %q}}", m["id"], m["method"])
	}))
}

func TestForwardsInOrderAndSilencesNotifications(t *testing.T) {
	var versions []string
	gw := fakeGateway(t, &versions)
	defer gw.Close()
	var in bytes.Buffer
	in.WriteString(`{"jsonrpc":"2.0","id":0,"method":"initialize","params":{}}` + "\n")
	in.WriteString(`{"jsonrpc":"2.0","method":"notifications/initialized"}` + "\n\n")
	for i := 1; i <= 1000; i++ {
		if i%10 == 0 {
			in.WriteString(`{"jsonrpc":"2.0","method":"notifications/progress"}` + "\n")
			continue
		}
		fmt.Fprintf(&in, `{"jsonrpc":"2.0","id":%d,"method":"m%d"}`+"\n", i, i)
	}
	var out, logs bytes.Buffer
	b := New(Config{Hub: gw.URL + "/", Token: token, Log: func(f string, a ...any) { fmt.Fprintf(&logs, f+"\n", a...) }})
	if err := b.Run(context.Background(), &in, &out); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(out.String()), "\n")
	if len(lines) != 1+900 {
		t.Fatalf("got %d lines", len(lines))
	}
	n := 1
	for _, l := range lines[1:] {
		for n%10 == 0 {
			n++
		}
		want := fmt.Sprintf(`{"jsonrpc":"2.0","id":%d,"result":{"echo":"m%d"}}`, n, n)
		if l != want {
			t.Fatalf("line %q, want %q", l, want)
		}
		n++
	}
	if versions[0] != "" || versions[1] != "2025-06-18" {
		t.Fatalf("protocol header %v", versions[:2])
	}
	if strings.Contains(logs.String(), token) || strings.Contains(logs.String(), "echo") {
		t.Fatal("log leaked the token or a body")
	}
}

func TestUnauthorizedBecomesRPCErrorWithHint(t *testing.T) {
	gw := fakeGateway(t, nil)
	defer gw.Close()
	var logs strings.Builder
	b := New(Config{Hub: gw.URL, Token: "wrong-token-xxxxxxxxxxxx", Log: func(f string, a ...any) { fmt.Fprintf(&logs, f+"\n", a...) }})
	got := b.Send(context.Background(), []byte(`{"jsonrpc":"2.0","id":"a","method":"tools/list"}`))
	if len(got) != 1 || !strings.Contains(string(got[0]), `"id":"a"`) || !strings.Contains(string(got[0]), "-32001") {
		t.Fatalf("%s", got)
	}
	if !strings.Contains(logs.String(), "onemind mcp doctor") || strings.Contains(logs.String(), "wrong-token") {
		t.Fatalf("stderr %q", logs.String())
	}
	if n := b.Send(context.Background(), []byte(`{"jsonrpc":"2.0","method":"notifications/x"}`)); len(n) != 0 {
		t.Fatal("notification produced output")
	}
}

func TestSSEAnswerAndUnreachableAndBadInput(t *testing.T) {
	gw := fakeGateway(t, nil)
	b := New(Config{Hub: gw.URL, Token: token})
	got := b.Send(context.Background(), []byte(`{"jsonrpc":"2.0","id":5,"method":"stream"}`))
	if len(got) != 1 || string(got[0]) != `{"jsonrpc":"2.0","id":5,"result":{}}` {
		t.Fatalf("sse %q", got)
	}
	gw.Close()
	got = b.Send(context.Background(), []byte(`{"jsonrpc":"2.0","id":6,"method":"ping"}`))
	if !strings.Contains(string(got[0]), "unreachable") {
		t.Fatalf("%s", got)
	}
	if got := b.Send(context.Background(), []byte(`nope`)); !strings.Contains(string(got[0]), "-32700") {
		t.Fatalf("%s", got)
	}
	var calls atomic.Int32
	big := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls.Add(1) }))
	defer big.Close()
	var out bytes.Buffer
	in := `{"jsonrpc":"2.0","id":1,"method":"x","params":"` + strings.Repeat("a", MaxMessage+10) + "\"}\n"
	_ = New(Config{Hub: big.URL}).Run(context.Background(), strings.NewReader(in), &out)
	if calls.Load() != 0 || !strings.Contains(out.String(), "longer than") {
		t.Fatalf("calls %d out %q", calls.Load(), out.String()[:min(200, out.Len())])
	}
}
