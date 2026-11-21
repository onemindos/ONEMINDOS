// SPDX-License-Identifier: Apache-2.0
//! Desktop app updates (docs/UPDATER.md; CLIENT-12). The rules, in the order they matter:
//!
//! 1. **Signature first.** `tauri-plugin-updater` verifies the Ed25519 (minisign) signature of the
//!    download against the public key in `tauri.conf.json` and refuses the file otherwise.
//! 2. **Newer only.** The plugin's default comparison: only a greater version is offered.
//! 3. **Ask, then install.** `update_check` only *looks*; nothing downloads until the person clicks
//!    "Install and restart" in the popover, which calls `update_install`. There is no silent path.
//! 4. **Compiled-in endpoints.** The channel follows the running version (a `-dev` build follows
//!    `dev`, everything else `stable`) and the URLs below are constants. No box, page or setting
//!    can point the updater anywhere else, and plain HTTP is refused.
//! 5. **Off until the key exists.** While `tauri.conf.json` still holds the placeholder public key
//!    the commands report `configured: false` and the UI shows nothing.

use serde::Serialize;
use std::sync::Mutex;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_updater::{Update, UpdaterExt};

/// Written into `tauri.conf.json` until the founder runs `tauri signer generate` (desktop/README.md).
pub const PLACEHOLDER_PUBKEY: &str = "REPLACE_WITH_TAURI_SIGNER_PUBLIC_KEY";

pub const ENDPOINT_STABLE: &str = "https://github.com/onemindos/ONEMINDOS/releases/download/desktop-stable/latest.json";
pub const ENDPOINT_DEV: &str = "https://github.com/onemindos/ONEMINDOS/releases/download/desktop-dev/latest.json";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Channel {
    Stable,
    Dev,
}

/// A development build (`0.2.0-dev.3`) follows the dev channel, like the OS image; every other
/// version follows stable. Build metadata (`+abc`) is ignored.
pub fn channel_for(version: &str) -> Channel {
    let pre = version.split('+').next().unwrap_or("").split_once('-').map(|(_, p)| p).unwrap_or("");
    if pre.split('.').next() == Some("dev") {
        Channel::Dev
    } else {
        Channel::Stable
    }
}

pub fn endpoint_for(c: Channel) -> &'static str {
    match c {
        Channel::Stable => ENDPOINT_STABLE,
        Channel::Dev => ENDPOINT_DEV,
    }
}

/// HTTPS only, no credentials in the URL.
pub fn endpoint_ok(url: &str) -> bool {
    url::Url::parse(url).is_ok_and(|u| u.scheme() == "https" && u.username().is_empty() && u.password().is_none() && u.host_str().is_some())
}

/// True when a real key is configured (not empty, not the placeholder).
pub fn key_configured(pubkey: Option<&str>) -> bool {
    pubkey.map(str::trim).is_some_and(|k| !k.is_empty() && k != PLACEHOLDER_PUBKEY)
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Offer {
    pub version: String,
    pub current: String,
    pub notes: Option<String>,
    pub date: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Check {
    pub configured: bool,
    pub channel: Channel,
    pub current: String,
    pub available: Option<Offer>,
}

/// The update found by the last check, kept so the install click installs exactly what was shown.
#[derive(Default)]
pub struct Pending(Mutex<Option<Update>>);

fn pubkey(app: &AppHandle) -> Option<String> {
    app.config().plugins.0.get("updater")?.get("pubkey")?.as_str().map(str::to_string)
}

pub async fn check(app: &AppHandle, pending: &Pending) -> Result<Check, String> {
    let current = app.package_info().version.to_string();
    let channel = channel_for(&current);
    let configured = key_configured(pubkey(app).as_deref());
    let mut out = Check { configured, channel, current: current.clone(), available: None };
    if !configured {
        return Ok(out);
    }
    let endpoint = endpoint_for(channel);
    if !endpoint_ok(endpoint) {
        return Err("update_endpoint_refused".into());
    }
    let url = url::Url::parse(endpoint).map_err(|_| "update_endpoint_refused".to_string())?;
    let updater = app.updater_builder().endpoints(vec![url]).map_err(|e| e.to_string())?.build().map_err(|e| e.to_string())?;
    let found = updater.check().await.map_err(|e| e.to_string())?;
    out.available = found.as_ref().map(|u| Offer { version: u.version.clone(), current, notes: u.body.clone(), date: u.date.map(|d| d.to_string()) });
    *pending.0.lock().unwrap() = found;
    Ok(out)
}

/// Download, verify (the plugin refuses a bad signature) and install what the last check showed,
/// then restart. Only the popover's button calls this.
pub async fn install(app: &AppHandle, pending: &Pending) -> Result<(), String> {
    let update = pending.0.lock().unwrap().take().ok_or_else(|| "no_update_pending".to_string())?;
    update.download_and_install(|_, _| {}, || {}).await.map_err(|e| e.to_string())?;
    app.restart()
}

#[tauri::command]
pub async fn update_check(app: AppHandle, pending: State<'_, Pending>) -> Result<Check, String> {
    check(&app, &pending).await
}

#[tauri::command]
pub async fn update_install(app: AppHandle, pending: State<'_, Pending>) -> Result<(), String> {
    install(&app, &pending).await
}

/// Look once at start and every six hours. A found update is announced to the popover and the
/// tray tooltip; it is never installed here.
pub fn spawn_checker(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            let pending = app.state::<Pending>();
            if let Ok(c) = check(&app, &pending).await {
                if c.configured {
                    use tauri::Emitter;
                    let _ = app.emit("update", &c);
                }
            }
            tokio::time::sleep(std::time::Duration::from_secs(6 * 3600)).await;
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn channel_follows_the_version() {
        assert_eq!(channel_for("0.1.0"), Channel::Stable);
        assert_eq!(channel_for("1.4.2"), Channel::Stable);
        assert_eq!(channel_for("0.2.0-dev"), Channel::Dev);
        assert_eq!(channel_for("0.2.0-dev.7"), Channel::Dev);
        assert_eq!(channel_for("0.2.0-dev.7+abc"), Channel::Dev);
        assert_eq!(channel_for("0.2.0-rc.1"), Channel::Stable);
        assert_eq!(channel_for("0.2.0-devious"), Channel::Stable);
        assert_eq!(channel_for("0.2.0+dev"), Channel::Stable);
        assert_eq!(channel_for(""), Channel::Stable);
    }

    #[test]
    fn endpoints_are_https_and_distinct() {
        assert!(endpoint_ok(ENDPOINT_STABLE));
        assert!(endpoint_ok(ENDPOINT_DEV));
        assert_ne!(endpoint_for(Channel::Stable), endpoint_for(Channel::Dev));
        assert!(!endpoint_ok("http://example.com/latest.json"));
        assert!(!endpoint_ok("file:///tmp/latest.json"));
        assert!(!endpoint_ok("https://"));
        assert!(!endpoint_ok("not a url"));
        assert!(!endpoint_ok(&format!("https://u:p{}example.com/latest.json", '@')));
    }

    #[test]
    fn placeholder_key_keeps_updates_off() {
        assert!(!key_configured(None));
        assert!(!key_configured(Some("")));
        assert!(!key_configured(Some("  ")));
        assert!(!key_configured(Some(PLACEHOLDER_PUBKEY)));
        assert!(key_configured(Some("dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEFCQ0Q=")));
    }
}
