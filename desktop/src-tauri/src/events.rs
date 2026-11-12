// SPDX-License-Identifier: Apache-2.0
//! The box's live event stream (contract §12.8 `GET /v1/events`, server-sent events). The tray
//! uses it only as a wake-up: an event of a relevant type triggers a status refresh over REST,
//! so a new approval request shows within a second or two instead of at the next 20 s poll.
//! Event data is never shown or trusted as state. A box without the route answers 404 and the
//! tray keeps polling.

/// Event types that change what the tray shows. The box filters by `types`; older boxes may
/// ignore the filter, so `wakes` checks again.
pub const PATH: &str = "/v1/events?types=action.*,notification.created,alert.*,node.status,backup.health,os.update.state";

/// One line, or one event's data, longer than this ends the stream (and it is reopened later).
pub const MAX_PENDING: usize = 1 << 20;
pub const MIN_WAIT: u64 = 2;
pub const MAX_BACKOFF: u64 = 60;

#[derive(Debug, Clone, PartialEq)]
pub struct Event {
    /// The last event id seen on this stream (sent back as `Last-Event-ID` on reconnect).
    pub id: Option<String>,
    pub kind: String,
    pub data: String,
}

#[derive(Debug, PartialEq)]
pub struct TooLong;

/// Incremental parser for `text/event-stream` (WHATWG HTML §9.2), the parts the box uses:
/// `id`, `event`, `data`, comments (`: keepalive`), LF or CRLF line ends.
#[derive(Default)]
pub struct Parser {
    buf: Vec<u8>,
    last_id: Option<String>,
    kind: Option<String>,
    data: String,
    has_data: bool,
}

impl Parser {
    pub fn push(&mut self, chunk: &[u8]) -> Result<Vec<Event>, TooLong> {
        self.buf.extend_from_slice(chunk);
        let mut out = Vec::new();
        while let Some(pos) = self.buf.iter().position(|&b| b == b'\n') {
            let mut line: Vec<u8> = self.buf.drain(..=pos).collect();
            line.pop();
            if line.last() == Some(&b'\r') {
                line.pop();
            }
            let line = String::from_utf8_lossy(&line).into_owned();
            self.line(&line, &mut out);
            if self.data.len() > MAX_PENDING {
                return Err(TooLong);
            }
        }
        if self.buf.len() > MAX_PENDING {
            return Err(TooLong);
        }
        Ok(out)
    }

    pub fn last_id(&self) -> Option<&str> {
        self.last_id.as_deref()
    }

    fn line(&mut self, line: &str, out: &mut Vec<Event>) {
        if line.is_empty() {
            if self.has_data {
                let mut data = std::mem::take(&mut self.data);
                if data.ends_with('\n') {
                    data.pop();
                }
                out.push(Event { id: self.last_id.clone(), kind: self.kind.take().unwrap_or_else(|| "message".into()), data });
            }
            self.kind = None;
            self.data.clear();
            self.has_data = false;
            return;
        }
        if line.starts_with(':') {
            return;
        }
        let (field, value) = match line.split_once(':') {
            Some((f, v)) => (f, v.strip_prefix(' ').unwrap_or(v)),
            None => (line, ""),
        };
        match field {
            "event" => self.kind = Some(value.to_string()),
            "data" => {
                self.data.push_str(value);
                self.data.push('\n');
                self.has_data = true;
            }
            "id" if !value.contains('\0') => self.last_id = Some(value.to_string()),
            _ => {}
        }
    }
}

/// Does this event type change what the tray shows?
pub fn wakes(kind: &str) -> bool {
    kind.starts_with("action.")
        || kind.starts_with("alert.")
        || matches!(
            kind,
            "notification.created" | "node.status" | "node.joined" | "node.removed" | "node.degraded" | "backup.health" | "os.update.state" | "stream.reset"
        )
}

/// Seconds to wait before reopening the stream. `None`: the connection failed.
pub fn wait_after(status: Option<u16>, backoff: u64) -> u64 {
    match status {
        // A stream that ran and closed: reopen soon.
        Some(200) => MIN_WAIT,
        // The box does not serve events yet: polling covers it; look again in 5 minutes.
        Some(404) => 300,
        // Token refused, or this token may not read events: do not hammer the box.
        Some(401 | 403) => 120,
        Some(429) => 60,
        _ => backoff.clamp(MIN_WAIT, MAX_BACKOFF),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_contract_example_in_pieces() {
        let wire = "id: 18342\nevent: action.state_changed\ndata: {\"schema\":\"onemind.event/v1\",\"id\":\"18342\"}\n\n: keepalive\n\n";
        let mut p = Parser::default();
        let mut all = Vec::new();
        for piece in wire.as_bytes().chunks(7) {
            all.extend(p.push(piece).unwrap());
        }
        assert_eq!(all, vec![Event { id: Some("18342".into()), kind: "action.state_changed".into(), data: "{\"schema\":\"onemind.event/v1\",\"id\":\"18342\"}".into() }]);
        assert_eq!(p.last_id(), Some("18342"));
    }

    #[test]
    fn crlf_multiline_data_and_default_type() {
        let mut p = Parser::default();
        let ev = p.push(b"data: a\r\ndata: b\r\n\r\nid: 7\r\n\r\n").unwrap();
        assert_eq!(ev, vec![Event { id: None, kind: "message".into(), data: "a\nb".into() }]);
        assert_eq!(p.last_id(), Some("7"), "an id with no data still moves Last-Event-ID");
    }

    #[test]
    fn refuses_unbounded_lines() {
        let mut p = Parser::default();
        assert_eq!(p.push(&vec![b'x'; MAX_PENDING + 1]), Err(TooLong));
    }

    #[test]
    fn wake_types() {
        for k in ["action.requested", "action.state_changed", "alert.opened", "notification.created", "stream.reset", "node.status"] {
            assert!(wakes(k), "{k}");
        }
        for k in ["audit.appended", "automation.fired", "message", ""] {
            assert!(!wakes(k), "{k}");
        }
    }

    #[test]
    fn retry_policy() {
        assert_eq!(wait_after(Some(404), 2), 300);
        assert_eq!(wait_after(Some(401), 2), 120);
        assert_eq!(wait_after(Some(200), 32), MIN_WAIT);
        assert_eq!(wait_after(None, 500), MAX_BACKOFF);
        assert_eq!(wait_after(Some(502), 8), 8);
    }
}
