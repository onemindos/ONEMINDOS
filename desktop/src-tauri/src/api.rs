// SPDX-License-Identifier: Apache-2.0
//! Gateway client: the routes in sdk/contracts/poc-v0.md §3, plus the §12 reads the tray uses
//! (`/v1/me`, `/v1/notifications`, `/v1/os/updates`, `/v1/backups/status`). A §12 route exists
//! only once its module ships (§12 "Compatibility"), so a 404 on one is shown as "not reported
//! by this box", never as an error and never as "all good".

use serde::Serialize;
use serde_json::Value;
use std::time::Duration;

use crate::{approvals, inbox};

/// Contract §12.1: clients send `OneMind-API-Version: 1` (lower case: HTTP names are
/// case-insensitive, and `http` refuses upper-case static names).
pub const API_VERSION_HEADER: &str = "onemind-api-version";

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ApiError {
    /// 401 or 403 without a contract error body: the token was not accepted.
    Unauthorized,
    /// Connection refused, DNS failure, TLS failure or timeout.
    Unreachable,
    Http(u16),
    BadResponse,
    /// A non-2xx answer carrying the contract's error envelope (§3, §12.2). Clients branch on
    /// `error` and `reason` only; `message` is for people.
    Refused { status: u16, error: String, reason: Option<String>, message: String },
}

impl ApiError {
    pub fn code(&self) -> String {
        match self {
            ApiError::Unauthorized => "unauthorized".into(),
            ApiError::Unreachable => "unreachable".into(),
            ApiError::Http(s) => format!("http_{s}"),
            ApiError::BadResponse => "bad_response".into(),
            ApiError::Refused { status: 401, reason: None, .. } => "unauthorized".into(),
            ApiError::Refused { error, .. } => error.clone(),
        }
    }
}

fn default_headers() -> reqwest::header::HeaderMap {
    let mut h = reqwest::header::HeaderMap::new();
    h.insert(API_VERSION_HEADER, reqwest::header::HeaderValue::from_static("1"));
    h
}

pub fn client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(6))
        .connect_timeout(Duration::from_secs(3))
        .user_agent(concat!("onemind-desktop/", env!("CARGO_PKG_VERSION")))
        .default_headers(default_headers())
        // Never follow a redirect with the bearer token to another host.
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("http client")
}

/// For `GET /v1/events` (§12.8): no overall timeout, since the stream stays open; a read
/// timeout instead, well above the gateway's 15 s keepalive.
pub fn stream_client() -> reqwest::Client {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .read_timeout(Duration::from_secs(45))
        .user_agent(concat!("onemind-desktop/", env!("CARGO_PKG_VERSION")))
        .default_headers(default_headers())
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("http client")
}

/// Ids from the box (action ids, notification ids) go into URL paths, so only plain id
/// characters are accepted: no `/`, `.`, `%` or `?` can steer the request to another route.
pub fn safe_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 128 && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

/// GET `base + path` with the bearer token. `Ok(None)` means 404.
pub async fn get(c: &reqwest::Client, base: &str, token: Option<&str>, path: &str) -> Result<Option<Value>, ApiError> {
    let mut req = c.get(format!("{base}{path}"));
    if let Some(t) = token {
        req = req.bearer_auth(t);
    }
    let resp = req.send().await.map_err(|_| ApiError::Unreachable)?;
    match resp.status().as_u16() {
        200..=299 => resp.json::<Value>().await.map(Some).map_err(|_| ApiError::BadResponse),
        401 | 403 => Err(ApiError::Unauthorized),
        404 => Ok(None),
        s => Err(ApiError::Http(s)),
    }
}

/// POST a JSON body. A refusal keeps the contract's `error` and `reason` so callers can tell
/// `step_up_required` from `plan_changed` from a wrong token.
pub async fn post(c: &reqwest::Client, base: &str, token: &str, path: &str, body: &Value) -> Result<Value, ApiError> {
    let resp = c
        .post(format!("{base}{path}"))
        .bearer_auth(token)
        .json(body)
        .send()
        .await
        .map_err(|_| ApiError::Unreachable)?;
    let status = resp.status().as_u16();
    let v: Value = resp.json().await.unwrap_or(Value::Null);
    if (200..300).contains(&status) {
        return Ok(v);
    }
    Err(refusal(status, &v))
}

pub fn refusal(status: u16, v: &Value) -> ApiError {
    match s(v, "error") {
        Some(error) => ApiError::Refused {
            status,
            error,
            reason: s(v, "reason"),
            message: s(v, "message").unwrap_or_default().chars().take(300).collect(),
        },
        None if status == 401 || status == 403 => ApiError::Unauthorized,
        None => ApiError::Http(status),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Pending {
    pub id: String,
    pub kind: String,
    pub target: Option<String>,
    pub requested_by: Option<String>,
    pub expires_at: Option<String>,
    /// §12.3 risk class, when the box reports it.
    pub risk: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Updates {
    pub nodes_reporting: usize,
    pub available: usize,
    pub security: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Backups {
    /// `ok | stale | failing | not_configured | verified | unverified | none`, as the box says it.
    pub health: String,
    pub last_success_at: Option<String>,
}

/// One open alert from `GET /v1/alerts?state=open` (contract §12.14), reduced to what the tray shows.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Alert {
    pub id: String,
    /// `info | warning | critical`; anything else is read as `info`.
    pub severity: String,
    pub title: String,
    /// `open | acknowledged`.
    pub state: String,
    /// A path on the box's dashboard; opened only on the box's own origin.
    pub link: Option<String>,
}

/// OS slot and update state from `GET /v1/os/updates`: the first node that runs an update service
/// (a one-box home has one; the dashboard shows the rest).
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct OsState {
    pub version: Option<String>,
    /// The A/B slot the node booted from (`A`/`B`, as RAUC names it).
    pub booted_slot: Option<String>,
    /// `idle | checking | downloading | installing | pending_reboot | committed | rolled_back | unknown ...`, as the box says it.
    pub state: Option<String>,
    pub available_version: Option<String>,
    pub nodes: usize,
}

/// Data-set health from `GET /v1/storage`. `available: false` means this box has no managed storage.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct StorageState {
    pub available: bool,
    pub state: Option<String>,
    pub used_bytes: Option<u64>,
    pub total_bytes: Option<u64>,
    pub members: usize,
    pub missing: usize,
    pub needs_scrub: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Status {
    pub box_id: String,
    pub reachable: bool,
    pub error: Option<String>,
    pub name: Option<String>,
    pub version: Option<String>,
    pub nodes_total: usize,
    pub nodes_online: usize,
    pub pending: Vec<Pending>,
    /// `None`: the box does not serve the route yet.
    pub updates: Option<Updates>,
    pub backups: Option<Backups>,
    /// `GET /v1/me` (§12.6): who this computer's token is and whether it has passkeys.
    pub me: Option<approvals::Me>,
    /// Unread items of `GET /v1/notifications` (§12.14). `None`: no inbox on this box, or the
    /// token is not a person's (only people have an inbox).
    pub inbox: Option<Vec<inbox::Item>>,
    /// Open alerts (`GET /v1/alerts`). `None`: this box does not serve the route.
    pub alerts: Option<Vec<Alert>>,
    /// `None`: no `/v1/os/updates` on this box, or no node reports an update service.
    pub os: Option<OsState>,
    /// `None`: no `/v1/storage` on this box.
    pub storage: Option<StorageState>,
    /// Unix seconds when this was read, so the UI can say "from 3 min ago".
    pub fetched_at: u64,
}

pub fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

pub fn s(v: &Value, k: &str) -> Option<String> {
    v.get(k).and_then(|x| x.as_str()).map(str::to_string)
}

/// At most `n` characters (not bytes), with "…" when cut.
pub fn clip(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        return s.to_string();
    }
    let mut out: String = s.chars().take(n.saturating_sub(1)).collect();
    out.push('…');
    out
}

/// Accept a bare array (§12.1 lists) or `{ "items": [...] }` / `{ "nodes": [...] }`.
pub fn items(v: &Value) -> Vec<Value> {
    if let Some(a) = v.as_array() {
        return a.clone();
    }
    for k in ["items", "nodes", "actions"] {
        if let Some(a) = v.get(k).and_then(|x| x.as_array()) {
            return a.clone();
        }
    }
    Vec::new()
}

/// `requested_by` is a string in §3 and `{id, kind}` in §12.4.
pub fn requester(a: &Value) -> Option<String> {
    s(a, "requested_by")
        .or_else(|| a.get("requested_by").and_then(|r| s(r, "id")))
        .or_else(|| s(a, "principal_id"))
}

pub fn target(a: &Value) -> Option<String> {
    a.get("params")
        .and_then(|p| s(p, "app_id").or_else(|| s(p, "node_id")).or_else(|| s(p, "snapshot_id")))
        .or_else(|| a.get("target").and_then(|t| s(t, "id")))
}

pub fn parse_pending(actions: &Value) -> Vec<Pending> {
    items(actions)
        .iter()
        .filter(|a| a.get("state").and_then(|x| x.as_str()) == Some("awaiting_approval"))
        .filter(|a| a.get("id").and_then(|x| x.as_str()).is_some_and(safe_id))
        .map(|a| Pending {
            id: s(a, "id").unwrap_or_default(),
            kind: s(a, "type").unwrap_or_else(|| "action".into()),
            target: target(a),
            requested_by: requester(a),
            expires_at: s(a, "expires_at"),
            risk: s(a, "risk"),
        })
        .collect()
}

/// What the gateway serves for OS updates: `GET /v1/os/updates` answers `{nodes: [...], install}`.
/// (`/v1/os/status`, an older draft's name, is not a gateway route and answered 404.)
pub const UPDATES_PATH: &str = "/v1/os/updates";

/// The gateway's `GET /v1/os/updates`: one entry per node with `reported` (does it run an update
/// service) and `available_version` (the update on offer, or null). It does not say whether an
/// update is a security one, so `security` stays false there. Older drafts' shapes are still read:
/// the heartbeat `update` object, and `available: {version, security} | null`.
pub fn parse_updates(v: &Value) -> Updates {
    let mut nodes = items(v);
    // Nodes that run no update service say nothing about updates; do not count them as reporting.
    nodes.retain(|n| n.get("reported").and_then(|r| r.as_bool()) != Some(false));
    let mut available = 0;
    let mut security = false;
    for n in &nodes {
        let u = n.get("update").unwrap_or(n);
        if s(n, "available_version").is_some() {
            available += 1;
            continue;
        }
        if let Some(a) = u.get("available").filter(|a| !a.is_null()) {
            available += 1;
            security |= a.get("security").and_then(|x| x.as_bool()).unwrap_or(false);
        }
        security |= u.get("security").and_then(|x| x.as_bool()).unwrap_or(false) && u.get("available").is_some_and(|a| !a.is_null());
    }
    Updates { nodes_reporting: nodes.len(), available, security }
}

pub fn parse_backups(v: &Value) -> Backups {
    // Two drafts exist (docs/leap/dev/API.md and CONTRACT-12-DRAFT); read either shape.
    if let Some(h) = s(v, "health") {
        return Backups { health: h, last_success_at: s(v, "last_success_at") };
    }
    if let Some(b) = v.get("box") {
        return Backups {
            health: s(b, "state").unwrap_or_else(|| "unknown".into()),
            last_success_at: s(b, "last_success_at"),
        };
    }
    Backups { health: "unknown".into(), last_success_at: None }
}

pub fn parse_alerts(v: &Value) -> Vec<Alert> {
    items(v)
        .iter()
        .filter_map(|a| {
            let id = s(a, "id").filter(|i| safe_id(i))?;
            let state = s(a, "state").unwrap_or_else(|| "open".into());
            if state != "open" && state != "acknowledged" {
                return None;
            }
            Some(Alert {
                id,
                severity: s(a, "severity").filter(|x| matches!(x.as_str(), "info" | "warning" | "critical")).unwrap_or_else(|| "info".into()),
                title: clip(&s(a, "title").unwrap_or_else(|| "Alert".into()), 200),
                state,
                link: s(a, "link").map(|l| clip(&l, 500)),
            })
        })
        .collect()
}

/// `GET /v1/os/updates` is `{nodes: [...], install}`; each node has `rauc.booted_slot` and the
/// update service's `state`, `current_version`, `available_version` (`reported: false` when the
/// node runs none). Picks the first reporting node. `None` when none reports.
pub fn parse_os(v: &Value) -> Option<OsState> {
    let nodes = items(v);
    let n = nodes.iter().find(|n| n.get("reported").and_then(|x| x.as_bool()) == Some(true))?;
    let slot = n.get("rauc").and_then(|r| s(r, "booted_slot")).map(|x| clip(&x, 40));
    Some(OsState {
        version: s(n, "current_version").map(|x| clip(&x, 60)),
        booted_slot: slot,
        state: s(n, "state").map(|x| clip(&x, 40)),
        available_version: s(n, "available_version").map(|x| clip(&x, 60)),
        nodes: nodes.len(),
    })
}

/// `GET /v1/storage`: `{enabled, available, state, used_bytes, members: [{missing, size_bytes}], needs_scrub}`.
pub fn parse_storage(v: &Value) -> StorageState {
    let members = v.get("members").and_then(|m| m.as_array()).cloned().unwrap_or_default();
    let missing = members.iter().filter(|m| m.get("missing").and_then(|x| x.as_bool()) == Some(true)).count();
    let total: u64 = members.iter().filter_map(|m| m.get("size_bytes").and_then(|x| x.as_u64())).sum();
    StorageState {
        available: v.get("available").and_then(|x| x.as_bool()).unwrap_or(false),
        state: s(v, "state").map(|x| clip(&x, 40)),
        used_bytes: v.get("used_bytes").and_then(|x| x.as_u64()),
        total_bytes: if total > 0 { Some(total) } else { None },
        members: members.len(),
        missing,
        needs_scrub: v.get("needs_scrub").and_then(|x| x.as_bool()).unwrap_or(false),
    }
}

/// Pending approvals only (§12.4 filter; older gateways ignore the query and send everything,
/// which `parse_pending` filters again).
pub const PENDING_PATH: &str = "/v1/actions?state=awaiting_approval&limit=50";
/// The newest unread inbox items (§12.14).
pub const INBOX_UNREAD_PATH: &str = "/v1/notifications?unread=true&limit=20";
/// Open and acknowledged alerts the token may see (§12.14).
pub const ALERTS_PATH: &str = "/v1/alerts?state=open";

impl Status {
    /// Nothing known yet: unreachable until the box answers.
    pub fn unasked(box_id: &str) -> Status {
        Status {
            box_id: box_id.to_string(),
            reachable: false,
            error: None,
            name: None,
            version: None,
            nodes_total: 0,
            nodes_online: 0,
            pending: Vec::new(),
            updates: None,
            backups: None,
            me: None,
            inbox: None,
            alerts: None,
            os: None,
            storage: None,
            fetched_at: now(),
        }
    }
}

pub async fn status(c: &reqwest::Client, box_id: &str, base: &str, token: &str) -> Status {
    let mut st = Status::unasked(box_id);
    let t = Some(token);
    let (inst, nodes, actions, upd, bk, me, ntf, alr, osu, sto) = tokio::join!(
        get(c, base, t, "/v1/instance"),
        get(c, base, t, "/v1/nodes"),
        get(c, base, t, PENDING_PATH),
        get(c, base, t, UPDATES_PATH),
        get(c, base, t, "/v1/backups/status"),
        get(c, base, t, "/v1/me"),
        get(c, base, t, INBOX_UNREAD_PATH),
        get(c, base, t, ALERTS_PATH),
        get(c, base, t, "/v1/os/updates"),
        get(c, base, t, "/v1/storage"),
    );
    match inst {
        Ok(Some(i)) => {
            st.reachable = true;
            st.name = s(&i, "name");
            st.version = s(&i, "version");
        }
        Ok(None) => {
            st.error = Some("not_a_onemind_box".into());
            return st;
        }
        Err(e) => {
            st.error = Some(e.code());
            return st;
        }
    }
    if let Ok(Some(n)) = nodes {
        let list = items(&n);
        st.nodes_total = list.len();
        st.nodes_online = list.iter().filter(|x| x.get("status").and_then(|v| v.as_str()) == Some("online")).count();
    }
    if let Ok(Some(a)) = actions {
        st.pending = parse_pending(&a);
    }
    if let Ok(Some(u)) = upd {
        st.updates = Some(parse_updates(&u));
    }
    if let Ok(Some(b)) = bk {
        st.backups = Some(parse_backups(&b));
    }
    if let Ok(Some(m)) = me {
        st.me = Some(approvals::parse_me(&m));
    }
    if let Ok(Some(n)) = ntf {
        st.inbox = Some(inbox::parse(&n).into_iter().filter(|i| i.read_at.is_none()).collect());
    }
    if let Ok(Some(a)) = alr {
        st.alerts = Some(parse_alerts(&a));
    }
    if let Ok(Some(o)) = osu {
        st.os = parse_os(&o);
    }
    if let Ok(Some(x)) = sto {
        st.storage = Some(parse_storage(&x));
    }
    st
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn pending_only_awaiting() {
        let v = json!([
            {"id": "a1", "type": "app.install", "state": "awaiting_approval", "params": {"app_id": "jellyfin"}, "requested_by": "hermes"},
            {"id": "a2", "type": "app.remove", "state": "succeeded", "params": {"app_id": "x"}}
        ]);
        let p = parse_pending(&v);
        assert_eq!(p.len(), 1);
        assert_eq!(p[0].target.as_deref(), Some("jellyfin"));
        assert_eq!(p[0].requested_by.as_deref(), Some("hermes"));
    }

    #[test]
    fn pending_reads_v12_requester_and_risk_and_drops_unsafe_ids() {
        let v = json!([
            {"id": "6f1c9e0a-1", "type": "backup.restore", "state": "awaiting_approval", "risk": "destructive",
             "params": {"snapshot_id": "snap_01"}, "requested_by": {"id": "agent:hermes-agent", "kind": "agent"}},
            {"id": "../../v1/tokens", "type": "app.install", "state": "awaiting_approval"}
        ]);
        let p = parse_pending(&v);
        assert_eq!(p.len(), 1);
        assert_eq!(p[0].requested_by.as_deref(), Some("agent:hermes-agent"));
        assert_eq!(p[0].risk.as_deref(), Some("destructive"));
        assert_eq!(p[0].target.as_deref(), Some("snap_01"));
    }

    #[test]
    fn ids_are_plain() {
        assert!(safe_id("6f1c9e0a-1b2c-4d5e-8f90-a1b2c3d4e5f6"));
        assert!(safe_id("ntf_01J9ZK"));
        for bad in ["", "a/b", "..", "a?b=1", "a%2Fb", "a b", &"x".repeat(129)] {
            assert!(!safe_id(bad), "{bad}");
        }
    }

    #[test]
    fn updates_counts_available() {
        let v = json!([{"node_id": "n1", "update": {"available": {"version": "0.2.0", "security": true}}}, {"node_id": "n2", "update": {"available": null}}]);
        let u = parse_updates(&v);
        assert_eq!((u.nodes_reporting, u.available, u.security), (2, 1, true));
        // §12.13 shape: `available` next to the heartbeat fields.
        let v = json!([{"node_id": "n1", "state": "idle", "available": {"version": "0.3.0", "security": false}}]);
        assert_eq!(parse_updates(&v).available, 1);
    }

    #[test]
    fn updates_read_the_gateway_route() {
        // GET /v1/os/updates, as core/onemind_core/osupdate.py node_view builds it.
        assert_eq!(UPDATES_PATH, "/v1/os/updates");
        let v = json!({"nodes": [
            {"node_id": "hub", "reported": true, "available_version": "0.4.0", "current_version": "0.3.0"},
            {"node_id": "pi", "reported": true, "available_version": null, "current_version": "0.4.0"},
            {"node_id": "old", "reported": false, "available_version": null}
        ], "install": {"available": false}});
        let u = parse_updates(&v);
        // The node without an update service is not "reporting"; one update is on offer; security is not said.
        assert_eq!((u.nodes_reporting, u.available, u.security), (2, 1, false));
    }

    #[test]
    fn backups_both_drafts() {
        assert_eq!(parse_backups(&json!({"health": "stale"})).health, "stale");
        assert_eq!(parse_backups(&json!({"box": {"state": "verified"}})).health, "verified");
    }

    #[test]
    fn alerts_keep_open_ones_with_safe_ids() {
        let v = json!([
            {"id": "alr_1", "severity": "critical", "title": "Disk failing", "state": "open", "link": "/storage"},
            {"id": "alr_2", "severity": "loud", "title": "Seen", "state": "acknowledged"},
            {"id": "alr_3", "title": "Done", "state": "resolved"},
            {"id": "../x", "title": "bad", "state": "open"}
        ]);
        let a = parse_alerts(&v);
        assert_eq!(a.len(), 2);
        assert_eq!((a[0].severity.as_str(), a[0].link.as_deref()), ("critical", Some("/storage")));
        assert_eq!(a[1].severity, "info");
    }

    #[test]
    fn os_state_comes_from_the_first_reporting_node() {
        let v = json!({"nodes": [
            {"node_id": "n0", "reported": false, "rauc": {"booted_slot": null}},
            {"node_id": "n1", "reported": true, "state": "idle", "current_version": "0.4.1", "available_version": "0.4.2", "rauc": {"present": true, "booted_slot": "A"}}
        ], "install": {}});
        let o = parse_os(&v).unwrap();
        assert_eq!((o.booted_slot.as_deref(), o.state.as_deref(), o.available_version.as_deref(), o.nodes), (Some("A"), Some("idle"), Some("0.4.2"), 2));
        assert!(parse_os(&json!({"nodes": [{"node_id": "n0", "reported": false}]})).is_none());
    }

    #[test]
    fn storage_sums_members_and_counts_missing() {
        let v = json!({"enabled": true, "available": true, "state": "degraded", "used_bytes": 100, "needs_scrub": true,
            "members": [{"devid": 1, "missing": false, "size_bytes": 500}, {"devid": 2, "missing": true, "size_bytes": 500}]});
        let st = parse_storage(&v);
        assert_eq!((st.available, st.members, st.missing, st.total_bytes, st.needs_scrub), (true, 2, 1, Some(1000), true));
        assert!(!parse_storage(&json!({"enabled": false, "available": false})).available);
    }

    #[test]
    fn refusal_keeps_error_and_reason() {
        let e = refusal(401, &json!({"error": "unauthenticated", "message": "m", "reason": "step_up_required"}));
        assert_eq!(e, ApiError::Refused { status: 401, error: "unauthenticated".into(), reason: Some("step_up_required".into()), message: "m".into() });
        assert_eq!(refusal(403, &Value::Null), ApiError::Unauthorized);
        assert_eq!(refusal(502, &Value::Null), ApiError::Http(502));
        assert_eq!(refusal(401, &json!({"error": "unauthenticated", "message": ""})).code(), "unauthorized");
    }
}

/// Runs only when a gateway is given: ONEMIND_TEST_GATEWAY=http://127.0.0.1:8080 ONEMIND_TEST_TOKEN=...
/// `cargo test -- --ignored live_gateway`
#[cfg(test)]
mod live {
    #[test]
    #[ignore]
    fn live_gateway() {
        let (Ok(base), Ok(token)) = (std::env::var("ONEMIND_TEST_GATEWAY"), std::env::var("ONEMIND_TEST_TOKEN")) else { return };
        let st = tauri::async_runtime::block_on(async { super::status(&super::client(), "test", &base, &token).await });
        println!("{}", serde_json::to_string_pretty(&st).unwrap());
        assert!(st.reachable, "gateway not reachable: {:?}", st.error);
        let bad = tauri::async_runtime::block_on(async { super::status(&super::client(), "test", &base, "wrong-token").await });
        assert_eq!(bad.error.as_deref(), Some("unauthorized"));
    }
}
