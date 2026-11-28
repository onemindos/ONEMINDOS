// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"strings"
	"testing"
)

func TestFilesBrowseQuotasAndTrash(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/files/roots": ok([]any{map[string]any{"root": "home:usr_1", "name": "My files", "access": "rw", "used_bytes": 2.5e9, "quota_bytes": nil, "free_bytes": 5e11}}),
		"GET /v1/files/list":  ok([]any{map[string]any{"name": "a.txt", "type": "file", "size": 1500.0, "mtime": "2026-11-20T00:00:00Z"}}),
		"GET /v1/files/stat":  ok(map[string]any{"path": "/a.txt", "type": "file", "size": 1500.0, "mtime": "2026-11-20T00:00:00Z", "mime": "text/plain"}),
		"GET /v1/files/trash": ok([]any{map[string]any{"id": "trs_1", "name": "old.txt", "size": 10.0, "trashed_at": "2026-11-01T00:00:00Z", "purge_at": "2026-12-01T00:00:00Z"}}),
		"POST /v1/files/trash/empty": func(map[string]any) (int, any) {
			return 202, map[string]any{"id": "req_9", "state": "awaiting_approval"}
		},
		"GET /v1/files/quotas": ok([]any{map[string]any{"person_id": "usr_1", "root": "home:usr_1", "limit_bytes": 1e10, "used_bytes": 2.5e9},
			map[string]any{"person_id": nil, "root": "shared", "limit_bytes": nil, "used_bytes": 0.0}}),
		"PUT /v1/files/quotas/usr_1": func(b map[string]any) (int, any) { return 200, b },
	})
	outHas(t, run(t, "", false, "files", "roots").out, "home:usr_1", "My files", "2.5 GB", "500.0 GB")
	outHas(t, run(t, "", false, "files", "list", "/docs", "--root", "home:usr_1").out, "a.txt", "1.5 KB")
	if q := g.sent("GET", "/v1/files/list")[0].query; !strings.Contains(q, "root=home%3Ausr_1") || !strings.Contains(q, "path=%2Fdocs") {
		t.Fatalf("query %q", q)
	}
	if r := run(t, "", false, "files", "list"); r.code != ExitUsage {
		t.Fatalf("needs --root %+v", r)
	}
	outHas(t, run(t, "", false, "files", "stat", "/a.txt", "--root", "home:usr_1").out, "text/plain", "1.5 KB")
	outHas(t, run(t, "", false, "files", "trash", "list", "--trash", "shared").out, "trs_1", "old.txt")
	if g.sent("GET", "/v1/files/trash")[0].query != "trash=shared" {
		t.Fatal("trash query")
	}
	r := run(t, "", false, "files", "trash", "empty", "--reason", "spring clean")
	outHas(t, r.out, "Requested", "req_9", "Files → Sharing → Requests")
	if strings.Contains(r.out, "onemind actions approve") {
		t.Fatalf("a files request is not an action: %s", r.out)
	}
	e := g.sent("POST", "/v1/files/trash/empty")[0]
	if e.body["trash"] != "home" || e.body["reason"] != "spring clean" || e.idem == "" {
		t.Fatalf("empty body %+v", e)
	}
	outHas(t, run(t, "", false, "files", "quotas", "list").out, "usr_1", "10.0 GB", "(shared)", "no limit")
	if r := run(t, "", false, "files", "quotas", "set", "usr_1", "--gb", "20"); r.code != 0 {
		t.Fatalf("quota %+v", r)
	}
	if g.sent("PUT", "/v1/files/quotas/usr_1")[0].body["limit_bytes"] != 2e10 {
		t.Fatalf("quota body %+v", g.sent("PUT", "/v1/files/quotas/usr_1")[0].body)
	}
	run(t, "", false, "files", "quotas", "set", "usr_1", "--unlimited")
	if b := g.sent("PUT", "/v1/files/quotas/usr_1")[1].body; b["limit_bytes"] != nil || len(b) != 1 {
		t.Fatalf("unlimited body %+v", b)
	}
	if r := run(t, "", false, "files", "quotas", "set", "usr_1"); r.code != ExitUsage {
		t.Fatalf("needs a choice %+v", r)
	}
	if r := run(t, "", false, "files", "quotas", "set", "usr_1", "--gb", "5", "--unlimited"); r.code != ExitUsage {
		t.Fatalf("not both %+v", r)
	}
	g.neverApproved(t)
}

func TestFilesGrantsAndRequests(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/files/grants": ok([]any{map[string]any{"id": "gr_1", "subject": map[string]any{"kind": "agent", "id": "agent:hermes"}, "root": "shared", "path": "/docs", "access": "r", "revoked_at": nil}}),
		"POST /v1/files/grants": func(map[string]any) (int, any) {
			return 202, map[string]any{"id": "req_1", "state": "awaiting_approval"}
		},
		"DELETE /v1/files/grants/gr_1": ok(map[string]any{"id": "gr_1", "revoked_at": "2026-11-26T00:00:00Z"}),
		"GET /v1/files/requests":       ok([]any{map[string]any{"id": "req_1", "type": "files.grant.create", "state": "awaiting_approval", "requested_by": "agent:hermes", "expires_at": "2026-11-27T00:00:00Z"}}),
		"GET /v1/files/requests/req_1": ok(map[string]any{"id": "req_1", "type": "files.grant.create", "state": "awaiting_approval", "risk": "medium", "requested_by": "agent:hermes"}),
	})
	outHas(t, run(t, "", false, "files", "grants", "list").out, "gr_1", "agent:hermes", "shared/docs", "active")
	r := run(t, "", false, "files", "grants", "request", "--for", "agent:hermes", "--root", "shared", "--path", "/docs", "--access", "r", "--reason", "notes")
	outHas(t, r.out, "Requested", "req_1")
	b := g.sent("POST", "/v1/files/grants")[0].body
	s := obj(b["subject"])
	if s["kind"] != "agent" || s["id"] != "agent:hermes" || b["access"] != "r" || b["approve"] != nil {
		t.Fatalf("grant body %+v", b)
	}
	run(t, "", false, "files", "grants", "request", "--for", "photos", "--root", "shared", "--path", "/p", "--access", "rw")
	if obj(g.sent("POST", "/v1/files/grants")[1].body["subject"])["kind"] != "app" {
		t.Fatal("an app subject")
	}
	// The same ask twice on the same day sends the same key, so the gateway replays the waiting request.
	run(t, "", false, "files", "grants", "request", "--for", "photos", "--root", "shared", "--path", "/p", "--access", "rw")
	reqs := g.sent("POST", "/v1/files/grants")
	if reqs[1].idem == "" || reqs[1].idem != reqs[2].idem {
		t.Fatalf("keys %q %q", reqs[1].idem, reqs[2].idem)
	}
	if r := run(t, "", false, "files", "grants", "request", "--for", "photos", "--access", "x"); r.code != ExitUsage {
		t.Fatalf("validated %+v", r)
	}
	if r := run(t, "", false, "files", "grants", "revoke", "gr_1"); r.code != ExitUsage {
		t.Fatalf("needs --yes %+v", r)
	}
	if r := run(t, "", false, "files", "grants", "revoke", "gr_1", "--yes"); r.code != 0 {
		t.Fatalf("revoke %+v", r)
	}
	run(t, "", false, "files", "grants", "list", "--all")
	if g.sent("GET", "/v1/files/grants")[1].query != "include_revoked=true" {
		t.Fatal("--all")
	}
	outHas(t, run(t, "", false, "files", "requests", "list", "--state", "awaiting_approval").out, "req_1", "files.grant.create")
	outHas(t, run(t, "", false, "files", "requests", "show", "req_1").out, "medium", "dashboard")
	g.neverApproved(t)
}

func TestPhotosAndOnboarding(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/photos/library":                ok(map[string]any{"items": []any{map[string]any{"id": "p1", "file_name": "IMG_1.jpg", "taken_at": "2026-10-01T00:00:00Z", "size": 3e6, "level": "in_verified_backup"}}, "next_cursor": "c2"}),
		"GET /v1/photos/sources/src_1/coverage": ok(map[string]any{"total": 10.0, "on_box": 9.0, "backed_up": 6.0, "verified": 4.0, "as_of": "2026-11-26T00:00:00Z"}),
		"GET /v1/photos/sources/src_1/receipts": ok(map[string]any{"items": []any{map[string]any{"client_key": "k1", "received_at": "2026-11-01T00:00:00Z", "level": "on_box"}}, "next_cursor": nil}),
		"GET /v1/onboarding/state":              ok(map[string]any{"complete": false, "settings_saved": true, "backups_enabled": false, "destinations": 0.0, "kit": map[string]any{"state": "not_issued"}}),
		"GET /v1/onboarding/settings":           ok(map[string]any{"saved": true, "box_name": "home", "time_zone": "America/New_York", "backup_choice": "usb", "backup_destination_id": nil}),
		"PUT /v1/onboarding/settings":           func(b map[string]any) (int, any) { return 200, b },
	})
	out := run(t, "", false, "photos", "library", "--limit", "5").out
	outHas(t, out, "IMG_1.jpg", "3.0 MB", "in a verified backup", "--cursor c2")
	if g.sent("GET", "/v1/photos/library")[0].query != "limit=5" {
		t.Fatalf("query %q", g.sent("GET", "/v1/photos/library")[0].query)
	}
	outHas(t, run(t, "", false, "photos", "coverage", "src_1").out, "10", "test-restored", "4")
	outHas(t, run(t, "", false, "photos", "receipts", "src_1").out, "k1", "on the box only")
	if r := run(t, "", false, "photos", "library", "--json"); obj(jsonOf(t, r.out))["next_cursor"] != "c2" {
		t.Fatalf("json %+v", r)
	}
	outHas(t, run(t, "", false, "onboarding", "state").out, "set-up complete", "no", "not_issued")
	outHas(t, run(t, "", false, "onboarding", "settings", "show").out, "home", "America/New_York")
	if r := run(t, "", false, "onboarding", "settings", "save", "--name", "home"); r.code != ExitUsage {
		t.Fatalf("needs all %+v", r)
	}
	if r := run(t, "", false, "onboarding", "settings", "save", "--name", "home", "--time-zone", "UTC", "--backup", "later"); r.code != 0 {
		t.Fatalf("save %+v", r)
	}
	if b := g.sent("PUT", "/v1/onboarding/settings")[0].body; b["box_name"] != "home" || b["backup_choice"] != "later" || b["backup_destination_id"] != nil {
		t.Fatalf("save body %+v", b)
	}
}

func TestNotifyPrefsAndSources(t *testing.T) {
	prefs := map[string]any{"quiet_hours": map[string]any{"from": "22:00", "to": "07:00", "tz": "UTC"}, "routes": []any{map[string]any{"match": map[string]any{}, "channels": []any{"*"}}},
		"digest": map[string]any{"enabled": true, "at": "08:00"}, "mutes": []any{map[string]any{"topic": "tips", "channel": "*"}}, "retention_days": 90.0}
	// The gateway's ETag rule (routers/notifications.py put_preferences): a stale If-Match is a 409.
	etag, edits := `"e1"`, 0
	var g *routeGW
	g = newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/notifications/preferences": func(map[string]any) (int, any) {
			return 200, withHeaders{prefs, map[string]string{"ETag": etag}}
		},
		"PUT /v1/notifications/preferences": func(b map[string]any) (int, any) {
			if im := g.cur.Header.Get("If-Match"); im != "" && im != etag {
				return 409, map[string]any{"error": "conflict", "message": "preferences changed since you read them (ETag mismatch)"}
			}
			edits++
			prefs, etag = b, fmt.Sprintf(`"e%d"`, edits+1)
			return 200, withHeaders{b, map[string]string{"ETag": etag}}
		},
		"GET /v1/notifications/sources": ok([]any{map[string]any{"id": "src_app_photos", "name": "Photos", "kind": "app", "posts_last_hour": 4.0, "muted": true},
			map[string]any{"id": "src_system", "name": "System", "kind": "system", "posts_last_hour": 0.0, "muted": false}}),
		"PUT /v1/notifications/sources/src_system": func(b map[string]any) (int, any) { return 200, b },
	})
	outHas(t, run(t, "", false, "notify", "prefs", "show").out, "22:00 to 07:00 (UTC)", "daily at 08:00", "tips on *", "90")
	run(t, "", false, "notify", "prefs", "mute", "photos", "--channel", "in_app")
	b := g.sent("PUT", "/v1/notifications/preferences")[0].body
	if len(list(b["mutes"])) != 2 || b["retention_days"] != 90.0 || obj(b["digest"])["at"] != "08:00" || len(list(b["routes"])) != 1 {
		t.Fatalf("mute must keep everything else: %+v", b)
	}
	run(t, "", false, "notify", "prefs", "mute", "photos", "--channel", "in_app") // twice adds nothing
	if got := g.sent("PUT", "/v1/notifications/preferences")[1].body; len(list(got["mutes"])) != 2 {
		t.Fatalf("duplicate mute %+v", got)
	}
	run(t, "", false, "notify", "prefs", "unmute", "tips")
	run(t, "", false, "notify", "prefs", "unmute", "photos", "--channel", "in_app")
	if got := g.sent("PUT", "/v1/notifications/preferences")[3].body; len(list(got["mutes"])) != 0 {
		t.Fatalf("unmute %+v", got)
	}
	// Every mute and unmute sent back the ETag it read.
	if im := g.header("PUT", "/v1/notifications/preferences", "If-Match"); len(im) != 4 || im[0] != `"e1"` || im[3] != `"e4"` {
		t.Fatalf("If-Match %v", im)
	}
	// A dashboard edit between the read and the write: 409, nothing saved, plain words, ExitConflict.
	var r result
	g.routes["GET /v1/notifications/preferences"] = func(map[string]any) (int, any) {
		cur := etag
		etag = `"dashboard"`
		return 200, withHeaders{prefs, map[string]string{"ETag": cur}}
	}
	r = run(t, "", false, "notify", "prefs", "mute", "photos")
	if r.code != ExitConflict || !strings.Contains(r.errOut, "nothing was saved") || len(g.sent("PUT", "/v1/notifications/preferences")) != 5 || edits != 4 {
		t.Fatalf("stale write %+v edits %d", r, edits)
	}
	// No ETag at all: refuse rather than write blind.
	g.routes["GET /v1/notifications/preferences"] = ok(prefs)
	if r = run(t, "", false, "notify", "prefs", "unmute", "photos"); r.code == 0 || len(g.sent("PUT", "/v1/notifications/preferences")) != 5 {
		t.Fatalf("no etag %+v", r)
	}
	if r := run(t, `{"digest": {"enabled": false}}`, false, "notify", "prefs", "set", "--file", "-"); r.code != 0 {
		t.Fatalf("set %+v", r)
	}
	outHas(t, run(t, "", false, "notify", "sources", "list").out, "src_app_photos", "muted", "src_system", "on")
	run(t, "", false, "notify", "sources", "mute", "src_system")
	if g.sent("PUT", "/v1/notifications/sources/src_system")[0].body["muted"] != true {
		t.Fatal("mute body")
	}
	run(t, "", false, "notify", "sources", "unmute", "src_system")
	if g.sent("PUT", "/v1/notifications/sources/src_system")[1].body["muted"] != false {
		t.Fatal("unmute body")
	}
	// the existing channel commands still exist beside the new ones
	if r := run(t, "", false, "notify", "channel", "list"); r.code == ExitUsage {
		t.Fatalf("channel list gone %+v", r)
	}
}

// The files request key is the same all day, and the gateway replays the stored request for it. After
// a deny or cancel, asking again must say nothing new was filed and exit ExitConflict, not "Requested".
func TestFilesRequestReplayedAfterDecision(t *testing.T) {
	state := "denied"
	newRouteGW(t, map[string]func(map[string]any) (int, any){
		"POST /v1/files/trash/empty": func(map[string]any) (int, any) {
			return 202, map[string]any{"id": "frq_x", "state": state}
		},
	})
	for _, s := range []string{"denied", "cancelled", "expired", "executed"} {
		state = s
		r := run(t, "", false, "files", "trash", "empty")
		if r.code != ExitConflict || strings.Contains(r.out, "Requested") || !strings.Contains(r.errOut, "nothing new filed") || !strings.Contains(r.errOut, s) {
			t.Fatalf("%s: %+v", s, r)
		}
		if r := run(t, "", false, "files", "trash", "empty", "--json"); r.code != ExitConflict || obj(jsonOf(t, r.out))["state"] != s {
			t.Fatalf("%s --json: %+v", s, r)
		}
	}
	state = "awaiting_approval"
	if r := run(t, "", false, "files", "trash", "empty"); r.code != 0 || !strings.Contains(r.out, "Requested") {
		t.Fatalf("waiting %+v", r)
	}
}

// files list, trash list and requests list follow the gateway's Link rel=next pages (§12.1), so a
// folder with more entries than one page is shown whole, and --json prints every entry.
func TestFilesListFollowsNextPages(t *testing.T) {
	var g *routeGW
	page := func(name string) func(map[string]any) (int, any) {
		return func(map[string]any) (int, any) {
			q := g.cur.URL.Query()
			if q.Get("cursor") == "" {
				next := g.cur.URL.Path + "?" + q.Encode() + "&cursor=bzox"
				return 200, withHeaders{[]any{map[string]any{"name": name + "-1", "id": name + "-1"}}, map[string]string{"Link": "<" + next + ">; rel=\"next\""}}
			}
			return 200, []any{map[string]any{"name": name + "-2", "id": name + "-2"}}
		}
	}
	g = newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/files/list":     page("f"),
		"GET /v1/files/trash":    page("t"),
		"GET /v1/files/requests": page("r"),
	})
	outHas(t, run(t, "", false, "files", "list", "--root", "shared").out, "f-1", "f-2")
	if q := g.sent("GET", "/v1/files/list")[1].query; !strings.Contains(q, "cursor=bzox") || !strings.Contains(q, "root=shared") {
		t.Fatalf("second page query %q", q)
	}
	if r := run(t, "", false, "files", "list", "--root", "shared", "--json"); len(jsonOf(t, r.out).([]any)) != 2 {
		t.Fatalf("json %+v", r)
	}
	outHas(t, run(t, "", false, "files", "trash", "list").out, "t-1", "t-2")
	outHas(t, run(t, "", false, "files", "requests", "list").out, "r-1", "r-2")
}

// A next link that leaves the gateway's /v1/ paths is not followed, and stopping is said on stderr.
func TestPagingRefusesForeignLink(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/files/trash": func(map[string]any) (int, any) {
			return 200, withHeaders{[]any{map[string]any{"id": "t-1"}}, map[string]string{"Link": `<https://elsewhere.example/v1/x>; rel="next"`}}
		},
	})
	r := run(t, "", false, "files", "trash", "list")
	outHas(t, r.out, "t-1")
	outHas(t, r.errOut, "more remain")
	if len(g.sent("GET", "/v1/files/trash")) != 1 {
		t.Fatal("followed a foreign link")
	}
}
