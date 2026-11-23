// SPDX-License-Identifier: Apache-2.0
//! The smallest useful shared core: a version string and the gateway-path normaliser a sync client
//! needs on every platform (a path never climbs above the root, "//" and "." collapse).
uniffi::setup_scaffolding!();

#[uniffi::export]
pub fn core_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[uniffi::export]
pub fn normalize_path(raw: String) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for seg in raw.split('/') {
        match seg {
            "" | "." => {}
            ".." => {
                parts.pop();
            }
            s => parts.push(s),
        }
    }
    format!("/{}", parts.join("/"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalises() {
        assert_eq!(
            normalize_path("Docs//a/./b/../c.txt".into()),
            "/Docs/a/c.txt"
        );
        assert_eq!(normalize_path("../../etc".into()), "/etc");
        assert_eq!(normalize_path("".into()), "/");
    }
}
