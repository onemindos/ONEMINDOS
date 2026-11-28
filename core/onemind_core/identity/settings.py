# SPDX-License-Identifier: Apache-2.0
"""Identity settings: ONEMIND_IDENTITY_* (docs/leap/core/IDENTITY.md §6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..sections import config_section


@config_section("identity")
@dataclass(frozen=True)
class IdentitySettings:
    # WebAuthn relying party. Empty rp_id = the request's host name; empty origins = https://<rp_id>[:port],
    # plus http:// for localhost (browsers allow WebAuthn there without TLS).
    rp_id: str | None = None
    rp_name: str = "OneMind"
    origins: tuple[str, ...] = ()
    # Browser sessions: idle timeout and absolute lifetime.
    session_idle_hours: int = 72
    session_max_days: int = 30
    # CLI and app sessions: short bearer access token plus a rotating refresh token.
    access_token_minutes: int = 60
    refresh_days: int = 30
    # Cookies carry Secure; turn off only for a plain-HTTP dev box (browsers keep Secure cookies on localhost).
    cookie_secure: bool = True
    # Retain the existing policy of an action-bound assertion even for low-risk approvals in a
    # passkey session. Password and authenticator sessions are governed by D-034's verification levels.
    require_passkey_approval: bool = True
    # #702 / F-2 (not yet decided): a phone's device-bound approver key may approve destructive and
    # actuate requests only when this is on. Off: those still need a passkey. Physical actions always do.
    approver_key_high_risk: bool = False
    # §12.6 / F-14: role default scopes for sessions. Static-file tokens always keep v0 behaviour.
    enforce_role_scopes: bool = True
    # Immediately offer the box code for eligible actions before the first proven key, as in D-028.
    # D-034 also lets someone on the home network explicitly choose the box route for L2.
    l2_grace: bool = True
    # The file the gateway writes and onemind-screen reads. Without a screen, L2 needs a proven key.
    box_code_file: Path | None = None
    # Optional RAM-only disk unlock key delivered to the setup owner with the sign-in recovery kit.
    recovery_key_file: Path | None = None
    # Appliance boot's authoritative encrypted/plain status. Missing status or key blocks encrypted setup.
    recovery_disk_state_file: Path | None = None
    # The authenticator allow-list; empty = the file shipped with the gateway (identity/levels.py).
    allowlist_file: Path | None = None
    # How recently the person must have proved L1.
    step_up_s: int = 300
    # §12.1: failed logins per source per minute before a back-off.
    login_failures_per_min: int = 10
    lockout_minutes: int = 15
    # Optional first-boot token (a file holding one line) accepted by POST /v1/auth/setup besides an
    # owner token from ONEMIND_TOKENS_FILE. Read at request time; never logged.
    setup_token_file: Path | None = None

    def validate(self) -> None:
        for name in ("session_idle_hours", "session_max_days", "access_token_minutes", "refresh_days",
                     "step_up_s", "login_failures_per_min", "lockout_minutes"):
            if getattr(self, name) < 1:
                raise ValueError(f"ONEMIND_IDENTITY_{name.upper()} must be at least 1")
        for origin in self.origins:
            if not origin.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                raise ValueError("ONEMIND_IDENTITY_ORIGINS entries must be https:// (http only on localhost)")
