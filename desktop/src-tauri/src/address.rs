// SPDX-License-Identifier: Apache-2.0
//! Turning what the owner typed into a box base URL, and the plain-HTTP rule:
//! HTTPS is always accepted; plain HTTP only to this computer (loopback), or when the owner
//! ticks "this box has no HTTPS yet", which the UI then marks as "Not encrypted".

use std::net::IpAddr;
use url::{Host, Url};

#[derive(Debug, PartialEq)]
pub enum AddressError {
    Invalid,
    /// Plain HTTP to another machine without the owner's explicit consent.
    NeedsHttps,
}

impl AddressError {
    pub fn code(&self) -> &'static str {
        match self {
            AddressError::Invalid => "invalid_address",
            AddressError::NeedsHttps => "needs_https",
        }
    }
}

/// Returns (base_url, is_plain_http_to_another_machine).
pub fn normalize(input: &str, allow_insecure: bool) -> Result<(String, bool), AddressError> {
    let raw = input.trim();
    if raw.is_empty() {
        return Err(AddressError::Invalid);
    }
    let with_scheme = if raw.contains("://") { raw.to_string() } else { format!("https://{raw}") };
    let u = Url::parse(&with_scheme).map_err(|_| AddressError::Invalid)?;
    if !matches!(u.scheme(), "http" | "https") || !u.username().is_empty() || u.password().is_some() {
        return Err(AddressError::Invalid);
    }
    let host = u.host().ok_or(AddressError::Invalid)?;
    let loopback = match &host {
        Host::Domain(d) => d.eq_ignore_ascii_case("localhost"),
        Host::Ipv4(ip) => IpAddr::V4(*ip).is_loopback(),
        Host::Ipv6(ip) => IpAddr::V6(*ip).is_loopback(),
    };
    let insecure = u.scheme() == "http" && !loopback;
    if insecure && !allow_insecure {
        return Err(AddressError::NeedsHttps);
    }
    let host_str = match host {
        Host::Ipv6(ip) => format!("[{ip}]"),
        h => h.to_string(),
    };
    let base = match u.port() {
        Some(p) => format!("{}://{}:{}", u.scheme(), host_str, p),
        None => format!("{}://{}", u.scheme(), host_str),
    };
    Ok((base, insecure))
}

/// Host part of a saved base URL, for the file-share address.
pub fn host_of(base: &str) -> Option<String> {
    Url::parse(base).ok()?.host_str().map(|h| h.trim_matches(['[', ']']).to_string())
}

/// A link that came from the box (an inbox item's `link`, the approvals page) as a full URL on
/// the box's own origin, or `None`. A path must start with exactly one `/`; an absolute URL must
/// have the box's scheme, host and port. Anything else (another host, `//host`, `javascript:`,
/// `file:`, backslashes, control characters) is refused, so box data cannot make the app open
/// an arbitrary address.
pub fn box_link(base: &str, link: &str) -> Option<String> {
    let l = link.trim();
    if l.is_empty() || l.len() > 2048 || l.contains('\\') || l.chars().any(char::is_control) {
        return None;
    }
    let b = Url::parse(base).ok()?;
    let u = if l.starts_with('/') {
        if l.starts_with("//") {
            return None;
        }
        b.join(l).ok()?
    } else {
        Url::parse(l).ok()?
    };
    let same = u.scheme() == b.scheme()
        && u.host_str() == b.host_str()
        && u.port_or_known_default() == b.port_or_known_default()
        && u.username().is_empty()
        && u.password().is_none();
    same.then(|| u.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn https_default_and_path_dropped() {
        assert_eq!(normalize("onemind.local:8080/foo", false), Ok(("https://onemind.local:8080".into(), false)));
    }

    #[test]
    fn loopback_http_ok() {
        assert_eq!(normalize("http://127.0.0.1:8080", false), Ok(("http://127.0.0.1:8080".into(), false)));
        assert_eq!(normalize("http://localhost:8080", false), Ok(("http://localhost:8080".into(), false)));
    }

    #[test]
    fn lan_http_needs_consent() {
        assert_eq!(normalize("http://onemind.local:8080", false), Err(AddressError::NeedsHttps));
        assert_eq!(normalize("http://onemind.local:8080", true), Ok(("http://onemind.local:8080".into(), true)));
    }

    #[test]
    fn rejects_credentials_and_other_schemes() {
        let with_credentials = format!("https://a:b{}box.local", '@');
        assert_eq!(normalize(&with_credentials, false), Err(AddressError::Invalid));
        assert_eq!(normalize("file:///etc/passwd", false), Err(AddressError::Invalid));
        assert_eq!(normalize("   ", false), Err(AddressError::Invalid));
    }

    #[test]
    fn host_extraction() {
        assert_eq!(host_of("https://onemind.local:8080").as_deref(), Some("onemind.local"));
    }

    #[test]
    fn box_links_stay_on_the_box() {
        let base = "https://onemind.local:8443";
        assert_eq!(box_link(base, "/approvals/6f1c").as_deref(), Some("https://onemind.local:8443/approvals/6f1c"));
        assert_eq!(box_link(base, "https://onemind.local:8443/backups").as_deref(), Some("https://onemind.local:8443/backups"));
        assert_eq!(box_link("https://onemind.local", "https://onemind.local:443/x").as_deref(), Some("https://onemind.local/x"));
        for bad in [
            "//evil.example/x",
            "https://evil.example/approvals",
            "http://onemind.local:8443/x",
            "https://onemind.local:9999/x",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "/\\evil.example",
            "/a\nb",
            "approvals",
            "",
        ] {
            assert_eq!(box_link(base, bad), None, "{bad:?}");
        }
        let with_credentials = format!("https://u:p{}onemind.local:8443/x", '@');
        assert_eq!(box_link(base, &with_credentials), None);
    }
}
