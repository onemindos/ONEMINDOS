// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answers below have the shape of GET /v1/fabric/events (core/onemind_core/routers/fabric_events.py).
const busEvents = `{"observer":"watching","events":[
{"seq":9,"ts":"2026-11-25T10:00:03Z","event":"fabric.auth_failed","account":null,"key":"UCVXBA2UEXAMPLE","identity":null,"client":"client","name":null,"cause":"unknown_key","reason":"Authentication Failure","repeats":58},
{"seq":8,"ts":"2026-11-25T10:00:00Z","event":"fabric.connect","account":"NODE_aaaa1111","key":"UB6UKIVGEXAMPLE","identity":"node:aaaa1111","client":"leaf","name":"leaf","cause":null,"reason":null,"repeats":null}]}`

func busHub(t *testing.T, body string) (*httptest.Server, *string) {
	t.Helper()
	seen := ""
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/fabric/events" || r.Method != http.MethodGet || r.Header.Get("Authorization") != "Bearer tok" {
			w.WriteHeader(401)
			return
		}
		seen = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv, &seen
}

func TestFabricEventsPrintsATableNewestFirst(t *testing.T) {
	srv, query := busHub(t, busEvents)
	var out bytes.Buffer
	if err := fabricEvents([]string{"--hub", srv.URL, "--token", "tok", "--count", "20"}, &out); err != nil {
		t.Fatal(err)
	}
	got := out.String()
	for _, want := range []string{"TIME\tEVENT\tWHO\tACCOUNT\tDETAIL", "auth_failed\tUCVXBA2U...\t-\tunknown_key Authentication Failure (+58 more)",
		"connect\tnode:aaaa1111\tNODE_aaaa1111\t-"} {
		if !strings.Contains(got, want) {
			t.Errorf("output lacks %q:\n%s", want, got)
		}
	}
	if strings.Index(got, "auth_failed") > strings.Index(got, "\tconnect\t") {
		t.Errorf("not newest first:\n%s", got)
	}
	if *query != "count=20" {
		t.Errorf("query = %q", *query)
	}
}

func TestFabricEventsJSONIsTheGatewaysObject(t *testing.T) {
	srv, _ := busHub(t, busEvents)
	var out bytes.Buffer
	if err := fabricEvents([]string{"--hub", srv.URL, "--token", "tok", "--json"}, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), `"observer": "watching"`) || !strings.Contains(out.String(), `"cause": "unknown_key"`) {
		t.Errorf("json = %s", out.String())
	}
}

func TestFabricEventsSaysWhenTheObserverIsOff(t *testing.T) {
	srv, _ := busHub(t, `{"observer":"off","events":[]}`)
	var out bytes.Buffer
	if err := fabricEvents([]string{"--hub", srv.URL, "--token", "tok"}, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "observer is off") {
		t.Errorf("output = %q", out.String())
	}
}

func TestFabricEventsRefusesAnOutOfRangeLimitAndABadToken(t *testing.T) {
	srv, _ := busHub(t, busEvents)
	var out bytes.Buffer
	if err := fabricEvents([]string{"--hub", srv.URL, "--token", "tok", "--count", "500"}, &out); err == nil {
		t.Error("limit 500 accepted")
	}
	if err := fabricEvents([]string{"--hub", srv.URL, "--token", "wrong"}, &out); err == nil {
		t.Error("a bad token was accepted")
	}
}
