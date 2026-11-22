// SPDX-License-Identifier: Apache-2.0
//! CI-08 (#233), desktop slice: the desktop reads gateway JSON by key (`api.rs`, `approvals.rs`,
//! `inbox.rs`, `manage.rs`), so a renamed field would not break the build, it would silently show
//! "unknown". This test reads the committed spec `sdk/openapi/onemind-v1.json` and fails when
//! (1) a route the desktop calls is missing or loses its method,
//! (2) a query parameter the desktop sends is dropped from a route that declares parameters,
//! (3) a response field the desktop reads is no longer in a response schema the spec types.
//! Where the spec leaves a 200 body untyped, only (1) and (2) can be checked; that is stated per
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

/// Properties of the 200 JSON body; for an array body, of its items. `None` when the spec does
/// not type the body.
fn response_fields(spec: &Value, path: &str) -> Option<Vec<String>> {
    let s = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"].get("schema")?;
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

/// (method, spec path, query names the desktop sends, response fields the desktop reads).
/// Fields are the keys read in api.rs, approvals.rs, inbox.rs and manage.rs for that route.
#[allow(clippy::type_complexity)]
const ROUTES: &[(&str, &str, &[&str], &[&str])] = &[
    ("get", "/v1/instance", &[], &["name", "version", "hub_node_id"]),
    ("get", "/v1/nodes", &[], &["status", "node_id"]),
    ("get", "/v1/actions", &[], &["id", "type", "state", "risk", "requested_by", "expires_at", "params", "plan_sha256"]),
    ("get", "/v1/actions/{action_id}", &[], &[]),
    ("post", "/v1/actions", &[], &[]),
    ("post", "/v1/actions/{action_id}/approve", &[], &[]),
    ("post", "/v1/actions/{action_id}/deny", &[], &[]),
    ("get", "/v1/apps", &[], &["id", "name", "version", "status", "installed"]),
    ("get", "/v1/apps/{app_id}/plan", &["type"], &[]),
    ("get", "/v1/os/updates", &[], &[]),
    ("get", "/v1/storage", &[], &[]),
    ("get", "/v1/me", &[], &[]),
    ("get", "/v1/alerts", &["state"], &[]),
    ("get", "/v1/notifications", &["unread", "limit"], &[]),
    ("post", "/v1/notifications/{notification_id}/read", &[], &[]),
    ("post", "/v1/notifications/read-all", &[], &[]),
    ("get", "/v1/backups/status", &[], &[]),
    ("get", "/v1/backups/destinations", &[], &[]),
    ("get", "/v1/backups/runs", &[], &[]),
    ("post", "/v1/backups/runs", &[], &[]),
    ("post", "/v1/backups/verify", &[], &[]),
    ("get", "/v1/onboarding/settings", &[], &["box_name", "time_zone", "backup_choice", "backup_destination_id", "saved"]),
    ("put", "/v1/onboarding/settings", &[], &[]),
    ("get", "/v1/events", &["types"], &[]),
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
    for (m, p, _, fields) in ROUTES {
        if fields.is_empty() {
            continue;
        }
        let have = response_fields(&sp, p).unwrap_or_else(|| panic!("{m} {p}: the spec no longer types the body but the desktop reads {fields:?}"));
        typed += 1;
        for f in *fields {
            assert!(have.iter().any(|h| h == f), "desktop reads `{f}` from {p}; spec has {have:?}");
        }
    }
    assert!(typed >= 4, "the field check must cover the typed routes");
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
    assert!(response_fields(&sp, "/v1/instance").unwrap().contains(&"name".to_string()));
    let target = deref(&sp, &props).clone();
    let mut renamed = target.clone();
    let v = renamed["properties"].as_object_mut().unwrap().remove("name").unwrap();
    renamed["properties"].as_object_mut().unwrap().insert("box_label".into(), v);
    sp["paths"]["/v1/instance"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = renamed;
    assert!(!response_fields(&sp, "/v1/instance").unwrap().contains(&"name".to_string()));
}
