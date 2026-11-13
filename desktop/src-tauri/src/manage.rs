// SPDX-License-Identifier: Apache-2.0
//! Box management from the tray: app lifecycle (contract §12.40), backups (§12.12) and the owner's
//! first-run preferences (§12.41).
//!
//! The rule is the approvals rule: **the tray only files a request.** A lifecycle request or a backup
//! run is created with `approve: false` (or no approve field at all), is bound to the plan hash the
//! person was shown, and then waits in the approval list for an owner. Nothing here approves, and a
//! backup restore is not offered at all (destructive, always needs a passkey; see approvals.rs).
//! Ids that come from the box go into URL paths only after `safe_app_id`.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::api::{self, ApiError};

/// §12.40 lifecycle types the tray files. `app.delete_data` stays on the dashboard.
pub const LIFECYCLE: [&str; 5] = ["app.start", "app.stop", "app.restart", "app.update", "app.remove"];
/// How long a request stays open for approval (same default as the dashboard and phone).
const REQUEST_TTL_SECS: u64 = 24 * 3600;

/// App ids are DNS-label slugs (§4 manifest): lower case, digits and hyphens, at most 59 characters.
pub fn safe_app_id(id: &str) -> bool {
    let b = id.as_bytes();
    !b.is_empty()
        && b.len() <= 59
        && b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
        && b[0] != b'-'
        && b[b.len() - 1] != b'-'
}

const BUSY: [&str; 7] = ["starting", "stopping", "restarting", "updating", "configuring", "deleting_data", "reverting"];

/// What can be asked for an app in this state. The box still checks (`policy_verdict: refused`).
pub fn lifecycle_options(installed: bool, status: &str) -> Vec<&'static str> {
    if !installed || BUSY.contains(&status) {
        return Vec::new();
    }
    if status == "stopped" {
        return vec!["app.start", "app.remove"];
    }
    vec!["app.stop", "app.restart", "app.update", "app.remove"]
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct AppRow {
    pub id: String,
    pub name: String,
    pub version: Option<String>,
    pub status: String,
    pub options: Vec<&'static str>,
}

/// Installed apps from `GET /v1/apps`, with the actions each one offers.
pub fn parse_apps(v: &Value) -> Vec<AppRow> {
    api::items(v)
        .iter()
        .filter(|a| a.get("installed").and_then(|x| x.as_bool()) == Some(true))
        .filter_map(|a| {
            let id = api::s(a, "id").filter(|i| safe_app_id(i))?;
            let status = api::s(a, "status").unwrap_or_else(|| "unknown".into());
            Some(AppRow {
                name: api::s(a, "name").map(|n| api::clip(&n, 80)).unwrap_or_else(|| id.clone()),
                version: api::s(a, "version"),
                options: lifecycle_options(true, &status),
                id,
                status,
            })
        })
        .collect()
}

/// `GET /v1/apps/{id}/plan?type=` (§12.40), reduced to what the confirmation card shows.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PlanView {
    pub app_id: String,
    pub kind: String,
    pub risk: Option<String>,
    /// `needs_approval` or `refused`.
    pub verdict: String,
    pub reason: Option<String>,
    pub summary: Option<String>,
    pub warnings: Vec<String>,
    pub from_version: Option<String>,
    pub to_version: Option<String>,
    pub volumes: usize,
    pub plan_sha256: Option<String>,
}

pub fn parse_plan(app_id: &str, kind: &str, v: &Value) -> PlanView {
    let p = v.get("plan").unwrap_or(&Value::Null);
    let warnings = p
        .get("warnings")
        .and_then(|w| w.as_array())
        .map(|w| w.iter().filter_map(|x| x.as_str()).map(|x| api::clip(x, 200)).take(10).collect())
        .unwrap_or_default();
    PlanView {
        app_id: app_id.to_string(),
        kind: kind.to_string(),
        risk: api::s(v, "risk"),
        verdict: api::s(v, "policy_verdict").unwrap_or_else(|| "needs_approval".into()),
        reason: api::s(v, "reason").map(|r| api::clip(&r, 300)),
        summary: api::s(p, "summary").map(|s| api::clip(&s, 500)),
        warnings,
        from_version: api::s(p, "from_version"),
        to_version: api::s(p, "to_version"),
        volumes: p.get("volumes").and_then(|x| x.as_array()).map_or(0, Vec::len),
        plan_sha256: api::s(v, "plan_sha256"),
    }
}

pub async fn preview(c: &reqwest::Client, base: &str, token: &str, app_id: &str, kind: &str) -> Result<PlanView, ApiError> {
    if !safe_app_id(app_id) || !LIFECYCLE.contains(&kind) {
        return Err(ApiError::BadResponse);
    }
    let v = api::get(c, base, Some(token), &format!("/v1/apps/{app_id}/plan?type={kind}"))
        .await?
        .ok_or(ApiError::Http(404))?;
    Ok(parse_plan(app_id, kind, &v))
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Filed {
    pub id: String,
    pub state: String,
}

/// RFC 3339 UTC from Unix seconds (civil-from-days), so no date crate is needed.
pub fn iso_utc(secs: u64) -> String {
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", rem / 3600, (rem % 3600) / 60, rem % 60)
}

/// A key that is unique per request: the same key returns the same action (§3), so a double click
/// cannot file two.
fn idempotency_key(prefix: &str) -> String {
    let ns = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    format!("desktop-{prefix}-{ns}")
}

/// File one lifecycle request, bound to the plan hash the card showed. Never approves.
pub fn lifecycle_body(app_id: &str, kind: &str, plan_sha256: &str, now_secs: u64, key: &str) -> Value {
    json!({
        "type": kind,
        "params": { "app_id": app_id },
        "idempotency_key": key,
        "expires_at": iso_utc(now_secs + REQUEST_TTL_SECS),
        "plan_sha256": plan_sha256,
    })
}

pub async fn request_lifecycle(c: &reqwest::Client, base: &str, token: &str, app_id: &str, kind: &str, plan_sha256: &str) -> Result<Filed, ApiError> {
    if !safe_app_id(app_id) || !LIFECYCLE.contains(&kind) || plan_sha256.is_empty() || plan_sha256.len() > 80 {
        return Err(ApiError::BadResponse);
    }
    let body = lifecycle_body(app_id, kind, plan_sha256, api::now(), &idempotency_key(kind));
    let v = api::post(c, base, token, "/v1/actions", &body).await?;
    Ok(filed(&v))
}

fn filed(v: &Value) -> Filed {
    Filed { id: api::s(v, "id").unwrap_or_default(), state: api::s(v, "state").unwrap_or_else(|| "awaiting_approval".into()) }
}

// ---- backups (§12.12) ----

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Dest {
    pub id: String,
    pub kind: String,
    pub label: String,
    pub primary: bool,
    pub state: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct RunRow {
    pub id: String,
    pub state: String,
    pub started_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Default)]
pub struct BackupView {
    pub health: String,
    pub last_success_at: Option<String>,
    pub last_verified_restore_at: Option<String>,
    pub next_run_at: Option<String>,
    pub copies: Option<u64>,
    pub destinations: Vec<Dest>,
    pub runs: Vec<RunRow>,
}

pub fn parse_destinations(v: &Value) -> Vec<Dest> {
    api::items(v)
        .iter()
        .filter_map(|d| {
            Some(Dest {
                id: api::s(d, "id")?,
                kind: api::s(d, "kind").unwrap_or_default(),
                label: api::clip(&api::s(d, "label").unwrap_or_default(), 80),
                primary: d.get("primary").and_then(|x| x.as_bool()).unwrap_or(false),
                state: api::s(d, "state"),
            })
        })
        .collect()
}

pub fn parse_runs(v: &Value) -> Vec<RunRow> {
    api::items(v)
        .iter()
        .filter_map(|r| Some(RunRow { id: api::s(r, "id")?, state: api::s(r, "state").unwrap_or_default(), started_at: api::s(r, "started_at") }))
        .take(5)
        .collect()
}

pub fn parse_backup_view(status: &Value, dests: Option<&Value>, runs: Option<&Value>) -> BackupView {
    BackupView {
        health: api::s(status, "health").unwrap_or_else(|| "unknown".into()),
        last_success_at: api::s(status, "last_success_at"),
        last_verified_restore_at: api::s(status, "last_verified_restore_at"),
        next_run_at: api::s(status, "next_run_at"),
        copies: status.get("copies").and_then(|x| x.as_u64()),
        destinations: dests.map(parse_destinations).unwrap_or_default(),
        runs: runs.map(parse_runs).unwrap_or_default(),
    }
}

pub async fn backups(c: &reqwest::Client, base: &str, token: &str) -> Result<Option<BackupView>, ApiError> {
    let t = Some(token);
    let (s, d, r) = tokio::join!(api::get(c, base, t, "/v1/backups/status"), api::get(c, base, t, "/v1/backups/destinations"), api::get(c, base, t, "/v1/backups/runs"));
    let Some(status) = s? else { return Ok(None) };
    // Destinations and runs are optional extras: a 403 or 404 on them leaves the lists empty.
    Ok(Some(parse_backup_view(&status, d.ok().flatten().as_ref(), r.ok().flatten().as_ref())))
}

/// Body of `POST /v1/backups/runs` and `/verify`: a request, never an approval.
pub fn backup_body(kind: &str) -> Option<(&'static str, Value)> {
    match kind {
        "run" => Some(("/v1/backups/runs", json!({ "scope": "box", "reason": "Requested from the desktop app", "approve": false }))),
        "verify" => Some(("/v1/backups/verify", json!({ "reason": "Requested from the desktop app", "approve": false }))),
        _ => None,
    }
}

pub async fn request_backup(c: &reqwest::Client, base: &str, token: &str, kind: &str) -> Result<Filed, ApiError> {
    let (path, body) = backup_body(kind).ok_or(ApiError::BadResponse)?;
    let resp = c
        .post(format!("{base}{path}"))
        .bearer_auth(token)
        .header("idempotency-key", idempotency_key(kind))
        .json(&body)
        .send()
        .await
        .map_err(|_| ApiError::Unreachable)?;
    let status = resp.status().as_u16();
    let v: Value = resp.json().await.unwrap_or(Value::Null);
    if (200..300).contains(&status) {
        return Ok(filed(&v));
    }
    Err(api::refusal(status, &v))
}

// ---- first-run settings (§12.41), owner only ----

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SettingsBody {
    pub box_name: String,
    pub time_zone: String,
    /// `usb | peer | s3 | later`.
    pub backup_choice: String,
    pub backup_destination_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Settings {
    pub box_name: Option<String>,
    pub time_zone: Option<String>,
    pub backup_choice: String,
    pub backup_destination_id: Option<String>,
    pub saved: bool,
    pub destinations: Vec<Dest>,
}

pub fn parse_settings(v: &Value, dests: Vec<Dest>) -> Settings {
    Settings {
        box_name: api::s(v, "box_name"),
        time_zone: api::s(v, "time_zone"),
        backup_choice: api::s(v, "backup_choice").unwrap_or_else(|| "later".into()),
        backup_destination_id: api::s(v, "backup_destination_id"),
        saved: v.get("saved").and_then(|x| x.as_bool()).unwrap_or(false),
        destinations: dests,
    }
}

/// Lower-case RFC 1123 label, 1 to 63 characters, no leading or trailing hyphen.
pub fn valid_box_name(n: &str) -> bool {
    let b = n.as_bytes();
    !b.is_empty()
        && b.len() <= 63
        && b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
        && b[0] != b'-'
        && b[b.len() - 1] != b'-'
}

fn kind_for(choice: &str) -> Option<&'static str> {
    match choice {
        "usb" => Some("usb"),
        "peer" => Some("box"),
        "s3" => Some("s3"),
        _ => None,
    }
}

/// What can be seen wrong before anything is sent; the box validates again and writes nothing on a refusal.
pub fn settings_problem(b: &SettingsBody, dests: &[Dest]) -> Option<&'static str> {
    if !valid_box_name(&b.box_name) {
        return Some("invalid_box_name");
    }
    let z = b.time_zone.trim();
    if z.is_empty() || z.len() > 128 || z.starts_with('/') || z.chars().any(char::is_whitespace) {
        return Some("invalid_time_zone");
    }
    if !matches!(b.backup_choice.as_str(), "usb" | "peer" | "s3" | "later") {
        return Some("invalid_backup_choice");
    }
    match (&b.backup_destination_id, kind_for(&b.backup_choice)) {
        (None, _) => None,
        (Some(_), None) => Some("destination_not_allowed"),
        (Some(id), Some(kind)) => (!dests.iter().any(|d| &d.id == id && d.kind == kind)).then_some("destination_mismatch"),
    }
}

pub async fn settings(c: &reqwest::Client, base: &str, token: &str) -> Result<Option<Settings>, ApiError> {
    let t = Some(token);
    let (s, d) = tokio::join!(api::get(c, base, t, "/v1/onboarding/settings"), api::get(c, base, t, "/v1/backups/destinations"));
    let Some(v) = s? else { return Ok(None) };
    Ok(Some(parse_settings(&v, d.ok().flatten().as_ref().map(parse_destinations).unwrap_or_default())))
}

/// Full replacement. The box answers 403 to anyone but an owner person and writes nothing on a refusal.
pub async fn save_settings(c: &reqwest::Client, base: &str, token: &str, body: &SettingsBody) -> Result<Settings, ApiError> {
    let dests = api::get(c, base, Some(token), "/v1/backups/destinations").await.ok().flatten().as_ref().map(parse_destinations).unwrap_or_default();
    if let Some(p) = settings_problem(body, &dests) {
        return Err(ApiError::Refused { status: 422, error: p.into(), reason: None, message: String::new() });
    }
    let resp = c
        .put(format!("{base}/v1/onboarding/settings"))
        .bearer_auth(token)
        .json(body)
        .send()
        .await
        .map_err(|_| ApiError::Unreachable)?;
    let status = resp.status().as_u16();
    let v: Value = resp.json().await.unwrap_or(Value::Null);
    if (200..300).contains(&status) {
        return Ok(parse_settings(&v, dests));
    }
    Err(api::refusal(status, &v))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_ids_are_slugs() {
        assert!(safe_app_id("uptime-kuma"));
        for bad in ["", "-a", "a-", "A", "a/b", "..", "a b", "a?x=1", &"x".repeat(60)] {
            assert!(!safe_app_id(bad), "{bad}");
        }
    }

    #[test]
    fn options_follow_the_status() {
        assert_eq!(lifecycle_options(true, "installed"), vec!["app.stop", "app.restart", "app.update", "app.remove"]);
        assert_eq!(lifecycle_options(true, "stopped"), vec!["app.start", "app.remove"]);
        assert!(lifecycle_options(true, "updating").is_empty());
        assert!(lifecycle_options(false, "not_installed").is_empty());
        assert!(!LIFECYCLE.contains(&"app.delete_data"), "delete-data stays on the dashboard");
    }

    #[test]
    fn apps_keep_installed_ones_with_safe_ids() {
        let v = json!([
            {"id": "ollama", "name": "Ollama", "version": "0.5", "installed": true, "status": "installed"},
            {"id": "jellyfin", "installed": false, "status": "not_installed"},
            {"id": "../../v1/tokens", "installed": true, "status": "installed"}
        ]);
        let a = parse_apps(&v);
        assert_eq!(a.len(), 1);
        assert_eq!(a[0].id, "ollama");
        assert_eq!(a[0].options.len(), 4);
    }

    #[test]
    fn plan_preview_is_read_from_the_contract_shape() {
        let v = json!({"type": "app.update", "app_id": "ollama", "risk": "write", "policy_verdict": "needs_approval",
            "plan": {"summary": "Update ollama", "warnings": ["Down for a minute"], "from_version": "0.5", "to_version": "0.6", "volumes": [{}, {}]},
            "plan_sha256": "sha256:abc"});
        let p = parse_plan("ollama", "app.update", &v);
        assert_eq!((p.verdict.as_str(), p.volumes), ("needs_approval", 2));
        assert_eq!(p.to_version.as_deref(), Some("0.6"));
        assert_eq!(p.warnings, vec!["Down for a minute".to_string()]);
        assert_eq!(parse_plan("a", "app.stop", &json!({"policy_verdict": "refused", "reason": "already stopped"})).reason.as_deref(), Some("already stopped"));
    }

    #[test]
    fn a_lifecycle_request_carries_the_plan_hash_and_never_approves() {
        let b = lifecycle_body("ollama", "app.restart", "sha256:abc", 0, "k1");
        assert_eq!(b["type"], "app.restart");
        assert_eq!(b["params"], json!({"app_id": "ollama"}));
        assert_eq!(b["plan_sha256"], "sha256:abc");
        assert_eq!(b["expires_at"], "1970-01-02T00:00:00Z");
        assert!(b.get("approve").is_none());
    }

    #[test]
    fn iso_dates() {
        assert_eq!(iso_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(iso_utc(951_782_400), "2000-02-29T00:00:00Z");
        assert_eq!(iso_utc(1_794_000_000 + 3 * 3600 + 4 * 60 + 5), "2026-11-07T00:24:05Z");
    }

    #[test]
    fn backup_requests_never_approve() {
        for k in ["run", "verify"] {
            let (path, body) = backup_body(k).unwrap();
            assert!(path.starts_with("/v1/backups/"));
            assert_eq!(body["approve"], json!(false));
        }
        assert!(backup_body("restore").is_none(), "restore is not offered from the tray");
    }

    #[test]
    fn backup_view_reads_status_destinations_and_runs() {
        let s = json!({"health": "ok", "last_success_at": "2026-11-13T01:00:00Z", "copies": 2});
        let d = json!([{"id": "dst_1", "kind": "usb", "label": "Blue disk", "primary": true, "state": "online"}]);
        let r = json!([{"id": "run1", "state": "succeeded", "started_at": "2026-11-13T01:00:00Z"}]);
        let v = parse_backup_view(&s, Some(&d), Some(&r));
        assert_eq!((v.health.as_str(), v.copies, v.destinations.len(), v.runs.len()), ("ok", Some(2), 1, 1));
        assert_eq!(parse_backup_view(&json!({}), None, None).health, "unknown");
    }

    fn dests() -> Vec<Dest> {
        vec![
            Dest { id: "dst_1".into(), kind: "usb".into(), label: "USB".into(), primary: true, state: None },
            Dest { id: "dst_2".into(), kind: "box".into(), label: "Peer".into(), primary: false, state: None },
        ]
    }
    fn body() -> SettingsBody {
        SettingsBody { box_name: "home".into(), time_zone: "Europe/Berlin".into(), backup_choice: "usb".into(), backup_destination_id: Some("dst_1".into()) }
    }

    #[test]
    fn settings_checks_before_sending() {
        assert_eq!(settings_problem(&body(), &dests()), None);
        assert_eq!(settings_problem(&SettingsBody { box_name: "Home".into(), ..body() }, &dests()), Some("invalid_box_name"));
        assert_eq!(settings_problem(&SettingsBody { time_zone: "/etc/localtime".into(), ..body() }, &dests()), Some("invalid_time_zone"));
        assert_eq!(settings_problem(&SettingsBody { backup_choice: "s3".into(), ..body() }, &dests()), Some("destination_mismatch"));
        assert_eq!(settings_problem(&SettingsBody { backup_choice: "later".into(), ..body() }, &dests()), Some("destination_not_allowed"));
        assert_eq!(settings_problem(&SettingsBody { backup_choice: "peer".into(), backup_destination_id: Some("dst_2".into()), ..body() }, &dests()), None);
        assert_eq!(settings_problem(&SettingsBody { backup_choice: "later".into(), backup_destination_id: None, ..body() }, &[]), None);
        assert!(valid_box_name("a") && !valid_box_name("-a") && !valid_box_name(&"x".repeat(64)));
    }

    #[test]
    fn settings_before_the_first_save() {
        let s = parse_settings(&json!({"box_name": null, "time_zone": null, "backup_choice": "later", "backup_destination_id": null, "saved": false}), vec![]);
        assert_eq!((s.box_name, s.saved, s.backup_choice.as_str()), (None, false, "later"));
    }
}
