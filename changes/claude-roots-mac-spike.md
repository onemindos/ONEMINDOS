---
pr: 960
branch: claude/roots-mac-spike
---
Mac spike (#705): desktop-mac/ holds an Xcode project with a SwiftUI host app and a replicated File Provider extension that shows OneMind read-only under Finder Locations, listing GET /v1/files/list and downloading with Range on a typed dev token; it refuses writes and refuses to start without a token. A tiny Rust UniFFI library links into the extension. 19 XCTest cases; the README records the result, the UNVERIFIED Developer ID and app-group answers, and the founder's lab kit.
