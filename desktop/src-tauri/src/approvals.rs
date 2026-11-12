// SPDX-License-Identifier: Apache-2.0
//! Approvals from the tray (UMB-CLIENT-10; contract §12.3 risk classes and step-up, §12.4).
//!
//! Three rules:
//! 1. **Approve only what the owner saw.** The card carries the plan hash it showed. Before
//!    approving, the action is read again; if its plan hash differs, nothing is approved. The
//!    hash is also sent with the approval, so the box refuses a plan that changed in between
//!    (`409 stale_precondition`, reason `plan_changed`).
//! 2. **A notification never approves.** Only the card's Approve button does, after a confirm.
//! 3. **Passkey step-up (F-2) happens in the browser.** A WebAuthn assertion is bound to the web
//!    origin that asked for it, and the box only accepts its own origin (`https://<box>`). The
//!    tray's web view runs on the app's origin, so it cannot produce an assertion the box would
//!    accept. When an approval needs a passkey (risk `destructive`/`actuate`, the owner has a
//!    passkey, or the box answers `step_up_required`), the tray opens the box's approvals page in
//!    the system browser, where the passkey prompt is bound to the right origin. Native platform
//!    passkeys (Touch ID / Windows Hello through the OS APIs) are the DESK-S2 follow-up.

use serde::Serialize;
use serde_json::{json, Value};

use crate::api::{self, ApiError};

/// The dashboard page where the owner finishes an approval that needs a passkey.
pub const BROWSER_PATH: &str = "/approvals";
const LIST_MAX: usize = 20;
const PARAMS_MAX_BYTES: usize = 16 * 1024;

/// `GET /v1/me` (§12.6), the parts the tray uses.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Me {
    pub id: Option<String>,
    pub kind: Option<String>,
    pub role: Option<String>,
    /// Passkeys of this principal. Above zero, every owner approval needs one (F-2).
    pub passkeys: u64,
    pub can_approve: Option<bool>,
}

pub fn parse_me(v: &Value) -> Me {
    let p = v.get("principal").unwrap_or(&Value::Null);
    Me {
        id: api::s(p, "id"),
        kind: api::s(p, "kind"),
        role: api::s(p, "role"),
        passkeys: v.get("passkeys").and_then(|x| x.as_u64()).unwrap_or(0),
        can_approve: v
            .get("capabilities")
            .and_then(|c| c.as_array())
            .map(|c| c.iter().any(|x| x.as_str() == Some("can_approve"))),
    }
}

/// The §12.4 plan, reduced to what fits a tray card. Lists are capped; counts are exact.
#[derive(Debug, Clone, Serialize, Default, PartialEq)]
pub struct Plan {
    pub summary: Option<String>,
    pub warnings: Vec<String>,
    pub images: Vec<String>,
    pub volumes: usize,
    pub nodes: Vec<String>,
    pub objects: usize,
}

/// Each entry is a string, or an object whose first present key of `keys` is a string.
fn strings(v: Option<&Value>, keys: &[&str]) -> Vec<String> {
    let Some(a) = v.and_then(|x| x.as_array()) else { return Vec::new() };
    a.iter()
        .filter_map(|e| e.as_str().map(str::to_string).or_else(|| keys.iter().find_map(|k| api::s(e, k))))
        .map(|s| api::clip(&s, 200))
        .take(LIST_MAX)
        .collect()
}

fn count(v: &Value, k: &str) -> usize {
    v.get(k).and_then(|x| x.as_array()).map_or(0, Vec::len)
}

pub fn parse_plan(v: &Value) -> Plan {
    Plan {
        summary: api::s(v, "summary").map(|s| api::clip(&s, 500)),
        warnings: strings(v.get("warnings"), &["message", "text", "summary"]),
        images: strings(v.get("images"), &["ref", "image", "name"]),
        volumes: count(v, "volumes"),
        nodes: strings(v.get("nodes"), &["node_id", "id", "name"]),
        objects: count(v, "objects"),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Detail {
    pub box_id: String,
    pub id: String,
    pub kind: String,
    pub state: String,
    pub risk: Option<String>,
    pub target: Option<String>,
    pub requested_by: Option<String>,
    /// `person`, `agent`, `plugin`, `automation` or `node` when the box says so (§12.1).
    pub requester_kind: Option<String>,
    /// The requester's own words. An agent's reason is shown as unchecked.
    pub reason: Option<String>,
    pub expires_at: Option<String>,
    pub params: Value,
    pub plan: Option<Plan>,
    pub plan_sha256: Option<String>,
    /// Why this approval needs a passkey, if it does: `risk` or `owner_passkey`.
    pub passkey: Option<String>,
}

fn requester_kind(a: &Value) -> Option<String> {
    a.get("requested_by").and_then(|r| api::s(r, "kind")).or_else(|| {
        let id = api::requester(a)?;
        let (kind, _) = id.split_once(':')?;
        ["person", "agent", "plugin", "automation", "node"].contains(&kind).then(|| kind.to_string())
    })
}

/// The plan hash the box binds the approval to: the preview's, else the action's own field.
fn plan_sha(a: &Value, preview: Option<&Value>) -> Option<String> {
    preview.and_then(|p| api::s(p, "plan_sha256")).or_else(|| api::s(a, "plan_sha256"))
}

/// F-2 and §12.3: `destructive` and `actuate` always need a passkey; every owner approval
/// needs one once the owner has a passkey.
pub fn needs_passkey(risk: Option<&str>, me: Option<&Me>) -> Option<&'static str> {
    if matches!(risk, Some("destructive" | "actuate")) {
        return Some("risk");
    }
    if me.is_some_and(|m| m.passkeys > 0) {
        return Some("owner_passkey");
    }
    None
}

pub fn build_detail(box_id: &str, a: &Value, preview: Option<&Value>, me: Option<&Me>) -> Detail {
    let plan = preview
        .and_then(|p| p.get("plan"))
        .or_else(|| a.get("plan"))
        .filter(|p| p.is_object())
        .map(parse_plan);
    let mut params = a.get("params").cloned().unwrap_or(Value::Null);
    let size = params.to_string().len();
    if size > PARAMS_MAX_BYTES {
        params = Value::String(format!("(settings too large to show here: {size} bytes; open the dashboard)"));
    }
    let risk = api::s(a, "risk");
    Detail {
        box_id: box_id.to_string(),
        id: api::s(a, "id").unwrap_or_default(),
        kind: api::s(a, "type").unwrap_or_else(|| "action".into()),
        state: api::s(a, "state").unwrap_or_else(|| "unknown".into()),
        passkey: needs_passkey(risk.as_deref(), me).map(str::to_string),
        risk,
        target: api::target(a),
        requested_by: api::requester(a),
        requester_kind: requester_kind(a),
        reason: api::s(a, "reason").map(|r| api::clip(&r, 500)),
        expires_at: api::s(a, "expires_at"),
        params,
        plan,
        plan_sha256: plan_sha(a, preview),
    }
}

pub async fn detail(c: &reqwest::Client, base: &str, token: &str, box_id: &str, id: &str, me: Option<&Me>) -> Result<Detail, ApiError> {
    let (a, preview) = read(c, base, token, id).await?;
    Ok(build_detail(box_id, &a, preview.as_ref(), me))
}

/// The action and its preview (`GET /v1/actions/{id}/preview`, absent on older boxes).
async fn read(c: &reqwest::Client, base: &str, token: &str, id: &str) -> Result<(Value, Option<Value>), ApiError> {
    let t = Some(token);
    let action_path = format!("/v1/actions/{id}");
    let preview_path = format!("/v1/actions/{id}/preview");
    let (a, p) = tokio::join!(api::get(c, base, t, &action_path), api::get(c, base, t, &preview_path));
    let a = a?.ok_or(ApiError::Http(404))?;
    Ok((a, p.ok().flatten()))
}

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum Outcome {
    /// The box took the decision. `approval` is `passkey`, `token`, … as the box records it.
    Done { state: String, approval: Option<String> },
    /// The owner finishes this approval in the browser, with a passkey. Nothing was approved.
    Browser { why: String },
    /// The plan changed after the card was shown. Nothing was approved.
    PlanChanged,
    /// The action is no longer waiting (approved elsewhere, denied, expired, cancelled).
    NotPending { state: String },
    Refused { code: String, message: String },
}

/// What a refused approve or deny means for the person at the tray.
pub fn after_refusal(e: &ApiError) -> Outcome {
    match e {
        ApiError::Refused { reason: Some(r), .. } if r == "step_up_required" => Outcome::Browser { why: "step_up".into() },
        ApiError::Refused { reason: Some(r), .. } if r == "plan_unchecked" => Outcome::Browser { why: "plan_unchecked".into() },
        ApiError::Refused { reason: Some(r), .. } if r == "plan_changed" => Outcome::PlanChanged,
        ApiError::Refused { error, message, .. } => Outcome::Refused { code: error.clone(), message: message.clone() },
        other => Outcome::Refused { code: other.code(), message: String::new() },
    }
}

/// The checks made before anything is sent. `None` means: go ahead and send the approval.
pub fn pre_approve(state: &str, seen_plan: Option<&str>, current_plan: Option<&str>, risk: Option<&str>, me: Option<&Me>) -> Option<Outcome> {
    if state != "awaiting_approval" {
        return Some(Outcome::NotPending { state: state.to_string() });
    }
    if seen_plan != current_plan {
        return Some(Outcome::PlanChanged);
    }
    needs_passkey(risk, me).map(|why| Outcome::Browser { why: why.into() })
}

/// Approve or deny one action. `seen_plan` is the plan hash the card showed (or none, when the
/// box sent no plan). The caller has checked `id` with `api::safe_id`.
#[allow(clippy::too_many_arguments)]
pub async fn decide(
    c: &reqwest::Client,
    base: &str,
    token: &str,
    id: &str,
    decision: &str,
    seen_plan: Option<&str>,
    reason: Option<&str>,
    me: Option<&Me>,
) -> Result<Outcome, ApiError> {
    let (a, preview) = match read(c, base, token, id).await {
        Ok(x) => x,
        Err(ApiError::Http(404)) => return Ok(Outcome::NotPending { state: "gone".into() }),
        Err(e) => return Err(e),
    };
    let state = api::s(&a, "state").unwrap_or_default();
    let (path, body) = match decision {
        "deny" => {
            if state != "awaiting_approval" {
                return Ok(Outcome::NotPending { state });
            }
            let body = match reason.map(str::trim).filter(|r| !r.is_empty()) {
                Some(r) => json!({ "reason": api::clip(r, 500) }),
                None => json!({}),
            };
            (format!("/v1/actions/{id}/deny"), body)
        }
        "approve" => {
            let current = plan_sha(&a, preview.as_ref());
            if let Some(stop) = pre_approve(&state, seen_plan, current.as_deref(), api::s(&a, "risk").as_deref(), me) {
                return Ok(stop);
            }
            let body = match current {
                Some(h) => json!({ "plan_sha256": h }),
                None => json!({}),
            };
            (format!("/v1/actions/{id}/approve"), body)
        }
        _ => return Ok(Outcome::Refused { code: "invalid_decision".into(), message: String::new() }),
    };
    Ok(match api::post(c, base, token, &path, &body).await {
        Ok(v) => Outcome::Done {
            state: api::s(&v, "state").unwrap_or_else(|| if decision == "deny" { "denied".into() } else { "accepted".into() }),
            approval: api::s(&v, "approval"),
        },
        Err(e) => after_refusal(&e),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn me(passkeys: u64) -> Me {
        Me { id: Some("person:owner".into()), kind: Some("person".into()), role: Some("owner".into()), passkeys, can_approve: Some(true) }
    }

    #[test]
    fn me_from_contract_shape() {
        let m = parse_me(&json!({"principal": {"id": "person:ana", "kind": "person", "role": "owner"}, "passkeys": 2, "capabilities": ["can_approve"]}));
        assert_eq!(m, Me { id: Some("person:ana".into()), kind: Some("person".into()), role: Some("owner".into()), passkeys: 2, can_approve: Some(true) });
        assert_eq!(parse_me(&json!({})).passkeys, 0);
    }

    #[test]
    fn passkey_rule() {
        assert_eq!(needs_passkey(Some("destructive"), None), Some("risk"));
        assert_eq!(needs_passkey(Some("actuate"), Some(&me(0))), Some("risk"));
        assert_eq!(needs_passkey(Some("sensitive"), Some(&me(1))), Some("owner_passkey"));
        assert_eq!(needs_passkey(Some("write"), Some(&me(0))), None);
        assert_eq!(needs_passkey(None, None), None);
    }

    #[test]
    fn approve_only_the_plan_that_was_shown() {
        assert_eq!(pre_approve("awaiting_approval", Some("sha256:a"), Some("sha256:a"), Some("sensitive"), None), None);
        assert_eq!(pre_approve("awaiting_approval", Some("sha256:a"), Some("sha256:b"), None, None), Some(Outcome::PlanChanged));
        // A plan appearing (or vanishing) after the card was shown is a change too.
        assert_eq!(pre_approve("awaiting_approval", None, Some("sha256:b"), None, None), Some(Outcome::PlanChanged));
        assert_eq!(pre_approve("awaiting_approval", Some("sha256:a"), None, None, None), Some(Outcome::PlanChanged));
        assert_eq!(pre_approve("accepted", Some("x"), Some("x"), None, None), Some(Outcome::NotPending { state: "accepted".into() }));
        assert_eq!(pre_approve("awaiting_approval", None, None, Some("destructive"), None), Some(Outcome::Browser { why: "risk".into() }));
    }

    #[test]
    fn refusals_map_to_plain_outcomes() {
        let r = |status, error: &str, reason: Option<&str>| ApiError::Refused { status, error: error.into(), reason: reason.map(Into::into), message: "m".into() };
        assert_eq!(after_refusal(&r(401, "unauthenticated", Some("step_up_required"))), Outcome::Browser { why: "step_up".into() });
        assert_eq!(after_refusal(&r(409, "stale_precondition", Some("plan_changed"))), Outcome::PlanChanged);
        assert_eq!(after_refusal(&r(409, "stale_precondition", Some("plan_unchecked"))), Outcome::Browser { why: "plan_unchecked".into() });
        assert_eq!(after_refusal(&r(403, "permission_denied", None)), Outcome::Refused { code: "permission_denied".into(), message: "m".into() });
        assert_eq!(after_refusal(&ApiError::Unreachable), Outcome::Refused { code: "unreachable".into(), message: String::new() });
    }

    #[test]
    fn detail_reads_v12_action_and_preview() {
        let a = json!({"id": "6f1c", "type": "backup.restore", "state": "awaiting_approval", "risk": "destructive",
            "reason": "data corrupted since 02:00", "requested_by": {"id": "agent:hermes-agent", "kind": "agent"},
            "params": {"snapshot_id": "snap_01J", "scope": {"app_id": "vaultwarden"}}, "expires_at": "2026-11-13T00:00:00Z",
            "plan_sha256": "sha256:old"});
        let p = json!({"plan": {"summary": "Restore vaultwarden", "warnings": ["Downtime about 1 minute"], "images": [{"ref": "vw:1.32"}],
            "volumes": [{}, {}], "nodes": ["3f9c"], "objects": [{}, {}, {}]}, "plan_sha256": "sha256:new"});
        let d = build_detail("box1", &a, Some(&p), None);
        assert_eq!(d.requester_kind.as_deref(), Some("agent"));
        assert_eq!(d.passkey.as_deref(), Some("risk"));
        assert_eq!(d.plan_sha256.as_deref(), Some("sha256:new"), "the preview's hash is what the card shows");
        let plan = d.plan.unwrap();
        assert_eq!((plan.volumes, plan.objects), (2, 3));
        assert_eq!(plan.images, vec!["vw:1.32".to_string()]);
        assert_eq!(plan.warnings, vec!["Downtime about 1 minute".to_string()]);
    }

    #[test]
    fn detail_of_a_v0_action() {
        let a = json!({"id": "a1", "type": "app.install", "state": "awaiting_approval", "params": {"app_id": "ntfy"}, "requested_by": "hermes"});
        let d = build_detail("box1", &a, None, Some(&me(0)));
        assert!(d.plan.is_none() && d.plan_sha256.is_none() && d.risk.is_none() && d.passkey.is_none());
        assert_eq!(d.requester_kind, None);
        assert_eq!(d.target.as_deref(), Some("ntfy"));
        let big = json!({"id": "a2", "type": "app.configure", "state": "awaiting_approval", "params": {"blob": "x".repeat(20_000)}});
        assert!(build_detail("box1", &big, None, None).params.is_string());
    }
}
