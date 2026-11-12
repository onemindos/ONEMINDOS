// SPDX-License-Identifier: Apache-2.0
//! Gateway client: the routes in sdk/contracts/poc-v0.md §3, plus the §12 reads the tray uses
//! (`/v1/me`, `/v1/notifications`, `/v1/os/status`, `/v1/backups/status`). A §12 route exists
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

/// §12.13 `GET /v1/os/status`: one entry per node, the heartbeat `update` object plus
/// `available: {version, security} | null`. Older drafts nested it under `update`.
pub fn parse_updates(v: &Value) -> Updates {
    let nodes = items(v);
    let mut available = 0;
    let mut security = false;
    for n in &nodes {
        let u = n.get("update").unwrap_or(n);
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

/// Pending approvals only (§12.4 filter; older gateways ignore the query and send everything,
/// which `parse_pending` filters again).
pub const PENDING_PATH: &str = "/v1/actions?state=awaiting_approval&limit=50";
/// The newest unread inbox items (§12.14).
pub const INBOX_UNREAD_PATH: &str = "/v1/notifications?unread=true&limit=20";

pub async fn status(c: &reqwest::Client, box_id: &str, base: &str, token: &str) -> Status {
    let mut st = Status {
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
        fetched_at: now(),
    };
    let t = Some(token);
    let (inst, nodes, actions, upd, bk, me, ntf) = tokio::join!(
        get(c, base, t, "/v1/instance"),
        get(c, base, t, "/v1/nodes"),
        get(c, base, t, PENDING_PATH),
        get(c, base, t, "/v1/os/status"),
        get(c, base, t, "/v1/backups/status"),
        get(c, base, t, "/v1/me"),
        get(c, base, t, INBOX_UNREAD_PATH),
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
    fn backups_both_drafts() {
        assert_eq!(parse_backups(&json!({"health": "stale"})).health, "stale");
        assert_eq!(parse_backups(&json!({"box": {"state": "verified"}})).health, "verified");
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
