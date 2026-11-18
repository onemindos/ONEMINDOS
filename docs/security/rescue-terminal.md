<!-- SPDX-License-Identifier: Apache-2.0 -->
# Threat model: the owner-only web terminal (SEC-TERM-01, #273)

**Status:** built and tested, **not reachable on any box**. The shell opens only after a fresh passkey sign-in, and passkeys do not exist yet (#236, Kanidm). Until they do, every start is refused with 503. **Decision:** D-014 (web terminal = yes, narrowly), amended 2026-11-15: build now, keep it disabled until passkeys, never behind the plain owner token. Code: `internal/rescue/terminal.go`, `audit.go`, `pty_linux.go`.

## What it is
A page in the rescue console (`onemindd rescue`, :7443, its own process and unit) that opens a root shell on the box. A shell is the most powerful thing on the machine, so the point of this note is what stops anyone but the owner, at a chosen moment, from getting one.

## The gates, in order
Each gate is a refusal; a request must pass all of them. Tests: `internal/rescue/terminal_test.go`.

| # | Gate | Refusal | Why |
|---|---|---|---|
| 1 | LAN only, owner token | 403 for public and mesh clients; 401 without the owner token | The console's existing check (CORE-UPDATE-8, D-008). |
| 1b | Valid credential that is not the owner's (an agent token, a non-owner person) | **403**, and a `terminal.denied` line on the chain | AI never actuates, and no agent may ever hold a shell. The credential is real, so 403, not 401. |
| 2 | The switch file `/etc/onemind/rescue-terminal.on` exists and nobody but its owner can write it | 404 | Off by default. The owner turns it on with `onemindd rescue terminal enable` (root on the box). Each change is on the chain first. |
| 3 | A fresh passkey assertion for this request (`Reauther`) | 401 stale; **503 when the box has no passkey support (today)** | D-014: not behind the plain owner token. Production wires no `Reauther`, so the terminal cannot open yet. |
| 4 | The `terminal.start` line is written and synced | 500, no shell | Fail closed: no record, no shell. |
| 5 | CSRF header and same-origin on every write | 403 | A page open in the same browser cannot start or type into a session with the cached password. |

Also: one session at a time (409), input of at most 4 KiB per request, a 10 minute idle timeout and a 1 hour hard cap, the page's script runs only with a per-response nonce (`script-src 'nonce-...'`, no `unsafe-inline`, no `unsafe-eval`).

## Not reachable by agents, the SDK or AI tools
The terminal exists only in the rescue process. It is not a gateway route, so it is not in `sdk/openapi/onemind-v1.json`, the generated SDKs, the MCP catalogue or the capability gateway's tools. A test greps the OpenAPI document and the gateway code for it. An agent that holds the owner's token is outside this model (the token is the owner's); gate 3 is what protects against that: a token alone, stolen or leaked, still cannot open a shell.

## Audit
`/var/lib/onemind/rescue-audit.jsonl` is a hash chain in the gateway's line format (`core/onemind_core/audit.py`), so `onemind-audit-verify` checks it; a test cross-checks our lines against the Python verifier. Events: `terminal.start` (session id, client address, passkey credential id), `terminal.end` (session, reason: `owner-closed`, `shell-exited`, `idle-timeout`, `max-duration`; seconds, bytes in and out), `terminal.denied`, `terminal.switch`. It is a separate file from the gateway's chain on purpose: the console must work with the gateway down, and two writers would fork the sequence. A chain that does not verify is never appended to, and then no shell opens.

**Keystrokes are not recorded.** The decision, with reasons: the chain cannot be edited, so a password or key typed into a shell would be kept for good and readable by anyone who can read the log; a recording gives a second place to leak secrets from; and a root shell can edit any log a recorder writes to the same box, so a local recording proves little. What is recorded is who (passkey), from where, when, how long and how much. If the founder wants session recording, it needs to go to a place the shell cannot write (the hub), with redaction; that is a separate decision.

## Residual risks and gaps
- **Passkeys do not exist (#236).** Until a `Reauther` is wired, the terminal is dead code on purpose. The "owner opens a shell on a real image" box in #273 stays open until then.
- **The unit's sandbox blocks a shell.** `onemind-rescue.service` has `PrivateDevices=yes` (no `/dev/ptmx`), `NoNewPrivileges`, an almost empty capability set and a syscall filter, so a shell started from it is useless. Opening a real root shell needs a looser unit or a separate one, with `ReadWritePaths=` for the audit file; that is a design choice for the Opus gate, taken when passkeys land. The PTY code was run in a Debian container, not under that unit.
- **It is a root shell.** Anyone who passes all gates can do anything on the box, including edit `/var/lib/onemind/rescue-audit.jsonl`. The chain detects edits; it cannot prevent them. Shipping the lines to the hub is the stronger answer (later).
- **Line-mode page.** The browser side is a plain text box with Send and Ctrl-C, no full-screen programs (`vim`, `top`). A real terminal emulator needs a vendored library and its own review.
- **The switch is a file on the box, not a dashboard setting.** The issue says "the owner turns it on in settings"; the dashboard cannot write to a host file, so that needs a gateway to console channel. The CLI is the first slice.
- **Not run on a real image.** Unit tests, a PTY test in a Debian arm64 container, no QEMU battery run.
