// SPDX-License-Identifier: Apache-2.0
//! The join link the owner's box shows (`onemind-join:v2?hub=…&ca=…&code=…&kind=desktop`,
//! docs/architecture/FABRIC.md §4.3), read exactly as core/onemind_core/fabric.py parse_join_qr,
//! internal/fabric/join.go ParseQR and sdk/ts parseJoinQR read it: the shared vectors in
//! sdk/testdata/join-qr/vectors.json are the test. A refusal carries the same reason word in every
//! language. The link gives the desktop app the box's addresses and the sha256 of its CA, which the
//! app pins (pin.rs) before it sends anything.

pub const MAX_LEN: usize = 640;
pub const KINDS: [&str; 6] = ["worker", "leaf", "phone", "desktop", "browser", "sensor"];

#[derive(Debug, Clone, PartialEq, Default)]
pub struct JoinLink {
    pub version: u8,
    pub code: String,
    /// sha256 of the box CA certificate (DER), 64 lower-case hex characters.
    pub ca: String,
    pub hub: String,
    /// The v2 kind, or the v1 role (may be empty in v1).
    pub kind: String,
    pub alt: String,
    pub mdns: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Refused {
    pub reason: &'static str,
}

fn no(reason: &'static str) -> Refused {
    Refused { reason }
}

fn fields_of(version: u8) -> &'static [&'static str] {
    if version == 1 { &["code", "ca", "role", "hub"] } else { &["hub", "alt", "mdns", "ca", "code", "kind"] }
}

fn required_of(version: u8) -> &'static [&'static str] {
    if version == 1 { &["code", "ca", "hub"] } else { &["hub", "ca", "code", "kind"] }
}

/// Strict percent-decoding: every `%` starts two hex digits; the result is printable ASCII.
fn unescape(v: &str) -> Option<String> {
    let b = v.as_bytes();
    let mut out = String::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        let mut c = b[i];
        if c == b'%' {
            let hex = v.get(i + 1..i + 3)?;
            c = u8::from_str_radix(hex, 16).ok()?;
            if !hex.bytes().all(|h| h.is_ascii_hexdigit()) {
                return None;
            }
            i += 2;
        }
        if !(0x21..=0x7e).contains(&c) {
            return None;
        }
        out.push(c as char);
        i += 1;
    }
    Some(out)
}

fn is_label(l: &str) -> bool {
    let b = l.as_bytes();
    !b.is_empty()
        && b.len() <= 63
        && b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
        && b[0] != b'-'
        && b[b.len() - 1] != b'-'
}

/// `https://host[:port][/]` to `https://host[:port]`, host lower-cased: a DNS name or a dotted-quad
/// IPv4 address; no userinfo, path, query, fragment or IPv6 literal.
fn https(v: &str) -> Option<String> {
    let rest = v.strip_prefix("https://")?;
    let rest = rest.strip_suffix('/').unwrap_or(rest);
    let (host, port) = match rest.split_once(':') {
        Some((h, p)) => (h, Some(p)),
        None => (rest, None),
    };
    if host.is_empty() || host.len() > 253 || !host.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'-') {
        return None;
    }
    if let Some(p) = port {
        let ok = (1..=5).contains(&p.len()) && p.bytes().all(|c| c.is_ascii_digit()) && !p.starts_with('0');
        if !ok || p.parse::<u32>().ok()? > 65535 {
            return None;
        }
    }
    let host = host.to_ascii_lowercase();
    let labels: Vec<&str> = host.split('.').collect();
    if !labels.iter().all(|l| is_label(l)) {
        return None;
    }
    if labels.last()?.bytes().all(|c| c.is_ascii_digit()) {
        let octet = |l: &&str| (l == &"0" || (!l.starts_with('0') && l.len() <= 3)) && l.parse::<u16>().map(|n| n <= 255).unwrap_or(false);
        if labels.len() != 4 || !labels.iter().all(octet) {
            return None;
        }
    }
    Some(match port {
        Some(p) => format!("https://{host}:{p}"),
        None => format!("https://{host}"),
    })
}

/// v1 codes are looser: three groups of four letters or digits, each dash optional.
fn code_v1(c: &str) -> bool {
    let b = c.as_bytes();
    let mut i = 0;
    for group in 0..3 {
        for _ in 0..4 {
            if i >= b.len() || !b[i].is_ascii_alphanumeric() {
                return false;
            }
            i += 1;
        }
        if group < 2 && b.get(i) == Some(&b'-') {
            i += 1;
        }
    }
    i == b.len()
}

fn code_v2(c: &str) -> bool {
    let crockford = |x: u8| x.is_ascii_digit() || (x.is_ascii_uppercase() && !matches!(x, b'I' | b'L' | b'O' | b'U'));
    let b = c.as_bytes();
    b.len() == 14 && b[4] == b'-' && b[9] == b'-' && b.iter().enumerate().all(|(i, x)| i == 4 || i == 9 || crockford(*x))
}

fn is_sha(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn mdns_ok(s: &str) -> bool {
    s.strip_suffix(".local").is_some_and(|l| !l.contains('.') && is_label(l))
}

pub fn parse(payload: &str) -> Result<JoinLink, Refused> {
    if !payload.is_ascii() {
        return Err(no("charset"));
    }
    if payload.len() > MAX_LEN {
        return Err(no("length"));
    }
    let rest = payload.strip_prefix("onemind-join:v").ok_or(no("prefix"))?;
    let digits = rest.bytes().take_while(|c| c.is_ascii_digit()).count();
    if digits == 0 || rest.as_bytes().get(digits) != Some(&b'?') {
        return Err(no("prefix"));
    }
    let version: u8 = match &rest[..digits] {
        "1" => 1,
        "2" => 2,
        _ => return Err(no("version")),
    };
    let mut fields: Vec<(&str, String)> = Vec::new();
    for part in rest[digits + 1..].split('&') {
        let (key, raw) = part.split_once('=').ok_or(no("syntax"))?;
        let key_ok = !key.is_empty() && key.bytes().all(|c| c.is_ascii_lowercase());
        let raw_ok = !raw.is_empty() && raw.bytes().all(|c| c.is_ascii_alphanumeric() || b"._~%:/-".contains(&c));
        let value = if key_ok && raw_ok { unescape(raw) } else { None }.ok_or(no("syntax"))?;
        let known = fields_of(version).iter().find(|k| **k == key).ok_or(no("unknown_field"))?;
        if fields.iter().any(|(k, _)| k == known) {
            return Err(no("duplicate"));
        }
        fields.push((known, value));
    }
    let get = |k: &str| fields.iter().find(|(f, _)| *f == k).map(|(_, v)| v.clone());
    if required_of(version).iter().any(|k| get(k).is_none()) {
        return Err(no("missing_field"));
    }
    let mut t = JoinLink { version, code: get("code").unwrap_or_default(), ca: get("ca").unwrap_or_default(), ..Default::default() };
    if version == 1 {
        t.kind = get("role").unwrap_or_default();
        t.ca = t.ca.to_ascii_lowercase();
        if !code_v1(&t.code) {
            return Err(no("code"));
        }
    } else if !code_v2(&t.code) {
        return Err(no("code"));
    }
    if !is_sha(&t.ca) {
        return Err(no("ca"));
    }
    if version == 1 {
        if !matches!(t.kind.as_str(), "" | "worker" | "leaf") {
            return Err(no("role"));
        }
    } else {
        t.kind = get("kind").unwrap_or_default();
        if !KINDS.contains(&t.kind.as_str()) {
            return Err(no("kind"));
        }
    }
    t.hub = https(&get("hub").unwrap_or_default()).ok_or(no("hub"))?;
    if let Some(a) = get("alt") {
        t.alt = https(&a).ok_or(no("alt"))?;
    }
    if let Some(m) = get("mdns") {
        if !mdns_ok(&m) {
            return Err(no("mdns"));
        }
        t.mdns = m;
    }
    Ok(t)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    const VECTORS: &str = include_str!("../../../sdk/testdata/join-qr/vectors.json");

    #[test]
    fn shared_vectors() {
        // serde_json refuses the lone UTF-16 surrogate of the "lone UTF-16 surrogate" vector (a Rust
        // string cannot hold one either); it stands in for any non-ASCII text, so é keeps the case.
        let text = VECTORS.replace("worker\\ud800\"", "worker\\u00e9\"");
        assert_ne!(text, VECTORS, "the lone-surrogate vector moved; update this test");
        let v: Value = serde_json::from_str(&text).unwrap();
        let s = |x: &Value, k: &str| x[k].as_str().unwrap_or_default().to_string();
        for c in v["valid"].as_array().unwrap() {
            let got = parse(c["payload"].as_str().unwrap()).unwrap_or_else(|e| panic!("{}: refused {}", s(c, "name"), e.reason));
            let e = &c["expect"];
            let want = JoinLink {
                version: e["version"].as_u64().unwrap() as u8,
                code: s(e, "code"),
                ca: s(e, "ca"),
                hub: s(e, "hub"),
                kind: s(e, "kind"),
                alt: s(e, "alt"),
                mdns: s(e, "mdns"),
            };
            assert_eq!(got, want, "{}", s(c, "name"));
        }
        for c in v["hostile"].as_array().unwrap() {
            let got = parse(c["payload"].as_str().unwrap());
            assert_eq!(got.err().map(|e| e.reason), Some(c["reason"].as_str().unwrap()), "{}", s(c, "name"));
        }
    }
}
