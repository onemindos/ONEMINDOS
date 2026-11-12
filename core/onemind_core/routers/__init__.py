# SPDX-License-Identifier: Apache-2.0
"""Route groups of the gateway, one module per feature area (docs/leap/core/PLUMBING.md §2).

Each module exposes `register(app: FastAPI, gw: Gateway) -> None`. app.py keeps the ordered
registry (ROUTERS); `static` stays last because its SPA fallback matches every path.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from ..context import Gateway

Register = Callable[[FastAPI, Gateway], None]
