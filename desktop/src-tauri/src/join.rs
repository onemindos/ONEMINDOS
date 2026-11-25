// SPDX-License-Identifier: Apache-2.0
//! Joining a box by its join link or a typed code (issue #717), without a pasted token.
//!
//! 1. Where and whom: the link (joinlink.rs) gives the box's addresses and the sha256 of its CA;
//!    a typed code comes with the box address and that fingerprint, which is required.
//! 2. Pin: the app downloads `/v1/tls/ca.crt` (public, like on the phone) and keeps it only if its
//!    sha256 is the fingerprint. A different CA on any address stops the join: nothing is sent.
//! 3. From then on every request to that box uses a client that trusts only that CA, so the box's
//!    own certificate must chain to it and name the box (no system CA, no other box).
//! 4. Sign in over the pinned connection (password, or the owner's enrolment code), and keep the
//!    access and refresh tokens in the OS keychain (store.rs), never in a file or the web view.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::Duration;

use crate::{api, joinlink};

/// Where to join and which CA to pin.
#[derive(Debug, Clone, PartialEq)]
pub struct Target {
    /// Addresses to try in order: hub, then the mDNS name on the hub's port, then the away address.
    pub bases: Vec<String>,
    pub ca_sha256: String,
}

/// What the person entered: a link, or a typed code with the box address and CA fingerprint.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct JoinInput {
    #[serde(default)]
    pub link: String,
    #[serde(default)]
    pub code: String,
    #[serde(default)]
    pub address: String,
    #[serde(default)]
    pub ca: String,
}

/// How to sign in once the box is pinned.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct SignIn {
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub password: String,
    #[serde(default)]
    pub totp: String,
    /// The enrolment code an owner made for this person (`POST /v1/auth/enrol`).
    #[serde(default)]
    pub enrol_code: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Tokens {
    pub access_token: String,
    pub refresh_token: String,
}

fn port_of(base: &str) -> String {
    let host = base.trim_start_matches("https://");
    host.rsplit_once(':').map(|(_, p)| format!(":{p}")).unwrap_or_default()
}

fn is_fingerprint(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|c| c.is_ascii_hexdigit())
}

/// Reads the link or the typed code. Refuses a link for another kind of device and any join
/// without a CA fingerprint to pin.
pub fn target(input: &JoinInput) -> Result<Target, String> {
    let link = input.link.trim();
    if !link.is_empty() {
        let l = joinlink::parse(link).map_err(|e| format!("join_link_{}", e.reason))?;
        if l.kind != "desktop" {
            return Err("join_link_not_desktop".into());
        }
        let mut bases = vec![l.hub.clone()];
        if !l.mdns.is_empty() {
            bases.push(format!("https://{}{}", l.mdns, port_of(&l.hub)));
        }
        if !l.alt.is_empty() {
            bases.push(l.alt.clone());
        }
        bases.dedup();
        return Ok(Target { bases, ca_sha256: l.ca });
    }
    if input.code.trim().is_empty() {
        return Err("join_missing".into());
    }
    let ca = input.ca.trim().to_ascii_lowercase().replace([':', ' '], "");
    if !is_fingerprint(&ca) {
        return Err("ca_pin_missing".into());
    }
    let (base, insecure) = crate::address::normalize(&input.address, false).map_err(|e| e.code().to_string())?;
    if insecure || !base.starts_with("https://") {
        return Err("needs_https".into());
    }
    Ok(Target { bases: vec![base], ca_sha256: ca })
}

pub fn sha256_hex(b: &[u8]) -> String {
    Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect()
}

pub fn from_hex(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(s.get(i..i + 2)?, 16).ok()).collect()
}

/// For the one CA download only: the CA is not trusted yet, so the connection is not either;
/// what is kept is checked against the fingerprint instead. No token or password goes over it.
pub fn probe_client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(6))
        .connect_timeout(Duration::from_secs(3))
        .tls_danger_accept_invalid_certs(true)
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("http client")
}

/// A client that trusts only the pinned CA (DER). `stream` is for `GET /v1/events`.
pub fn pinned_client(ca_der: &[u8], stream: bool) -> Result<reqwest::Client, String> {
    let cert = reqwest::Certificate::from_der(ca_der).map_err(|_| "ca_invalid".to_string())?;
    let mut h = reqwest::header::HeaderMap::new();
    h.insert(api::API_VERSION_HEADER, reqwest::header::HeaderValue::from_static("1"));
    let b = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(if stream { 5 } else { 3 }))
        .user_agent(concat!("onemind-desktop/", env!("CARGO_PKG_VERSION")))
        .default_headers(h)
        .redirect(reqwest::redirect::Policy::none())
        .https_only(true)
        .tls_certs_only([cert]);
    let b = if stream { b.read_timeout(Duration::from_secs(45)) } else { b.timeout(Duration::from_secs(6)) };
    b.build().map_err(|_| "ca_invalid".to_string())
}

#[derive(Debug, PartialEq)]
pub enum PinError {
    /// Nothing answered at this address: try the next one.
    Unreachable,
    /// Something answered with another CA: stop the whole join.
    Mismatch,
}

/// Downloads the box CA from `base` and returns it only if its sha256 is the fingerprint.
pub async fn fetch_ca(c: &reqwest::Client, base: &str, ca_sha256: &str) -> Result<Vec<u8>, PinError> {
    let resp = c.get(format!("{base}/v1/tls/ca.crt")).send().await.map_err(|_| PinError::Unreachable)?;
    if !resp.status().is_success() {
        return Err(PinError::Mismatch);
    }
    let der = resp.bytes().await.map_err(|_| PinError::Unreachable)?;
    if der.len() > 16 * 1024 || sha256_hex(&der) != ca_sha256 {
        return Err(PinError::Mismatch);
    }
    Ok(der.to_vec())
}

/// Tries each address; the first that serves the pinned CA wins. A wrong CA anywhere stops.
pub async fn pin(c: &reqwest::Client, t: &Target) -> Result<(String, Vec<u8>), String> {
    for base in &t.bases {
        match fetch_ca(c, base, &t.ca_sha256).await {
            Ok(der) => return Ok((base.clone(), der)),
            Err(PinError::Mismatch) => return Err("ca_mismatch".into()),
            Err(PinError::Unreachable) => continue,
        }
    }
    Err("unreachable".into())
}

fn tokens_of(v: &Value) -> Result<Tokens, String> {
    let s = |k: &str| v.get(k).and_then(|x| x.as_str()).filter(|x| !x.is_empty()).map(str::to_string);
    match (s("access_token"), s("refresh_token")) {
        (Some(access_token), Some(refresh_token)) => Ok(Tokens { access_token, refresh_token }),
        _ => Err("bad_response".into()),
    }
}

async fn post_open(c: &reqwest::Client, base: &str, path: &str, body: &Value) -> Result<Value, String> {
    let resp = c.post(format!("{base}{path}")).json(body).send().await.map_err(|_| "unreachable".to_string())?;
    let status = resp.status().as_u16();
    let v: Value = resp.json().await.unwrap_or(Value::Null);
    if (200..300).contains(&status) {
        return Ok(v);
    }
    Err(api::refusal(status, &v).code())
}

/// Signs in over the pinned client: the enrolment code when given, else username and password.
/// `client: "app"` asks for bearer tokens (no browser cookie).
pub async fn sign_in(c: &reqwest::Client, base: &str, s: &SignIn) -> Result<Tokens, String> {
    if s.password.is_empty() {
        return Err("password_missing".into());
    }
    let v = if !s.enrol_code.trim().is_empty() {
        let body = json!({"code": s.enrol_code.trim(), "username": s.username.trim(), "password": s.password, "client": "app"});
        post_open(c, base, "/v1/auth/enrol", &body).await?
    } else {
        let mut body = json!({"username": s.username.trim(), "password": s.password, "client": "app", "client_name": "OneMind desktop"});
        if !s.totp.trim().is_empty() {
            body["totp"] = json!(s.totp.trim());
        }
        post_open(c, base, "/v1/auth/login", &body).await?
    };
    tokens_of(&v)
}

/// Trades the refresh token for a new pair (`POST /v1/auth/refresh`); the old one stops working.
pub async fn refresh(c: &reqwest::Client, base: &str, refresh_token: &str) -> Result<Tokens, String> {
    tokens_of(&post_open(c, base, "/v1/auth/refresh", &json!({"refresh_token": refresh_token})).await?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};

    const CA: &[u8] = b"not a real certificate, only bytes to hash";
    const CODE: &str = "7KQ4-M2XP-9D3F";

    fn link(kind: &str, ca: &str) -> String {
        format!("onemind-join:v2?hub=https%3A%2F%2Fbox1.local%3A8443&alt=https%3A%2F%2Fbox1.example.net&mdns=box1.local&ca={ca}&code={CODE}&kind={kind}")
    }

    /// A test-only hub stand-in on loopback: serves the CA bytes and the sign-in routes, and
    /// records every request line and body it got.
    fn hub(ca: &'static [u8]) -> (String, Arc<Mutex<Vec<String>>>) {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", l.local_addr().unwrap());
        let seen = Arc::new(Mutex::new(Vec::new()));
        let log = seen.clone();
        std::thread::spawn(move || {
            for s in l.incoming() {
                let Ok(mut s) = s else { continue };
                let mut buf = vec![0u8; 16384];
                let n = s.read(&mut buf).unwrap_or(0);
                let req = String::from_utf8_lossy(&buf[..n]).to_string();
                let line = req.lines().next().unwrap_or_default().to_string();
                let body = req.split("\r\n\r\n").nth(1).unwrap_or_default().to_string();
                log.lock().unwrap().push(format!("{line} {body}"));
                let (status, ctype, out): (&str, &str, Vec<u8>) = if line.starts_with("GET /v1/tls/ca.crt") {
                    ("200 OK", "application/x-x509-ca-cert", ca.to_vec())
                } else if line.starts_with("POST /v1/auth/") && body.contains("\"password\":\"right\"") {
                    ("201 Created", "application/json", br#"{"access_token":"ses_a","refresh_token":"ref_b","expires_at":"x"}"#.to_vec())
                } else {
                    ("401 Unauthorized", "application/json", br#"{"error":"unauthenticated","message":"no"}"#.to_vec())
                };
                let head = format!("HTTP/1.1 {status}\r\ncontent-type: {ctype}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n", out.len());
                let _ = s.write_all(head.as_bytes());
                let _ = s.write_all(&out);
            }
        });
        (base, seen)
    }

    #[test]
    fn a_desktop_link_gives_every_address_and_the_pin() {
        let ca = sha256_hex(CA);
        let t = target(&JoinInput { link: link("desktop", &ca), ..Default::default() }).unwrap();
        // the mDNS name on the hub port is the hub address here, so it is tried once
        assert_eq!(t.bases, vec!["https://box1.local:8443".to_string(), "https://box1.example.net".to_string()]);
        assert_eq!(t.ca_sha256, ca);
    }

    #[test]
    fn refuses_other_devices_and_joins_without_a_pin() {
        let ca = sha256_hex(CA);
        let link_of = |k: &str| JoinInput { link: link(k, &ca), ..Default::default() };
        assert_eq!(target(&link_of("worker")).unwrap_err(), "join_link_not_desktop");
        assert_eq!(target(&link_of("phone")).unwrap_err(), "join_link_not_desktop");
        assert_eq!(target(&JoinInput { link: "https://box1.local".into(), ..Default::default() }).unwrap_err(), "join_link_prefix");
        let typed = |ca: &str, address: &str| JoinInput { code: CODE.into(), address: address.into(), ca: ca.into(), ..Default::default() };
        assert_eq!(target(&typed("", "box1.local:8443")).unwrap_err(), "ca_pin_missing");
        assert_eq!(target(&typed("abc", "box1.local:8443")).unwrap_err(), "ca_pin_missing");
        assert_eq!(target(&typed(&ca, "http://box1.local")).unwrap_err(), "needs_https");
        assert_eq!(target(&typed(&ca, "http://127.0.0.1:8080")).unwrap_err(), "needs_https");
        let ok = target(&typed(&ca.to_ascii_uppercase(), "box1.local:8443")).unwrap();
        assert_eq!((ok.bases, ok.ca_sha256), (vec!["https://box1.local:8443".to_string()], ca));
        assert_eq!(target(&JoinInput::default()).unwrap_err(), "join_missing");
    }

    #[tokio::test(flavor = "current_thread")]
    async fn pins_only_the_ca_from_the_link_and_then_signs_in() {
        let (base, seen) = hub(CA);
        let c = probe_client();
        let good = Target { bases: vec!["http://127.0.0.1:1".into(), base.clone()], ca_sha256: sha256_hex(CA) };
        let (at, der) = pin(&c, &good).await.unwrap();
        assert_eq!((at.as_str(), der.as_slice()), (base.as_str(), CA));

        let wrong = Target { bases: vec![base.clone(), "http://127.0.0.1:1".into()], ca_sha256: sha256_hex(b"another CA") };
        assert_eq!(pin(&c, &wrong).await.unwrap_err(), "ca_mismatch");
        assert!(!seen.lock().unwrap().iter().any(|l| l.starts_with("POST")), "nothing is sent to a box with another CA");

        let s = SignIn { username: "ana".into(), password: "right".into(), ..Default::default() };
        let t = sign_in(&c, &base, &s).await.unwrap();
        assert_eq!(t, Tokens { access_token: "ses_a".into(), refresh_token: "ref_b".into() });
        let e = SignIn { username: "ana".into(), password: "right".into(), enrol_code: "EN-1".into(), ..Default::default() };
        assert!(sign_in(&c, &base, &e).await.is_ok());
        let bad = SignIn { username: "ana".into(), password: "wrong".into(), ..Default::default() };
        assert_eq!(sign_in(&c, &base, &bad).await.unwrap_err(), "unauthorized");
        let log = seen.lock().unwrap().join("\n");
        assert!(log.contains("POST /v1/auth/login") && log.contains("\"client\":\"app\""), "{log}");
        assert!(log.contains("POST /v1/auth/enrol") && log.contains("\"code\":\"EN-1\""), "{log}");
    }

    #[test]
    fn pinned_client_needs_a_real_certificate_and_hex_round_trips() {
        assert_eq!(pinned_client(b"junk", false).unwrap_err(), "ca_invalid");
        assert_eq!(from_hex("00ff10"), Some(vec![0, 255, 16]));
        assert_eq!(from_hex("0g"), None);
        assert_eq!(from_hex("abc"), None);
    }
}
