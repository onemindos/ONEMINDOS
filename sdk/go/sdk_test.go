// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

const token = "test-token-0123456789abcdef"

func newTest(t *testing.T, h http.HandlerFunc, opts ...Option) *Client {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	c, err := New(srv.URL, append([]Option{WithToken(token)}, opts...)...)
	if err != nil {
		t.Fatal(err)
	}
	c.sleep = func(ctx context.Context, d time.Duration) error { return ctx.Err() }
	return c
}

func writeErr(w http.ResponseWriter, status int, code, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	fmt.Fprintf(w, `{"error":%q,"message":%q}`, code, msg)
}

func TestNewRejectsBadURL(t *testing.T) {
	for _, u := range []string{"", "hub.local", "ftp://x", "http://"} {
		if _, err := New(u); err == nil {
			t.Errorf("%q accepted", u)
		}
	}
}

func TestGetRetriesThenTypedErrors(t *testing.T) {
	var n atomic.Int32
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+token {
			writeErr(w, 401, "unauthenticated", "missing bearer token")
			return
		}
		switch r.URL.Path {
		case "/v1/nodes":
			if n.Add(1) < 3 {
				w.WriteHeader(503)
				return
			}
			fmt.Fprint(w, `[{"node_id":"abc","status":"online","last_seen":"t","future_field":1}]`)
		case "/v1/nodes/x":
			writeErr(w, 404, "not_found", "no such node")
		case "/v1/instance":
			fmt.Fprint(w, `<html>proxy</html>`)
		default:
			writeErr(w, 418, "brand_new_code", "from a newer gateway")
		}
	})
	nodes, err := c.Nodes.List(context.Background())
	if err != nil || len(nodes) != 1 || n.Load() != 3 || nodes[0].AdditionalProperties["future_field"] == nil {
		t.Fatalf("nodes %v err %v attempts %d", nodes, err, n.Load())
	}
	_, err = c.Nodes.Get(context.Background(), "x")
	if !errors.Is(err, ErrNotFound) || err.Error() != "HTTP 404 not_found: no such node" {
		t.Fatalf("err %v", err)
	}
	if _, err = c.Instance.Get(context.Background()); !errors.Is(err, ErrUnexpectedResponse) {
		t.Fatalf("html: %v", err)
	}
	if _, err = c.Apps.List(context.Background()); Code(err) != "brand_new_code" || errors.Is(err, ErrConflict) {
		t.Fatalf("unknown code: %v", err)
	}
}

func TestTokenNeverPrinted(t *testing.T) {
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) {})
	if strings.Contains(c.String(), token) || !strings.Contains(c.String(), "principal=?") {
		t.Fatal(c.String())
	}
	bad, _ := New("http://127.0.0.1:1", WithToken(token), WithRetries(1))
	_, err := bad.Instance.Get(context.Background())
	if !errors.Is(err, ErrNetwork) || strings.Contains(err.Error(), token) {
		t.Fatalf("network err %v", err)
	}
}

func TestPlainHTTPWarningOnce(t *testing.T) {
	var warnings []string
	c, _ := New("http://hub.example:8080", WithWarn(func(s string) { warnings = append(warnings, s) }), WithRetries(1), WithTimeout(50*time.Millisecond))
	c.checkTransport()
	c.checkTransport()
	l, _ := New("http://localhost:8080", WithWarn(func(s string) { warnings = append(warnings, s) }))
	l.checkTransport()
	if len(warnings) != 1 {
		t.Fatalf("warnings %v", warnings)
	}
}

func TestRequestReusesIdempotencyKeyAcrossRetries(t *testing.T) {
	var mu sync.Mutex
	var keys []string
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Date", time.Now().Add(time.Hour).UTC().Format(http.TimeFormat))
		if r.URL.Path == "/v1/instance" {
			fmt.Fprint(w, `{"name":"x","version":"0","hub_node_id":null}`)
			return
		}
		var b actionBody
		_ = json.NewDecoder(r.Body).Decode(&b)
		mu.Lock()
		keys = append(keys, b.IdempotencyKey)
		first := len(keys) == 1
		mu.Unlock()
		if first {
			w.WriteHeader(502)
			return
		}
		exp, _ := time.Parse(time.RFC3339, b.ExpiresAt)
		if d := time.Until(exp); d < 24*time.Hour+50*time.Minute { // hub clock is 1 h ahead
			writeErr(w, 409, "conflict", "expiry not on the hub clock")
			return
		}
		w.WriteHeader(201)
		fmt.Fprintf(w, `{"id":"a1","type":%q,"params":{"app_id":%q},"state":"awaiting_approval","requested_by":{"id":"owner","kind":"person","role":"owner"},"idempotency_key":%q,"created_at":"t","updated_at":"t","expires_at":%q,"decided_by":null,"decided_at":null,"result":null,"version":1}`, b.Type, b.Params["app_id"], b.IdempotencyKey, b.ExpiresAt)
	})
	a, err := c.Actions.Request(context.Background(), ActionRequest{Type: ActionAppInstall, AppID: "ntfy"})
	if err != nil || a.State != "awaiting_approval" {
		t.Fatalf("%v %v", a, err)
	}
	if len(keys) != 2 || keys[0] != keys[1] || len(keys[0]) != 36 {
		t.Fatalf("keys %v", keys)
	}
}

func TestRequestReusesExpiresAtForOneKeyAcrossSeconds(t *testing.T) {
	var mu sync.Mutex
	var bodies []actionBody
	tick := 0
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		tick++ // the hub's clock (Date header) moves 5 s per answer
		w.Header().Set("Date", time.Now().Add(time.Duration(5*tick)*time.Second).UTC().Format(http.TimeFormat))
		if r.URL.Path == "/v1/instance" {
			mu.Unlock()
			fmt.Fprint(w, `{"name":"x","version":"0","hub_node_id":null}`)
			return
		}
		var b actionBody
		_ = json.NewDecoder(r.Body).Decode(&b)
		bodies = append(bodies, b)
		mu.Unlock()
		w.WriteHeader(201)
		fmt.Fprint(w, actionJSON("awaiting_approval", ""))
	})
	for _, key := range []string{"k1", "k1", "k2", "", ""} {
		if _, err := c.Actions.Request(context.Background(), ActionRequest{Type: ActionAppInstall, AppID: "x", IdempotencyKey: key}); err != nil {
			t.Fatal(err)
		}
	}
	if bodies[0].ExpiresAt != bodies[1].ExpiresAt {
		t.Fatalf("same key, different expires_at: %q vs %q", bodies[0].ExpiresAt, bodies[1].ExpiresAt)
	}
	if bodies[2].ExpiresAt == bodies[0].ExpiresAt {
		t.Fatal("another key must get its own expires_at")
	}
	if bodies[3].IdempotencyKey == bodies[4].IdempotencyKey {
		t.Fatal("no key: a fresh uuid per call")
	}
}

func TestExpiryMemoBoundedAndDropsExpired(t *testing.T) {
	var m expiryMemo
	now := time.Date(2030, 1, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < maxExpiries+10; i++ {
		m.get(fmt.Sprintf("k%d", i), now, time.Hour)
	}
	if len(m.m) != maxExpiries || len(m.order) != maxExpiries {
		t.Fatalf("not bounded: %d %d", len(m.m), len(m.order))
	}
	if got := m.get("fresh", now.Add(2*time.Hour), time.Hour); got != "2030-01-01T03:00:00Z" || len(m.m) != 1 {
		t.Fatalf("expired entries kept: %q %d", got, len(m.m))
	}
}

func actionJSON(state string, decidedBy string) string {
	d := "null"
	if decidedBy != "" {
		d = fmt.Sprintf(`{"id":%q,"kind":"person","role":"owner"}`, decidedBy)
	}
	return fmt.Sprintf(`{"id":"a1","type":"app.install","params":{"app_id":"x"},"state":%q,"requested_by":{"id":"hermes","kind":"agent","role":"agent"},"idempotency_key":"k","created_at":"t","updated_at":"t","expires_at":"t","decided_by":%s,"decided_at":null,"result":null,"version":2}`, state, d)
}

func TestApproveNeverBlindRetryAndReadBack(t *testing.T) {
	for _, tc := range []struct {
		name, principal, decidedBy string
		wantErr                    bool
	}{
		{"confirmed by read-back", "owner", "owner", false},
		{"someone else decided", "owner", "other", true},
		{"principal unknown", "", "owner", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var posts atomic.Int32
			c := newTest(t, func(w http.ResponseWriter, r *http.Request) {
				if r.Method == http.MethodPost {
					posts.Add(1)
					w.WriteHeader(502)
					return
				}
				fmt.Fprint(w, actionJSON("succeeded", tc.decidedBy))
			}, WithPrincipal(tc.principal))
			a, err := c.Actions.Approve(context.Background(), "a1")
			if posts.Load() != 1 {
				t.Fatalf("approve sent %d times", posts.Load())
			}
			if tc.wantErr != (err != nil) {
				t.Fatalf("err %v", err)
			}
			if tc.wantErr {
				var e *Error
				if !errors.Is(err, ErrAmbiguousResult) || !errors.As(err, &e) || e.Action == nil || e.Action.State != "succeeded" {
					t.Fatalf("want ambiguous with last state: %v", err)
				}
			} else if a.State != "succeeded" {
				t.Fatal(a.State)
			}
		})
	}
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) { writeErr(w, 409, "expired", "too late") })
	if _, err := c.Actions.Deny(context.Background(), "a1"); !errors.Is(err, ErrExpired) {
		t.Fatalf("clear 409 must pass through: %v", err)
	}
}

func TestWait(t *testing.T) {
	var n atomic.Int32
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) {
		states := []string{"awaiting_approval", "accepted", "dispatched", "succeeded"}
		i := int(n.Add(1)) - 1
		if i >= len(states) {
			i = len(states) - 1
		}
		fmt.Fprint(w, actionJSON(states[i], "owner"))
	})
	var seen []string
	a, err := c.Actions.Wait(context.Background(), "a1", time.Millisecond, func(a *Action) { seen = append(seen, a.State) })
	if err != nil || a.State != "succeeded" || strings.Join(seen, ",") != "awaiting_approval,accepted,dispatched,succeeded" {
		t.Fatalf("%v %v %v", a, err, seen)
	}
}

func TestVerifyChainVectors(t *testing.T) {
	root := filepath.Join("..", "testdata", "audit")
	raw, err := os.ReadFile(filepath.Join(root, "expected.json"))
	if err != nil {
		t.Fatal(err)
	}
	var want map[string]struct {
		OK          bool `json:"ok"`
		Records     int  `json:"records"`
		FirstBadSeq *int `json:"first_bad_seq"`
	}
	if err := json.Unmarshal(raw, &want); err != nil || len(want) == 0 {
		t.Fatal(err)
	}
	for name, w := range want {
		f, err := os.Open(filepath.Join(root, name))
		if err != nil {
			t.Fatal(err)
		}
		got := VerifyChain(f)
		f.Close()
		if got.OK != w.OK || got.Records != w.Records || (got.FirstBadSeq == nil) != (w.FirstBadSeq == nil) ||
			(got.FirstBadSeq != nil && *got.FirstBadSeq != *w.FirstBadSeq) {
			t.Errorf("%s: got %+v want %+v", name, got, w)
		}
	}
}

func TestCanonicalJSONMatchesPython(t *testing.T) {
	in := `{"b":"é <>&\u001b\n","a":[1,2.5,true,null],"c":{"z":1,"y":"\"q\""}}`
	dec := json.NewDecoder(strings.NewReader(in))
	dec.UseNumber()
	var v any
	_ = dec.Decode(&v)
	want := "{\"a\":[1,2.5,true,null],\"b\":\"é <>&\\u001b\\n\",\"c\":{\"y\":\"\\\"q\\\"\",\"z\":1}}"
	if got := CanonicalJSON(v); got != want {
		t.Fatalf("\n got %s\nwant %s", got, want)
	}
}

func TestSubscribeParsesResumesAndStops(t *testing.T) {
	var mu sync.Mutex
	var lastIDs []string
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		lastIDs = append(lastIDs, r.Header.Get("Last-Event-ID"))
		conn := len(lastIDs)
		mu.Unlock()
		if r.URL.Query().Get("types") != "action.*" || r.Header.Get("Accept") != "text/event-stream" {
			writeErr(w, 422, "conflict", "bad query")
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		fl := w.(http.Flusher)
		fmt.Fprint(w, "retry: 10\n\n: keepalive\n\n")
		if conn == 1 {
			fmt.Fprint(w, "id: 7\nevent: action.requested\ndata: {\"schema\":\"onemind.event/v1\",\"id\":\"7\",\"type\":\"action.requested\",\"subject\":{\"action_id\":\"a1\"},\"data\":{}}\n\n")
			fl.Flush()
			return // drop the connection: the client must resume from 7
		}
		fmt.Fprint(w, "id: 8\nevent: action.state_changed\ndata: {\"id\":\"8\",\"type\":\"action.state_changed\",\"subject\":{\"action_id\":\"a1\"},\"data\":{\"to\":\"accepted\"}}\n\n")
		fl.Flush()
		<-r.Context().Done()
	})
	var got []Event
	stop := errors.New("enough")
	err := c.Events.Subscribe(context.Background(), SubscribeOptions{Types: []string{"action.*"}}, func(e Event) error {
		got = append(got, e)
		if len(got) == 2 {
			return stop
		}
		return nil
	})
	if !errors.Is(err, stop) || len(got) != 2 || got[1].Data["to"] != "accepted" || got[0].Subject["action_id"] != "a1" {
		t.Fatalf("err %v got %+v", err, got)
	}
	mu.Lock()
	defer mu.Unlock()
	if lastIDs[0] != "" || lastIDs[1] != "7" {
		t.Fatalf("Last-Event-ID %v", lastIDs)
	}
}

func TestSubscribeEndsOn404(t *testing.T) {
	c := newTest(t, func(w http.ResponseWriter, r *http.Request) { writeErr(w, 404, "not_found", "no such resource") })
	err := c.Events.Subscribe(context.Background(), SubscribeOptions{}, func(Event) error { return nil })
	if !errors.Is(err, ErrNotFound) {
		t.Fatal(err)
	}
}

func TestFromEnv(t *testing.T) {
	t.Setenv("ONEMIND_HUB", "")
	t.Setenv("ONEMIND_GATEWAY_URL", "http://gw.local:8080")
	t.Setenv("ONEMIND_AGENT_TOKEN", "x")
	c, err := FromEnv()
	if err != nil || c.BaseURL() != "http://gw.local:8080" {
		t.Fatal(c, err)
	}
	t.Setenv("ONEMIND_GATEWAY_URL", "")
	if _, err := FromEnv(); err == nil {
		t.Fatal("want error")
	}
}
