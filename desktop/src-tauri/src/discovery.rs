// SPDX-License-Identifier: Apache-2.0
//! Finding boxes on the local network: browse `_onemind._tcp` over mDNS for a few seconds,
//! and also try the well-known name `onemind.local`. Discovery only suggests an address;
//! it creates no trust. Pairing (a token today, an owner-approved device request later)
//! is what makes a box "yours".

use mdns_sd::{ServiceDaemon, ServiceEvent};
use serde::Serialize;
use std::collections::BTreeMap;
use std::time::{Duration, Instant};

pub const SERVICE: &str = "_onemind._tcp.local.";
pub const WELL_KNOWN: &str = "onemind.local";
pub const DEFAULT_PORT: u16 = 8080;

#[derive(Debug, Clone, Serialize)]
pub struct Found {
    pub name: String,
    pub url: String,
    /// Random instance id from the TXT record (`id`), if the box advertises one.
    pub instance_id: Option<String>,
    /// `mdns` or `well_known`.
    pub via: String,
}

/// Browse for `window`, blocking (run it on a blocking thread).
pub fn browse(window: Duration) -> Vec<Found> {
    let mut out: BTreeMap<String, Found> = BTreeMap::new();
    let Ok(daemon) = ServiceDaemon::new() else { return Vec::new() };
    let Ok(rx) = daemon.browse(SERVICE) else { return Vec::new() };
    let deadline = Instant::now() + window;
    while let Some(left) = deadline.checked_duration_since(Instant::now()) {
        match rx.recv_timeout(left) {
            Ok(ServiceEvent::ServiceResolved(info)) => {
                let host = info.get_hostname().trim_end_matches('.').to_string();
                let port = info.get_port();
                let scheme = if port == 443 || info.get_property_val_str("tls") == Some("1") { "https" } else { "http" };
                let url = if (scheme == "https" && port == 443) || (scheme == "http" && port == 80) {
                    format!("{scheme}://{host}")
                } else {
                    format!("{scheme}://{host}:{port}")
                };
                let name = info
                    .get_fullname()
                    .trim_end_matches(SERVICE)
                    .trim_end_matches('.')
                    .to_string();
                out.insert(url.clone(), Found {
                    name: if name.is_empty() { host.clone() } else { name },
                    url,
                    instance_id: info.get_property_val_str("id").map(str::to_string),
                    via: "mdns".into(),
                });
            }
            Ok(_) => {}
            Err(_) => break,
        }
    }
    let _ = daemon.stop_browse(SERVICE);
    let _ = daemon.shutdown();
    out.into_values().collect()
}

/// Is a gateway answering `/healthz` at this base URL?
pub async fn probe(c: &reqwest::Client, base: &str) -> bool {
    match c.get(format!("{base}/healthz")).timeout(Duration::from_secs(2)).send().await {
        Ok(r) => r.status().is_success(),
        Err(_) => false,
    }
}

/// Candidate URLs for the well-known name, HTTPS first.
pub fn well_known_candidates() -> [String; 2] {
    [
        format!("https://{WELL_KNOWN}:{DEFAULT_PORT}"),
        format!("http://{WELL_KNOWN}:{DEFAULT_PORT}"),
    ]
}

/// `cargo test -- --ignored live_mdns` with a `_onemind._tcp` service advertised on the LAN
/// (for example `dns-sd -P "Test box" _onemind._tcp local 8080 onemind.local 127.0.0.1 id=t v=1`).
#[cfg(test)]
mod live {
    #[test]
    #[ignore]
    fn live_mdns() {
        let found = super::browse(std::time::Duration::from_secs(3));
        println!("{found:#?}");
        assert!(!found.is_empty(), "no _onemind._tcp service found");
    }
}
