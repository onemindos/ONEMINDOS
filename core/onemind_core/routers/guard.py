# SPDX-License-Identifier: Apache-2.0
"""Hardening that wraps every route: limits, security headers, startup refusals (guard.py).

Adds no routes. Also refuses to start the kubernetes executor without the app manifest schema
(H-18: the built-in check is for development only).
"""

from __future__ import annotations

from fastapi import FastAPI

from ..context import Gateway
from ..guard import GuardMiddleware, LimitSettings


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    if settings.executor == "kubernetes" and (settings.app_schema_path is None or not settings.app_schema_path.is_file()):
        raise ValueError(
            "the kubernetes executor needs the app manifest schema (ONEMIND_APP_SCHEMA); "
            "the built-in manifest check is for development only"
        )
    limits = settings.section(LimitSettings)
    gw.actions.max_pending_per_requester = limits.max_pending

    def on_backoff(source: str) -> None:
        gw.audit.append(
            "auth.backoff", None, None,
            {"source": source, "backoff_s": limits.auth_backoff_s, "failures_per_min": limits.auth_failures_per_min},
        )

    app.add_middleware(GuardMiddleware, limits=limits, on_backoff=on_backoff)
