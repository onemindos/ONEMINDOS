// SPDX-License-Identifier: Apache-2.0
//! Saved boxes. The list (name, address) is a plain JSON file in the app's config folder;
//! the token for each box lives only in the OS keychain (macOS Keychain, Windows Credential
//! Manager), never in that file and never in the web view's storage.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;

const KEYCHAIN_SERVICE: &str = "io.onemind.desktop";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct SavedBox {
    /// Stable id: the box's hub node id from `GET /v1/instance`.
    pub id: String,
    pub name: String,
    /// Base URL, scheme + host + port, no path. Example: `https://onemind.local:8080`.
    pub url: String,
    /// True when the owner accepted plain HTTP to a non-loopback address (development boxes).
    #[serde(default)]
    pub insecure: bool,
}

pub struct Store {
    path: PathBuf,
    boxes: Mutex<Vec<SavedBox>>,
}

impl Store {
    pub fn load(dir: PathBuf) -> Self {
        let path = dir.join("boxes.json");
        let boxes = std::fs::read(&path)
            .ok()
            .and_then(|b| serde_json::from_slice::<Vec<SavedBox>>(&b).ok())
            .unwrap_or_default();
        Store { path, boxes: Mutex::new(boxes) }
    }

    pub fn list(&self) -> Vec<SavedBox> {
        self.boxes.lock().unwrap().clone()
    }

    pub fn get(&self, id: &str) -> Option<SavedBox> {
        self.boxes.lock().unwrap().iter().find(|b| b.id == id).cloned()
    }

    pub fn upsert(&self, b: SavedBox) -> Result<(), String> {
        let mut boxes = self.boxes.lock().unwrap();
        boxes.retain(|x| x.id != b.id);
        boxes.push(b);
        self.write(&boxes)
    }

    pub fn remove(&self, id: &str) -> Result<(), String> {
        let mut boxes = self.boxes.lock().unwrap();
        boxes.retain(|x| x.id != id);
        self.write(&boxes)
    }

    fn write(&self, boxes: &[SavedBox]) -> Result<(), String> {
        if let Some(dir) = self.path.parent() {
            std::fs::create_dir_all(dir).map_err(|_| "config_write_failed".to_string())?;
        }
        let tmp = self.path.with_extension("json.tmp");
        let body = serde_json::to_vec_pretty(boxes).map_err(|_| "config_write_failed".to_string())?;
        std::fs::write(&tmp, body).map_err(|_| "config_write_failed".to_string())?;
        std::fs::rename(&tmp, &self.path).map_err(|_| "config_write_failed".to_string())
    }
}

fn entry(box_id: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYCHAIN_SERVICE, box_id).map_err(|_| "keychain_unavailable".to_string())
}

pub fn save_token(box_id: &str, token: &str) -> Result<(), String> {
    entry(box_id)?.set_password(token).map_err(|_| "keychain_write_failed".to_string())
}

pub fn token(box_id: &str) -> Option<String> {
    entry(box_id).ok()?.get_password().ok()
}

pub fn delete_token(box_id: &str) {
    if let Ok(e) = entry(box_id) {
        let _ = e.delete_credential();
    }
}

/// Writes, reads and deletes one keychain item. `cargo test -- --ignored keychain_roundtrip`
#[cfg(test)]
mod live {
    #[test]
    #[ignore]
    fn keychain_roundtrip() {
        let id = "test-box-roundtrip";
        super::save_token(id, "not-a-real-token").expect("save");
        assert_eq!(super::token(id).as_deref(), Some("not-a-real-token"));
        super::delete_token(id);
        assert_eq!(super::token(id), None);
    }
}
