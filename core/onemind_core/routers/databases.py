# SPDX-License-Identifier: Apache-2.0
"""Shared PostgreSQL (DB-SHARED-1): the install hook for `spec.database` and a read-only list.

Registered before `backups`, which dumps and restores these databases.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..actions import InstallHook
from ..auth import Principal
from ..backups.kube import DryKube, Kube
from ..context import Gateway
from ..databases import DatabasesSettings, SharedPostgres
from ..errors import ApiError, error_responses


def register(app: FastAPI, gw: Gateway) -> None:
    real = gw.executor.name == "kubernetes"
    kube = Kube(gw.settings.kubectl, gw.settings.executor_timeout_s) if real else DryKube()
    pg = SharedPostgres(kube, gw.settings.section(DatabasesSettings), dry_run=not real)
    app.state.databases = pg
    gw.actions.install_hooks.append(InstallHook("database", lambda entry, _action: pg.prepare_install(entry)))

    @app.get("/v1/databases", tags=["databases"], responses=error_responses(401, 403))
    def databases(p: Principal = Depends(gw.principal)):
        """Apps' databases on the shared PostgreSQL. Never a password: those live in each app's Secret."""
        if not (p.is_owner or p.role == "adult"):
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "list databases", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not list databases")
        installed = {i for i, st in gw.repo.list_app_states().items() if st.status == "installed"}
        return pg.describe(list(gw.catalog.load().values()), installed)
