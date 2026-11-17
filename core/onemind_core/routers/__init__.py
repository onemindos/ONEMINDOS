# SPDX-License-Identifier: Apache-2.0
"""Route groups of the gateway, one module per feature area (docs/leap/core/PLUMBING.md §2).

Each module exposes `register(app: FastAPI, gw: Gateway) -> None` and `ORDER: int`, its place in
the route order (and in /openapi.json). `discover()` finds every module in this package, so a new
feature adds only its own file: no shared list to edit, no merge conflict in app.py (CI-06, #231).
Equal ORDER values run in module-name order. `guard` is ORDER 0 (it wraps every route) and
`static` is the highest (its SPA fallback matches every path).
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

from fastapi import FastAPI

from ..context import Gateway

Register = Callable[[FastAPI, Gateway], None]


def discover() -> list[Register]:
    """Every router module's `register`, sorted by (ORDER, module name)."""
    found: list[tuple[int, str, Register]] = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        register = getattr(module, "register", None)
        if register is None:
            continue  # a helper module, not a route group
        order = getattr(module, "ORDER", None)
        if not isinstance(order, int):
            raise TypeError(f"router module {info.name} has register() but no integer ORDER")
        found.append((order, info.name, register))
    found.sort(key=lambda entry: (entry[0], entry[1]))
    return [register for _, _, register in found]
