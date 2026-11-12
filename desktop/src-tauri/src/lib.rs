// SPDX-License-Identifier: Apache-2.0
//! OneMind desktop client (CLIENT-8 skeleton): a menu-bar / tray app that finds boxes,
//! pairs with a token kept in the OS keychain, shows box status, raises a native
//! notification when something waits for the owner's approval, and opens the dashboard
//! and the box's file share. Approving happens in the dashboard, never from a notification.

mod address;
mod api;
mod discovery;
mod store;

use serde::Serialize;
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::Duration;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, Rect, State, WebviewWindow, WindowEvent};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_opener::OpenerExt;

const POLL: Duration = Duration::from_secs(20);

struct App {
    store: store::Store,
    http: reqwest::Client,
    last: Mutex<HashMap<String, api::Status>>,
    notified: Mutex<HashSet<String>>,
}

#[derive(Serialize)]
struct BoxView {
    #[serde(flatten)]
    saved: store::SavedBox,
    has_token: bool,
    status: Option<api::Status>,
}

// ---- commands (the only things the web view can call) ----

#[tauri::command]
fn list_boxes(app: State<'_, App>) -> Vec<BoxView> {
    let last = app.last.lock().unwrap();
    app.store
        .list()
        .into_iter()
        .map(|b| BoxView {
            has_token: store::token(&b.id).is_some(),
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
    Ok(saved)
}

#[tauri::command]
fn remove_box(app_handle: AppHandle, app: State<'_, App>, id: String) -> Result<(), String> {
    store::delete_token(&id);
    app.store.remove(&id)?;
    app.last.lock().unwrap().remove(&id);
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

/// Opens the box's file share in Finder / File Explorer. Shares (Samba app, per-device
/// SMB users) and a real mount are CLIENT-9; today this hands the address to the OS.
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

#[tauri::command]
fn hide(window: WebviewWindow) {
    let _ = window.hide();
}

#[tauri::command]
fn quit(app_handle: AppHandle) {
    app_handle.exit(0);
}

// ---- polling, notifications, tray ----

async fn refresh_one(app_handle: &AppHandle, b: &store::SavedBox) {
    let app = app_handle.state::<App>();
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
    let app = app_handle.state::<App>();
    let mut seen = app.notified.lock().unwrap();
    for p in &st.pending {
        let key = format!("{}/{}", b.id, p.id);
        if seen.insert(key) {
            let what = match &p.target {
                Some(t) => format!("{} {}", p.kind, t),
                None => p.kind.clone(),
            };
            let who = p.requested_by.as_deref().unwrap_or("someone");
            let _ = app_handle
                .notification()
                .builder()
                .title(format!("Approval needed on {}", b.name))
                .body(format!("{who} asks: {what}. Review it in the dashboard."))
                .show();
        }
    }
}

fn update_tray(app_handle: &AppHandle) {
    let app = app_handle.state::<App>();
    let last = app.last.lock().unwrap();
    let pending: usize = last.values().map(|s| s.pending.len()).sum();
    let down = last.values().filter(|s| !s.reachable).count();
    if let Some(tray) = app_handle.tray_by_id("main") {
        let tip = match (pending, down) {
            (0, 0) => "OneMind: all good".to_string(),
            (p, 0) => format!("OneMind: {p} waiting for approval"),
            (p, d) => format!("OneMind: {p} waiting, {d} box(es) unreachable"),
        };
        let _ = tray.set_tooltip(Some(&tip));
        #[cfg(target_os = "macos")]
        let _ = tray.set_title(if pending > 0 { Some(pending.to_string()) } else { None::<String> });
    }
}

fn spawn_poller(app_handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
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
            });

            let show = MenuItem::with_id(app, "show", "Show OneMind", true, None::<&str>)?;
            let dash = MenuItem::with_id(app, "dashboard", "Open dashboard", true, None::<&str>)?;
            let files = MenuItem::with_id(app, "files", "Files", true, None::<&str>)?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit = MenuItem::with_id(app, "quit", "Quit OneMind", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &dash, &files, &sep, &quit])?;

            let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/tray.png"))?;
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
            list_boxes, discover, pair, remove_box, refresh, open_dashboard, open_files, hide, quit
        ])
        .run(tauri::generate_context!())
        .expect("error while running OneMind desktop");
}
