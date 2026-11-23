// SPDX-License-Identifier: Apache-2.0
//! Open in Finder / Explorer / Files (files-webdav, #722): how this computer opens the box's files.
//!
//! - macOS: Finder mounts the box's WebDAV door (`https://<box>/dav/`) with `mount volume`, the same
//!   as Go > Connect to Server; Finder asks for the user name and an app password (Settings > Account
//!   and security on the box) and keeps it in the keychain.
//! - Linux: the file manager opens `davs://<box>/dav/` (GNOME Files, KDE Dolphin), the same door.
//! - Windows: File Explorer opens the SMB share `\\<box>\`. Microsoft deprecated its WebDAV client
//!   (the WebClient service), so Windows stays on SMB (File sharing on the box).
//!
//! The box answers WebDAV only from the LAN and the mesh; elsewhere Finder simply finds nothing.

use url::{Host, Url};

#[derive(Debug, PartialEq, Eq)]
pub enum Target {
    /// macOS: the AppleScript `mount volume` of this URL.
    Mount(String),
    /// Linux: a davs:// (or dav:// for a plain-HTTP box) URL for the file manager.
    Url(String),
    /// Windows: an SMB path for File Explorer.
    Path(String),
}

/// The menu and button text for this computer.
pub fn label(os: &str) -> &'static str {
    match os {
        "macos" => "Open in Finder",
        "windows" => "Open in Explorer",
        _ => "Open in Files",
    }
}

/// What to open for a box at `base_url` (its paired address) on `os` (std::env::consts::OS).
pub fn target(os: &str, base_url: &str) -> Option<Target> {
    let u = Url::parse(base_url).ok()?;
    let host = match u.host()? {
        Host::Domain(d) if d.chars().all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-') => d.to_string(),
        Host::Domain(_) => return None,
        Host::Ipv4(ip) => ip.to_string(),
        Host::Ipv6(ip) => format!("[{ip}]"),
    };
    let tls = match u.scheme() {
        "https" => true,
        "http" => false,
        _ => return None,
    };
    let port = u.port().map(|p| format!(":{p}")).unwrap_or_default();
    Some(match os {
        "windows" => Target::Path(format!(r"\\{}\", crate::address::host_of(base_url)?)),
        "macos" => Target::Mount(format!("{}://{host}{port}/dav/", if tls { "https" } else { "http" })),
        _ => Target::Url(format!("{}://{host}{port}/dav/", if tls { "davs" } else { "dav" })),
    })
}

/// The AppleScript that mounts `url`. `target` builds the URL from a parsed host made only of letters,
/// digits, dots, dashes, colons and brackets, so it can never close the quoted string.
pub fn mount_script(url: &str) -> Option<String> {
    if url.contains(['"', '\\', '\n', '\r']) {
        return None;
    }
    Some(format!("mount volume \"{url}\""))
}

/// The tray line that says how the box is doing: name, then online or not.
pub fn state_line(name: Option<&str>, reachable: Option<bool>) -> String {
    match (name, reachable) {
        (None, _) => "No box paired yet".to_string(),
        (Some(n), None) => format!("{n}: checking…"),
        (Some(n), Some(true)) => format!("{n}: online"),
        (Some(n), Some(false)) => format!("{n}: not reachable"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_os_opens_its_own_door() {
        assert_eq!(target("macos", "https://onemind.local"), Some(Target::Mount("https://onemind.local/dav/".into())));
        assert_eq!(target("linux", "https://onemind.local"), Some(Target::Url("davs://onemind.local/dav/".into())));
        assert_eq!(target("windows", "https://onemind.local"), Some(Target::Path(r"\\onemind.local\".into())));
    }

    #[test]
    fn the_port_and_plain_http_are_kept() {
        assert_eq!(target("macos", "https://box.local:8443/"), Some(Target::Mount("https://box.local:8443/dav/".into())));
        assert_eq!(target("linux", "http://127.0.0.1:8080"), Some(Target::Url("dav://127.0.0.1:8080/dav/".into())));
        assert_eq!(target("linux", "https://[fd00::1]"), Some(Target::Url("davs://[fd00::1]/dav/".into())));
        assert_eq!(target("windows", "https://[fd00::1]"), Some(Target::Path(r"\\fd00::1\".into())));
    }

    #[test]
    fn nothing_odd_reaches_the_script() {
        assert_eq!(target("macos", "ftp://box.local"), None);
        assert_eq!(target("macos", "not a url"), None);
        assert_eq!(mount_script("https://box.local/dav/"), Some("mount volume \"https://box.local/dav/\"".into()));
        assert_eq!(mount_script("https://x\" & do shell script \"id"), None);
    }

    #[test]
    fn labels_and_state() {
        assert_eq!(label("macos"), "Open in Finder");
        assert_eq!(label("windows"), "Open in Explorer");
        assert_eq!(label("linux"), "Open in Files");
        assert_eq!(state_line(None, None), "No box paired yet");
        assert_eq!(state_line(Some("Home box"), Some(true)), "Home box: online");
        assert_eq!(state_line(Some("Home box"), Some(false)), "Home box: not reachable");
        assert_eq!(state_line(Some("Home box"), None), "Home box: checking…");
    }
}
