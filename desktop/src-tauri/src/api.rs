// SPDX-License-Identifier: Apache-2.0
//! Gateway client: the routes in sdk/contracts/poc-v0.md §3, plus two planned read routes
//! (`/v1/os/updates`, `/v1/backups/status`) that a box may not serve yet. A 404 on a planned
//! route is shown as "not reported by this box", never as an error and never as "all good".

use serde::Serialize;
use serde_json::Value;
use std::time::Duration;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ApiError {
    /// 401: the token was not accepted.
    Unauthorized,
    /// Connection refused, DNS failure, TLS failure or timeout.
    Unreachable,
    Http(u16),
    BadResponse,
}

impl ApiError {
    pub fn code(&self) -> String {
        match self {
            ApiError::Unauthorized => "unauthorized".into(),
            ApiError::Unreachable => "unreachable".into(),
            ApiError::Http(s) => format!("http_{s}"),
            ApiError::BadResponse => "bad_response".into(),
        }
    }
}

pub fn client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(6))
        .connect_timeout(Duration::from_secs(3))
        .user_agent(concat!("onemind-desktop/", env!("CARGO_PKG_VERSION")))
        // Never follow a redirect with the bearer token to another host.
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("http client")
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

#[derive(Debug, Clone, Serialize)]
pub struct Pending {
    pub id: String,
    pub kind: String,
    pub target: Option<String>,
    pub requested_by: Option<String>,
    pub expires_at: Option<String>,
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
    /// Unix seconds when this was read, so the UI can say "from 3 min ago".
    pub fetched_at: u64,
}

fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn s(v: &Value, k: &str) -> Option<String> {
    v.get(k).and_then(|x| x.as_str()).map(str::to_string)
}

/// Accept a bare array or `{ "items": [...] }` / `{ "nodes": [...] }`.
fn items(v: &Value) -> Vec<Value> {
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

pub fn parse_pending(actions: &Value) -> Vec<Pending> {
    items(actions)
        .iter()
        .filter(|a| a.get("state").and_then(|x| x.as_str()) == Some("awaiting_approval"))
        .map(|a| Pending {
            id: s(a, "id").unwrap_or_default(),
            kind: s(a, "type").unwrap_or_else(|| "action".into()),
            target: a.get("params").and_then(|p| s(p, "app_id").or_else(|| s(p, "node_id"))),
            requested_by: s(a, "requested_by")
                .or_else(|| a.get("requested_by").and_then(|r| s(r, "id")))
                .or_else(|| s(a, "principal_id")),
            expires_at: s(a, "expires_at"),
        })
        .collect()
}

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
        fetched_at: now(),
    };
    let t = Some(token);
    let (inst, nodes, actions, upd, bk) = tokio::join!(
        get(c, base, t, "/v1/instance"),
        get(c, base, t, "/v1/nodes"),
        get(c, base, t, "/v1/actions"),
        get(c, base, t, "/v1/os/updates"),
        get(c, base, t, "/v1/backups/status"),
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
    fn updates_counts_available() {
        let v = json!([{"node_id": "n1", "update": {"available": {"version": "0.2.0", "security": true}}}, {"node_id": "n2", "update": {"available": null}}]);
        let u = parse_updates(&v);
        assert_eq!((u.nodes_reporting, u.available, u.security), (2, 1, true));
    }

    #[test]
    fn backups_both_drafts() {
        assert_eq!(parse_backups(&json!({"health": "stale"})).health, "stale");
        assert_eq!(parse_backups(&json!({"box": {"state": "verified"}})).health, "verified");
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
