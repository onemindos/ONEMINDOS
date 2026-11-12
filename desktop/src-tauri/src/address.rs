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
}
