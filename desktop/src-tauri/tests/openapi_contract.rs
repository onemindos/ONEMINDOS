// SPDX-License-Identifier: Apache-2.0
//! CI-08 (#233), desktop slice: the desktop reads gateway JSON by key (`api.rs`, `approvals.rs`,
//! `inbox.rs`, `manage.rs`), so a renamed field would not break the build, it would silently show
//! "unknown". This test reads the committed spec `sdk/openapi/onemind-v1.json` and fails when
//! (1) a route the desktop calls is missing or loses its method,
//! (2) a query parameter the desktop sends is dropped from a route that declares parameters,
//! (3) a response field the desktop reads is no longer in a response schema the spec types.
//! Where the spec leaves a success body untyped, only (1) and (2) can be checked; that is stated per
//! row, never hidden. Dashboard and mobile are other issues; this file is the desktop only.
use serde_json::Value;

fn spec() -> Value {
    let p = concat!(env!("CARGO_MANIFEST_DIR"), "/../../sdk/openapi/onemind-v1.json");
    serde_json::from_str(&std::fs::read_to_string(p).expect("spec file")).expect("spec json")
}

fn deref<'a>(spec: &'a Value, mut s: &'a Value) -> &'a Value {
    while let Some(r) = s.get("$ref").and_then(|r| r.as_str()) {
        s = r.trim_start_matches("#/").split('/').fold(spec, |v, k| &v[k]);
    }
    s
}

/// Properties of the JSON response body; for an array body, of its items. `None` when the spec
/// does not type the body.
fn response_fields(spec: &Value, path: &str, method: &str, status: &str) -> Option<Vec<String>> {
    let s = spec["paths"][path][method]["responses"][status]["content"]["application/json"].get("schema")?;
    let mut s = deref(spec, s);
    if s.get("type").and_then(|t| t.as_str()) == Some("array") {
        s = deref(spec, s.get("items")?);
    }
    Some(s.get("properties")?.as_object()?.keys().cloned().collect())
}

fn query_params(spec: &Value, path: &str, method: &str) -> Vec<String> {
    spec["paths"][path][method]["parameters"]
        .as_array()
        .map(|a| a.iter().filter(|p| p["in"] == "query").filter_map(|p| p["name"].as_str().map(String::from)).collect())
        .unwrap_or_default()
}

/// (method, spec path, query names, optional (success statuses, typed response fields)).
/// Fields are the declared keys read in api.rs, approvals.rs, inbox.rs and manage.rs.
#[allow(clippy::type_complexity)]
const ROUTES: &[(&str, &str, &[&str], Option<(&[&str], &[&str])>)] = &[
    ("get", "/v1/instance", &[], Some((&["200"], &["name", "version", "hub_node_id"]))),
    ("get", "/v1/nodes", &[], Some((&["200"], &["status", "node_id"]))),
    ("get", "/v1/actions", &[], Some((&["200"], &["id", "type", "state", "risk", "requested_by", "expires_at", "params", "plan_sha256"]))),
    // Older responses may also supply reason, target or principal_id as undeclared fallbacks.
    ("get", "/v1/actions/{action_id}", &[], Some((&["200"], &[
        "approval", "expires_at", "id", "params", "plan", "plan_sha256", "requested_by", "risk", "state", "type",
    ]))),
    ("post", "/v1/actions", &[], Some((&["200", "201"], &["id", "state"]))),
    ("post", "/v1/actions/{action_id}/approve", &[], None),
    ("post", "/v1/actions/{action_id}/deny", &[], None),
    ("get", "/v1/apps", &[], Some((&["200"], &["id", "name", "version", "status", "installed"]))),
    ("get", "/v1/apps/{app_id}/plan", &["type"], Some((&["200"], &[
        "plan", "plan_sha256", "policy_verdict", "reason", "risk",
    ]))),
    ("get", "/v1/os/updates", &[], None),
    ("get", "/v1/storage", &[], None),
    ("get", "/v1/me", &[], None),
    ("get", "/v1/alerts", &["state"], None),
    ("get", "/v1/notifications", &["unread", "limit"], None),
    ("post", "/v1/notifications/{notification_id}/read", &[], None),
    ("post", "/v1/notifications/read-all", &[], None),
    ("get", "/v1/backups/status", &[], None),
    ("get", "/v1/backups/destinations", &[], None),
    ("get", "/v1/backups/runs", &[], None),
    ("post", "/v1/backups/runs", &[], None),
    ("post", "/v1/backups/verify", &[], None),
    ("get", "/v1/onboarding/settings", &[], Some((&["200"], &["box_name", "time_zone", "backup_choice", "backup_destination_id", "saved"]))),
    ("put", "/v1/onboarding/settings", &[], None),
    ("get", "/v1/events", &["types"], None),
];

/// What the desktop uses that the spec does not declare today. Each is asserted still undeclared,
/// so the entry must be deleted (and the check above takes over) once the spec gains it. The
/// desktop tolerates both: it filters pending actions itself and treats a 404 preview as absent.
const KNOWN_UNDECLARED: &[(&str, &str)] = &[
    ("path", "/v1/actions/{action_id}/preview"),
    ("query", "/v1/actions:state"),
    ("query", "/v1/actions:limit"),
];

#[test]
fn every_route_the_desktop_calls_is_in_the_spec() {
    let sp = spec();
    for (m, p, _, _) in ROUTES {
        assert!(sp["paths"][*p][*m].is_object(), "desktop calls {m} {p} but the spec has no such operation");
    }
}

#[test]
fn query_parameters_the_desktop_sends_are_declared() {
    let sp = spec();
    for (m, p, q, _) in ROUTES {
        let declared = query_params(&sp, p, m);
        for name in *q {
            assert!(declared.iter().any(|d| d == name), "desktop sends ?{name} to {m} {p}; spec declares {declared:?}");
        }
    }
}

#[test]
fn response_fields_the_desktop_reads_are_in_typed_schemas() {
    let sp = spec();
    let mut typed = 0;
    for (m, p, _, response) in ROUTES {
        let Some((statuses, fields)) = response else { continue };
        for status in *statuses {
            let have = response_fields(&sp, p, m, status)
                .unwrap_or_else(|| panic!("{m} {p} {status}: the spec no longer types the body but the desktop reads {fields:?}"));
            for f in *fields {
                assert!(have.iter().any(|h| h == f), "desktop reads `{f}` from {m} {p} {status}; spec has {have:?}");
            }
        }
        typed += 1;
    }
    assert!(typed >= 8, "the field check must cover the typed routes");
}

#[test]
fn known_undeclared_list_does_not_go_stale() {
    let sp = spec();
    for (kind, what) in KNOWN_UNDECLARED {
        let still_missing = match *kind {
            "path" => !sp["paths"][*what]["get"].is_object(),
            _ => {
                let (p, q) = what.split_once(':').unwrap();
                !query_params(&sp, p, "get").iter().any(|d| d == q)
            }
        };
        assert!(still_missing, "the spec now declares {what}; remove it from KNOWN_UNDECLARED so the real check covers it");
    }
}

/// The spec is the contract: the check itself must be able to fail.
#[test]
fn the_checker_detects_a_renamed_field() {
    let mut sp = spec();
    let props = sp["paths"]["/v1/instance"]["get"]["responses"]["200"]["content"]["application/json"]["schema"].clone();
    assert!(response_fields(&sp, "/v1/instance", "get", "200").unwrap().contains(&"name".to_string()));
    let target = deref(&sp, &props).clone();
    let mut renamed = target.clone();
    let v = renamed["properties"].as_object_mut().unwrap().remove("name").unwrap();
    renamed["properties"].as_object_mut().unwrap().insert("box_label".into(), v);
    sp["paths"]["/v1/instance"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = renamed;
    assert!(!response_fields(&sp, "/v1/instance", "get", "200").unwrap().contains(&"name".to_string()));
}
