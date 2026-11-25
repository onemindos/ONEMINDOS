# SPDX-License-Identifier: Apache-2.0
"""The dashboard's static files with SPA fallback. Registered last: it matches every path."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException

from ..browsers import browser_spec
from ..context import Gateway
from ..errors import ApiError, allowed_methods
from ..guard import csp_with_frames
from ..netconf import NetSettings

# Paths the SPA fallback never answers: the API tree (whole segment) and the open meta routes.
API_TREES = ("v1",)
API_EXACT = ("healthz", "openapi.json", "mcp")


def is_api_path(full_path: str) -> bool:
    return full_path in API_EXACT or any(full_path == p or full_path.startswith(p + "/") for p in API_TREES)


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 10000  # last: its SPA fallback matches every path


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    dist = settings.dashboard_dist.resolve() if settings.dashboard_dist else None
    net = settings.section(NetSettings)

    def index_headers() -> dict[str, str]:
        """The dashboard page may frame a person's browser host (<app>--<key>.<box domain>, #692)."""
        headers = {"Cache-Control": "no-cache"}
        if any(browser_spec(e.manifest) is not None for e in gw.catalog.load().values()):
            scheme = "https" if net.tls else "http"
            headers["Content-Security-Policy"] = csp_with_frames(tuple(f"{scheme}://*.{d}" for d in net.box_domains()))
        return headers

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str, request: Request):
        if is_api_path(full_path) and allowed_methods(request):
            # GET on an API path that exists for other methods (POST .../approve): 405 with Allow,
            # not 404 (RFC 9110 §15.5.6; finding F-API-2).
            raise HTTPException(405)
        if is_api_path(full_path) or dist is None or not dist.is_dir():
            raise ApiError(404, "not_found", "no such resource")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        # A missing file that looks like an asset is a real 404, not the SPA shell.
        if "." in Path(full_path).name:
            raise ApiError(404, "not_found", "no such file")
        index = dist / "index.html"
        if not index.is_file():
            raise ApiError(404, "not_found", "dashboard not built")
        return FileResponse(index, headers=index_headers())
