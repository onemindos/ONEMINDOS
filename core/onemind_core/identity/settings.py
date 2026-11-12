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
    # §12.3 / F-2: once an owner has a passkey, every owner approval needs an assertion.
    require_passkey_approval: bool = True
    # §12.6 / F-14: role default scopes for sessions. Static-file tokens always keep v0 behaviour.
    enforce_role_scopes: bool = True
    # How recent a passkey sign-in must be for user, passkey and access administration.
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
