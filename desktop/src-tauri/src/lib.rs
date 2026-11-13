// SPDX-License-Identifier: Apache-2.0
//! OneMind desktop client v1: a menu-bar / tray app that finds boxes, pairs with a token kept in
//! the OS keychain, shows box status, raises native notifications from the person's inbox and
//! from pending approvals, follows the box's live event stream, and lets the owner approve or
//! deny a request after seeing its exact plan. Approvals that need a passkey finish in the
//! browser on the box's own page (approvals.rs explains why). A notification never approves.

mod address;
mod api;
mod approvals;
mod discovery;
mod events;
mod inbox;
mod manage;
mod store;

use serde::Serialize;
use serde_json::json;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, Rect, State, WebviewWindow, WindowEvent};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_opener::OpenerExt;

const POLL: Duration = Duration::from_secs(20);
/// At most one event-triggered refresh per box per second.
const WAKE_GAP: Duration = Duration::from_secs(1);

struct App {
    store: store::Store,
    http: reqwest::Client,
    last: Mutex<HashMap<String, api::Status>>,
    /// Keys of what a banner was already raised for (inbox::banners).
    notified: Mutex<HashSet<String>>,
    /// Boxes whose inbox was read once this session (the start-up backlog is one summary).
    inbox_primed: Mutex<HashSet<String>>,
    /// Boxes with a live `/v1/events` stream right now.
    live: Mutex<HashSet<String>>,
    followers: Mutex<HashMap<String, tauri::async_runtime::JoinHandle<()>>>,
    /// One refresh at a time per box, so a slow poll cannot overwrite the newer status an event
    /// just fetched (and so banner bookkeeping always sees statuses in order).
    refreshing: Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>,
}

#[derive(Serialize)]
struct BoxView {
    #[serde(flatten)]
    saved: store::SavedBox,
    has_token: bool,
    /// True while the box's event stream is open (updates arrive within seconds).
    live: bool,
    status: Option<api::Status>,
}

/// A saved box and its keychain token, or the error code the UI explains.
fn box_and_token(app: &App, id: &str) -> Result<(store::SavedBox, String), String> {
    let b = app.store.get(id).ok_or("unknown_box")?;
    let t = store::token(&b.id).ok_or("token_missing")?;
    Ok((b, t))
}

fn me_of(app: &App, id: &str) -> Option<approvals::Me> {
    app.last.lock().unwrap().get(id).and_then(|s| s.me.clone())
}

// ---- commands (the only things the web view can call) ----

#[tauri::command]
fn list_boxes(app: State<'_, App>) -> Vec<BoxView> {
    let last = app.last.lock().unwrap();
    let live = app.live.lock().unwrap();
    app.store
        .list()
        .into_iter()
        .map(|b| BoxView {
            has_token: store::token(&b.id).is_some(),
            live: live.contains(&b.id),
            status: last.get(&b.id).cloned(),
            saved: b,
        })
        .collect()
}

#[tauri::command]
async fn discover(app: State<'_, App>) -> Result<Vec<discovery::Found>, String> {
    let mut found = tauri::async_runtime::spawn_blocking(|| discovery::browse(Duration::from_millis(2500)))
        .await
        .unwrap_or_default();
    if !found.iter().any(|f| f.url.contains(discovery::WELL_KNOWN)) {
        for url in discovery::well_known_candidates() {
            if discovery::probe(&app.http, &url).await {
                found.push(discovery::Found {
                    name: discovery::WELL_KNOWN.into(),
                    url,
                    instance_id: None,
                    via: "well_known".into(),
                });
                break;
            }
        }
    }
    Ok(found)
}

#[tauri::command]
async fn pair(app_handle: AppHandle, app: State<'_, App>, url: String, token: String, allow_insecure: bool) -> Result<store::SavedBox, String> {
    let (base, insecure) = address::normalize(&url, allow_insecure).map_err(|e| e.code().to_string())?;
    let token = token.trim().to_string();
    if token.is_empty() {
        return Err("token_missing".into());
    }
    let inst = api::get(&app.http, &base, Some(&token), "/v1/instance")
        .await
        .map_err(|e| e.code())?
        .ok_or_else(|| "not_a_onemind_box".to_string())?;
    let id = inst
        .get("hub_node_id")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| base.clone());
    let name = inst.get("name").and_then(|v| v.as_str()).unwrap_or("OneMind").to_string();
    store::save_token(&id, &token)?;
    let saved = store::SavedBox { id, name, url: base, insecure };
    app.store.upsert(saved.clone())?;
    refresh_one(&app_handle, &saved).await;
    ensure_followers(&app_handle);
    Ok(saved)
}

#[tauri::command]
fn remove_box(app_handle: AppHandle, app: State<'_, App>, id: String) -> Result<(), String> {
    store::delete_token(&id);
    app.store.remove(&id)?;
    app.last.lock().unwrap().remove(&id);
    app.inbox_primed.lock().unwrap().remove(&id);
    app.refreshing.lock().unwrap().remove(&id);
    ensure_followers(&app_handle);
    update_tray(&app_handle);
    Ok(())
}

#[tauri::command]
async fn refresh(app_handle: AppHandle, app: State<'_, App>) -> Result<(), String> {
    for b in app.store.list() {
        refresh_one(&app_handle, &b).await;
    }
    Ok(())
}

#[tauri::command]
fn open_dashboard(app_handle: AppHandle, app: State<'_, App>, id: String) -> Result<(), String> {
    let b = app.store.get(&id).ok_or("unknown_box")?;
    app_handle.opener().open_url(&b.url, None::<&str>).map_err(|_| "open_failed".to_string())
}

/// Opens a link that came from the box (an inbox item), only if it stays on the box's origin.
#[tauri::command]
fn open_link(app_handle: AppHandle, app: State<'_, App>, id: String, link: String) -> Result<(), String> {
    let b = app.store.get(&id).ok_or("unknown_box")?;
    let url = address::box_link(&b.url, &link).ok_or("link_refused")?;
    app_handle.opener().open_url(url, None::<&str>).map_err(|_| "open_failed".to_string())
}

/// Opens the box's approvals page in the browser, where a passkey approval is finished.
#[tauri::command]
fn open_approvals(app_handle: AppHandle, app: State<'_, App>, id: String) -> Result<(), String> {
    open_link(app_handle, app, id, approvals::BROWSER_PATH.into())
}

/// One pending action with its plan, for the approval card.
#[tauri::command]
async fn approval(app: State<'_, App>, id: String, action_id: String) -> Result<approvals::Detail, String> {
    if !api::safe_id(&action_id) {
        return Err("invalid_id".into());
    }
    let (b, t) = box_and_token(&app, &id)?;
    let me = me_of(&app, &id);
    approvals::detail(&app.http, &b.url, &t, &b.id, &action_id, me.as_ref()).await.map_err(|e| e.code())
}

/// Approve or deny. `plan_sha256` is the hash the card showed; approvals.rs checks it again.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
async fn decide(
    app_handle: AppHandle,
    app: State<'_, App>,
    id: String,
    action_id: String,
    decision: String,
    plan_sha256: Option<String>,
    reason: Option<String>,
) -> Result<approvals::Outcome, String> {
    if !api::safe_id(&action_id) {
        return Err("invalid_id".into());
    }
    let (b, t) = box_and_token(&app, &id)?;
    let me = me_of(&app, &id);
    let out = approvals::decide(&app.http, &b.url, &t, &action_id, &decision, plan_sha256.as_deref(), reason.as_deref(), me.as_ref())
        .await
        .map_err(|e| e.code())?;
    refresh_one(&app_handle, &b).await;
    Ok(out)
}

/// The newest inbox items, read and unread. `None`: this box has no inbox, or the token is
/// not a person's (only people have one).
#[tauri::command]
async fn inbox(app: State<'_, App>, id: String) -> Result<Option<Vec<inbox::Item>>, String> {
    let (b, t) = box_and_token(&app, &id)?;
    match api::get(&app.http, &b.url, Some(&t), inbox::LIST_PATH).await {
        Ok(Some(v)) => Ok(Some(inbox::parse(&v))),
        Ok(None) | Err(api::ApiError::Unauthorized) => Ok(None),
        Err(e) => Err(e.code()),
    }
}

/// Mark one inbox item read, or all of them when `item_id` is absent.
#[tauri::command]
async fn inbox_read(app_handle: AppHandle, app: State<'_, App>, id: String, item_id: Option<String>) -> Result<(), String> {
    let (b, t) = box_and_token(&app, &id)?;
    let path = match item_id {
        Some(n) if api::safe_id(&n) => format!("/v1/notifications/{n}/read"),
        Some(_) => return Err("invalid_id".into()),
        None => "/v1/notifications/read-all".into(),
    };
    api::post(&app.http, &b.url, &t, &path, &json!({})).await.map_err(|e| e.code())?;
    refresh_one(&app_handle, &b).await;
    Ok(())
}

/// Opens the box's file share in Finder / File Explorer. Shares (Samba app, per-device SMB
/// users) and a real mount are CLIENT-9 and UMB-FILES-5; docs/FILES.md has the WebDAV plan.
#[tauri::command]
fn open_files(app_handle: AppHandle, app: State<'_, App>, id: String) -> Result<(), String> {
    let b = app.store.get(&id).ok_or("unknown_box")?;
    let host = address::host_of(&b.url).ok_or("invalid_address")?;
    #[cfg(target_os = "windows")]
    {
        app_handle
            .opener()
            .open_path(format!(r"\\{host}\"), None::<&str>)
            .map_err(|_| "open_failed".to_string())
    }
    #[cfg(not(target_os = "windows"))]
    {
        app_handle
            .opener()
            .open_url(format!("smb://{host}/"), None::<&str>)
            .map_err(|_| "open_failed".to_string())
    }
}

// ---- box management (manage.rs): every write only FILES a request; an owner approves it ----

/// A refusal reason the UI explains on its own (the box's `plan_changed`), else the error code.
fn manage_err(e: api::ApiError) -> String {
    match &e {
        api::ApiError::Refused { reason: Some(r), .. } if r == "plan_changed" => "plan_changed".into(),
        _ => e.code(),
    }
}

/// Installed apps with the lifecycle actions each offers.
#[tauri::command]
async fn manage_apps(app: State<'_, App>, id: String) -> Result<Vec<manage::AppRow>, String> {
    let (b, t) = box_and_token(&app, &id)?;
    match api::get(&app.http, &b.url, Some(&t), "/v1/apps").await {
        Ok(Some(v)) => Ok(manage::parse_apps(&v)),
        Ok(None) => Ok(Vec::new()),
        Err(e) => Err(manage_err(e)),
    }
}

/// The plan an app action would run. Files nothing.
#[tauri::command]
async fn manage_plan(app: State<'_, App>, id: String, app_id: String, kind: String) -> Result<manage::PlanView, String> {
    let (b, t) = box_and_token(&app, &id)?;
    manage::preview(&app.http, &b.url, &t, &app_id, &kind).await.map_err(manage_err)
}

/// File the request, bound to the plan hash the card showed. It then waits for an owner.
#[tauri::command]
async fn manage_request(app_handle: AppHandle, app: State<'_, App>, id: String, app_id: String, kind: String, plan_sha256: String) -> Result<manage::Filed, String> {
    let (b, t) = box_and_token(&app, &id)?;
    let out = manage::request_lifecycle(&app.http, &b.url, &t, &app_id, &kind, &plan_sha256).await.map_err(manage_err)?;
    refresh_one(&app_handle, &b).await;
    Ok(out)
}

/// Backup status, destinations and the last runs. `None`: this box has no backup service yet.
#[tauri::command]
async fn manage_backups(app: State<'_, App>, id: String) -> Result<Option<manage::BackupView>, String> {
    let (b, t) = box_and_token(&app, &id)?;
    manage::backups(&app.http, &b.url, &t).await.map_err(manage_err)
}

/// File a backup run or a backup check (`run` or `verify`). Restore is not offered here.
#[tauri::command]
async fn manage_backup_request(app_handle: AppHandle, app: State<'_, App>, id: String, kind: String) -> Result<manage::Filed, String> {
    let (b, t) = box_and_token(&app, &id)?;
    let out = manage::request_backup(&app.http, &b.url, &t, &kind).await.map_err(manage_err)?;
    refresh_one(&app_handle, &b).await;
    Ok(out)
}

/// First-run preferences (owner only; anyone else gets `permission_denied`).
#[tauri::command]
async fn manage_settings(app: State<'_, App>, id: String) -> Result<Option<manage::Settings>, String> {
    let (b, t) = box_and_token(&app, &id)?;
    manage::settings(&app.http, &b.url, &t).await.map_err(manage_err)
}

#[tauri::command]
async fn manage_settings_save(app_handle: AppHandle, app: State<'_, App>, id: String, body: manage::SettingsBody) -> Result<manage::Settings, String> {
    let (b, t) = box_and_token(&app, &id)?;
    let out = manage::save_settings(&app.http, &b.url, &t, &body).await.map_err(manage_err)?;
    refresh_one(&app_handle, &b).await;
    Ok(out)
}

#[tauri::command]
fn hide(window: WebviewWindow) {
    let _ = window.hide();
}

#[tauri::command]
fn quit(app_handle: AppHandle) {
    app_handle.exit(0);
}

// ---- polling, events, notifications, tray ----

async fn refresh_one(app_handle: &AppHandle, b: &store::SavedBox) {
    let app = app_handle.state::<App>();
    let gate = app.refreshing.lock().unwrap().entry(b.id.clone()).or_default().clone();
    let _turn = gate.lock().await;
    let st = match store::token(&b.id) {
        Some(t) => api::status(&app.http, &b.id, &b.url, &t).await,
        None => {
            let mut s = api::status(&app.http, &b.id, &b.url, "").await;
            s.error = Some("token_missing".into());
            s
        }
    };
    notify_new(app_handle, b, &st);
    app.last.lock().unwrap().insert(b.id.clone(), st.clone());
    let _ = app_handle.emit("status", &st);
    update_tray(app_handle);
}

fn notify_new(app_handle: &AppHandle, b: &store::SavedBox, st: &api::Status) {
    // An unreachable box reports nothing; keep what was announced until it answers again.
    if !st.reachable {
        return;
    }
    let app = app_handle.state::<App>();
    let quiet_backlog = st.inbox.is_some() && app.inbox_primed.lock().unwrap().insert(b.id.clone());
    let name = st.name.as_deref().unwrap_or(&b.name);
    let banners = {
        let mut seen = app.notified.lock().unwrap();
        inbox::banners(&b.id, name, &st.pending, st.inbox.as_deref(), &mut seen, quiet_backlog)
    };
    for x in banners {
        let _ = app_handle.notification().builder().title(plain(&x.title)).body(plain(&x.body)).show();
    }
}

/// Banner text from the box stays text. Linux notification servers may render a subset of HTML
/// in the body (freedesktop `body-markup`), so markup characters are escaped there.
fn plain(s: &str) -> String {
    if cfg!(target_os = "linux") {
        s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
    } else {
        s.to_string()
    }
}

fn update_tray(app_handle: &AppHandle) {
    let app = app_handle.state::<App>();
    let last = app.last.lock().unwrap();
    let pending: usize = last.values().map(|s| s.pending.len()).sum();
    let unread: usize = last.values().map(|s| s.inbox.as_ref().map_or(0, Vec::len)).sum();
    let down = last.values().filter(|s| !s.reachable).count();
    if let Some(tray) = app_handle.tray_by_id("main") {
        let mut parts = Vec::new();
        if pending > 0 {
            parts.push(format!("{pending} waiting for approval"));
        }
        if unread > 0 {
            parts.push(format!("{unread} unread"));
        }
        if down > 0 {
            parts.push(format!("{down} box(es) unreachable"));
        }
        let tip = if parts.is_empty() { "OneMind: nothing needs you".to_string() } else { format!("OneMind: {}", parts.join(", ")) };
        let _ = tray.set_tooltip(Some(&tip));
        #[cfg(target_os = "macos")]
        let _ = tray.set_title(if pending > 0 { Some(pending.to_string()) } else { None::<String> });
    }
}

fn set_live(app_handle: &AppHandle, box_id: &str, on: bool) {
    let app = app_handle.state::<App>();
    let changed = {
        let mut live = app.live.lock().unwrap();
        if on { live.insert(box_id.to_string()) } else { live.remove(box_id) }
    };
    if changed {
        let _ = app_handle.emit("live", json!({ "box_id": box_id, "live": on }));
    }
}

/// Follow one box's event stream for as long as the box is saved. Events only wake a REST
/// refresh (events.rs); the stream reconnects with `Last-Event-ID` and backs off on errors.
async fn follow(app_handle: AppHandle, box_id: String) {
    let client = api::stream_client();
    let mut last_id: Option<String> = None;
    let mut backoff = events::MIN_WAIT;
    loop {
        let Some(b) = app_handle.state::<App>().store.get(&box_id) else { return };
        let status = match store::token(&b.id) {
            None => Some(401),
            Some(token) => {
                let mut req = client
                    .get(format!("{}{}", b.url, events::PATH))
                    .bearer_auth(&token)
                    .header("accept", "text/event-stream");
                if let Some(id) = &last_id {
                    req = req.header("last-event-id", id.as_str());
                }
                match req.send().await {
                    Err(_) => None,
                    Ok(mut resp) => {
                        let code = resp.status().as_u16();
                        if code == 200 {
                            set_live(&app_handle, &box_id, true);
                            backoff = events::MIN_WAIT;
                            let mut parser = events::Parser::default();
                            let mut last_wake: Option<Instant> = None;
                            while let Ok(Some(chunk)) = resp.chunk().await {
                                let Ok(evs) = parser.push(&chunk) else { break };
                                if let Some(id) = parser.last_id() {
                                    last_id = Some(id.to_string());
                                }
                                let due = last_wake.is_none_or(|t| t.elapsed() >= WAKE_GAP);
                                if due && evs.iter().any(|e| events::wakes(&e.kind)) {
                                    last_wake = Some(Instant::now());
                                    refresh_one(&app_handle, &b).await;
                                }
                            }
                            set_live(&app_handle, &box_id, false);
                        }
                        Some(code)
                    }
                }
            }
        };
        let wait = events::wait_after(status, backoff);
        backoff = (backoff * 2).min(events::MAX_BACKOFF);
        tokio::time::sleep(Duration::from_secs(wait)).await;
    }
}

/// One follower per saved box; followers of removed boxes stop.
fn ensure_followers(app_handle: &AppHandle) {
    let app = app_handle.state::<App>();
    let ids: HashSet<String> = app.store.list().into_iter().map(|b| b.id).collect();
    let mut stopped = Vec::new();
    {
        let mut f = app.followers.lock().unwrap();
        f.retain(|id, h| {
            let keep = ids.contains(id);
            if !keep {
                h.abort();
                stopped.push(id.clone());
            }
            keep
        });
        for id in ids {
            if !f.contains_key(&id) {
                let h = tauri::async_runtime::spawn(follow(app_handle.clone(), id.clone()));
                f.insert(id, h);
            }
        }
    }
    for id in stopped {
        set_live(app_handle, &id, false);
    }
}

fn spawn_poller(app_handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            ensure_followers(&app_handle);
            let boxes = app_handle.state::<App>().store.list();
            for b in boxes {
                refresh_one(&app_handle, &b).await;
            }
            tokio::time::sleep(POLL).await;
        }
    });
}

/// Show the popover under the menu-bar icon (macOS) or above the tray icon (Windows).
fn toggle_popover(app_handle: &AppHandle, anchor: Option<Rect>) {
    let Some(w) = app_handle.get_webview_window("main") else { return };
    if w.is_visible().unwrap_or(false) {
        let _ = w.hide();
        return;
    }
    if let (Some(r), Ok(size)) = (anchor, w.outer_size()) {
        let scale = w.scale_factor().unwrap_or(1.0);
        let p = r.position.to_physical::<f64>(scale);
        let s = r.size.to_physical::<f64>(scale);
        let monitor = app_handle.monitor_from_point(p.x, p.y).ok().flatten();
        let (mx, my, mw, mh) = monitor
            .map(|m| (m.position().x as f64, m.position().y as f64, m.size().width as f64, m.size().height as f64))
            .unwrap_or((0.0, 0.0, 1e5, 1e5));
        let mut x = p.x + s.width / 2.0 - size.width as f64 / 2.0;
        x = x.clamp(mx + 8.0, mx + mw - size.width as f64 - 8.0);
        let top_half = p.y < my + mh / 2.0;
        let y = if top_half { p.y + s.height + 6.0 } else { p.y - size.height as f64 - 6.0 };
        let _ = w.set_position(PhysicalPosition::new(x, y));
    } else {
        let _ = w.center();
    }
    let _ = w.show();
    let _ = w.set_focus();
    let _ = w.emit("shown", ());
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| toggle_popover(app, None)))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let dir = app.path().app_config_dir().expect("config dir");
            app.manage(App {
                store: store::Store::load(dir),
                http: api::client(),
                last: Mutex::new(HashMap::new()),
                notified: Mutex::new(HashSet::new()),
                inbox_primed: Mutex::new(HashSet::new()),
                live: Mutex::new(HashSet::new()),
                followers: Mutex::new(HashMap::new()),
                refreshing: Mutex::new(HashMap::new()),
            });

            let show = MenuItem::with_id(app, "show", "Show OneMind", true, None::<&str>)?;
            let dash = MenuItem::with_id(app, "dashboard", "Open dashboard", true, None::<&str>)?;
            let files = MenuItem::with_id(app, "files", "Files", true, None::<&str>)?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit = MenuItem::with_id(app, "quit", "Quit OneMind", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &dash, &files, &sep, &quit])?;

            let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/tray/44x44.png"))?;
            TrayIconBuilder::with_id("main")
                .icon(icon)
                .icon_as_template(true)
                .tooltip("OneMind")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, ev| {
                    let first = app.state::<App>().store.list().into_iter().next();
                    match ev.id().as_ref() {
                        "show" => toggle_popover(app, None),
                        "dashboard" => {
                            if let Some(b) = first {
                                let _ = app.opener().open_url(&b.url, None::<&str>);
                            } else {
                                toggle_popover(app, None);
                            }
                        }
                        "files" => {
                            if let Some(b) = first {
                                let _ = open_files(app.clone(), app.state::<App>(), b.id);
                            } else {
                                toggle_popover(app, None);
                            }
                        }
                        "quit" => app.exit(0),
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, ev| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, rect, .. } = ev {
                        toggle_popover(tray.app_handle(), Some(rect));
                    }
                })
                .build(app)?;

            if let Some(w) = app.get_webview_window("main") {
                let w2 = w.clone();
                w.on_window_event(move |e| {
                    if let WindowEvent::Focused(false) = e {
                        if std::env::var_os("ONEMIND_DESKTOP_PIN").is_none() {
                            let _ = w2.hide();
                        }
                    }
                });
                // First run: nothing paired yet, so open the popover to start pairing.
                if app.state::<App>().store.list().is_empty() || std::env::var_os("ONEMIND_DESKTOP_PIN").is_some() {
                    let _ = w.center();
                    let _ = w.show();
                }
            }
            spawn_poller(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_boxes,
            discover,
            pair,
            remove_box,
            refresh,
            open_dashboard,
            open_link,
            open_approvals,
            approval,
            decide,
            inbox,
            inbox_read,
            open_files,
            manage_apps,
            manage_plan,
            manage_request,
            manage_backups,
            manage_backup_request,
            manage_settings,
            manage_settings_save,
            hide,
            quit
        ])
        .run(tauri::generate_context!())
        .expect("error while running OneMind desktop");
}
