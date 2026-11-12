// SPDX-License-Identifier: Apache-2.0
//! The person's notifications inbox (contract §12.14 `GET /v1/notifications`) and the native
//! banners the tray raises from it and from pending approvals.
//!
//! Banner rules: one banner per new item, keyed so an approval announced by the inbox and by
//! the pending-actions list is announced once; at most `MAX_BANNERS` per refresh, the rest in
//! one summary; the unread backlog found when the app starts is one summary, not a flood. A
//! banner only informs. It never approves, and on desktop it carries no action buttons.

use serde::Serialize;
use serde_json::Value;
use std::collections::HashSet;

use crate::api::{self, Pending};

/// The newest items, read and unread, for the inbox view.
pub const LIST_PATH: &str = "/v1/notifications?limit=30";
pub const MAX_BANNERS: usize = 3;

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Item {
    pub id: String,
    /// `info | warning | critical`; anything else is read as `info`.
    pub severity: String,
    pub topic: Option<String>,
    pub title: String,
    /// Plain text, at most 4 KiB on the box; clipped further here.
    pub body: String,
    /// A path on the box's dashboard, e.g. `/approvals/<id>`. Opened only on the box's own origin.
    pub link: Option<String>,
    pub action_id: Option<String>,
    pub created_at: Option<String>,
    pub read_at: Option<String>,
}

pub fn parse(v: &Value) -> Vec<Item> {
    api::items(v)
        .iter()
        .filter_map(|n| {
            let id = api::s(n, "id").filter(|i| api::safe_id(i))?;
            Some(Item {
                id,
                severity: api::s(n, "severity")
                    .filter(|s| matches!(s.as_str(), "info" | "warning" | "critical"))
                    .unwrap_or_else(|| "info".into()),
                topic: api::s(n, "topic").map(|t| api::clip(&t, 80)),
                title: api::clip(&api::s(n, "title").unwrap_or_default(), 200),
                body: api::clip(&api::s(n, "body").unwrap_or_default(), 1000),
                link: api::s(n, "link").map(|l| api::clip(&l, 500)),
                action_id: api::s(n, "action_id").filter(|a| api::safe_id(a)),
                created_at: api::s(n, "created_at"),
                read_at: api::s(n, "read_at"),
            })
        })
        .collect()
}

#[derive(Debug, Clone, PartialEq)]
pub struct Banner {
    pub title: String,
    pub body: String,
}

fn approval_banner(box_name: &str, p: &Pending) -> Banner {
    let what = match &p.target {
        Some(t) => format!("{} {}", p.kind, t),
        None => p.kind.clone(),
    };
    let who = p.requested_by.as_deref().unwrap_or("someone");
    Banner {
        title: format!("Approval needed on {box_name}"),
        body: format!("{who} asks: {what}. Review it in OneMind."),
    }
}

fn item_banner(box_name: &str, it: &Item) -> Banner {
    let title = if it.title.is_empty() { "New notification".to_string() } else { it.title.clone() };
    let body = if it.body.is_empty() { "Open OneMind for details.".to_string() } else { api::clip(&it.body, 180) };
    Banner { title: format!("{box_name}: {title}"), body }
}

/// Banners for what is new since the last call. `seen` holds keys across calls and is pruned to
/// what is still pending or unread for this box. `quiet_backlog`: this is the first inbox read for
/// the box in this session, so its unread items go into the summary instead of one banner each.
pub fn banners(
    box_id: &str,
    box_name: &str,
    pending: &[Pending],
    inbox: Option<&[Item]>,
    seen: &mut HashSet<String>,
    quiet_backlog: bool,
) -> Vec<Banner> {
    let mut fresh = Vec::new();
    let mut live = HashSet::new();
    let mut quiet = 0usize;
    for p in pending {
        let key = format!("{box_id}/action/{}", p.id);
        live.insert(key.clone());
        if seen.insert(key) {
            fresh.push(approval_banner(box_name, p));
        }
    }
    for it in inbox.unwrap_or(&[]) {
        let key = match &it.action_id {
            Some(a) => format!("{box_id}/action/{a}"),
            None => format!("{box_id}/ntf/{}", it.id),
        };
        live.insert(key.clone());
        if seen.insert(key) {
            if quiet_backlog {
                quiet += 1;
            } else {
                fresh.push(item_banner(box_name, it));
            }
        }
    }
    let prefix = format!("{box_id}/");
    seen.retain(|k| !k.starts_with(&prefix) || live.contains(k));
    let more = fresh.len().saturating_sub(MAX_BANNERS) + quiet;
    fresh.truncate(MAX_BANNERS);
    if more > 0 {
        fresh.push(Banner {
            title: box_name.to_string(),
            body: format!("{more} more waiting. Open OneMind to see them."),
        });
    }
    fresh
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn pending(id: &str) -> Pending {
        Pending { id: id.into(), kind: "app.install".into(), target: Some("ntfy".into()), requested_by: Some("hermes".into()), expires_at: None, risk: None }
    }

    fn item(id: &str, action: Option<&str>) -> Item {
        Item { id: id.into(), severity: "info".into(), topic: None, title: format!("t{id}"), body: String::new(), link: None, action_id: action.map(Into::into), created_at: None, read_at: None }
    }

    #[test]
    fn parses_contract_items_and_drops_unsafe_ids() {
        let v = json!([
            {"id": "ntf_1", "severity": "critical", "topic": "backups", "title": "Backup failing", "body": "Disk full",
             "link": "/backups", "source": "backup", "created_at": "2026-11-12T09:00:00Z", "read_at": null},
            {"id": "ntf_2", "severity": "loud", "title": "x", "action_id": "../x"},
            {"id": "../../v1/tokens", "title": "bad"}
        ]);
        let items = parse(&v);
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].severity, "critical");
        assert_eq!(items[0].link.as_deref(), Some("/backups"));
        assert_eq!(items[1].severity, "info");
        assert_eq!(items[1].action_id, None);
    }

    #[test]
    fn one_banner_per_new_thing_and_approvals_once() {
        let mut seen = HashSet::new();
        let b = banners("box", "Home", &[pending("a1")], Some(&[item("n1", Some("a1")), item("n2", None)]), &mut seen, false);
        assert_eq!(b.len(), 2, "a1 once (pending and inbox), n2 once");
        assert!(b[0].title.contains("Approval needed on Home"));
        assert_eq!(b[1].title, "Home: tn2");
        assert!(banners("box", "Home", &[pending("a1")], Some(&[item("n1", Some("a1")), item("n2", None)]), &mut seen, false).is_empty());
    }

    #[test]
    fn backlog_at_start_is_one_summary_and_floods_are_capped() {
        let mut seen = HashSet::new();
        let backlog: Vec<Item> = (0..7).map(|i| item(&format!("n{i}"), None)).collect();
        let b = banners("box", "Home", &[], Some(&backlog), &mut seen, true);
        assert_eq!(b.len(), 1);
        assert!(b[0].body.starts_with("7 more"));
        let many: Vec<Pending> = (0..5).map(|i| pending(&format!("p{i}"))).collect();
        let b = banners("box", "Home", &many, Some(&backlog), &mut seen, false);
        assert_eq!(b.len(), MAX_BANNERS + 1);
        assert!(b[MAX_BANNERS].body.starts_with("2 more"));
    }

    #[test]
    fn seen_is_pruned_per_box() {
        let mut seen = HashSet::new();
        banners("box", "Home", &[pending("a1")], None, &mut seen, false);
        banners("other", "Lab", &[pending("a9")], None, &mut seen, false);
        banners("box", "Home", &[], None, &mut seen, false);
        assert!(!seen.contains("box/action/a1"));
        assert!(seen.contains("other/action/a9"));
    }
}
