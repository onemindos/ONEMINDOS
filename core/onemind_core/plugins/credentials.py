# SPDX-License-Identifier: Apache-2.0
"""Persistent retirement of app-managed plugin credentials; never issues a token."""
from __future__ import annotations

from sqlalchemy import select

from ..actions import InstallHook
from ..identity.models import TokenRow
from .auth import plugin_app_id


def register_credentials(gw, identity) -> None:
    repo = identity.repo

    def revoke(app_id: str, reason: str, action_id: str | None = None) -> None:
        ids = repo.update(TokenRow, [
            TokenRow.kind == "plugin", TokenRow.source == "app-install",
            TokenRow.principal_id == f"plugin:{app_id}", TokenRow.revoked_at.is_(None),
        ], {"revoked_at": gw.clock()})
        if gw.actions.principals is not None:  # PR 7: a reinstall is a new identity for its rules
            gw.actions.principals.retire(f"plugin:{app_id}", reason)
        if ids:
            gw.audit.append("plugin.principal.revoked", None, action_id, {
                "principal_id": f"plugin:{app_id}", "reason": reason, "count": len(ids),
            })

    def prepare(app, action):
        # A retry/reinstall must not resurrect a credential from a previous workload.
        revoke(app.id, "app.install", action.id)
        return []

    def removing(app, action):
        # Even if cleanup fails, the old workload cannot authenticate again.
        revoke(app.id, "app.remove", action.id)

    def completed(action, outcome):
        if action.type == "app.install" and outcome != "succeeded":
            revoke(action.params["app_id"], f"install {outcome}", action.id)

    # Retire credentials left across a gateway crash or a missing app state.
    # Installed and deliberately stopped workloads retain their exact snapshots.
    rows = repo.all(select(TokenRow).where(
        TokenRow.kind == "plugin", TokenRow.source == "app-install", TokenRow.revoked_at.is_(None),
    ))
    for principal_id in {row.principal_id for row in rows}:
        app_id = plugin_app_id(principal_id)
        state = gw.repo.get_app_state(app_id) if app_id else None
        if app_id and (state is None or state.status not in {"installed", "stopped"}):
            revoke(app_id, "gateway recovery")

    gw.actions.install_hooks.append(InstallHook("plugin-credentials", prepare, removing=removing))
    gw.actions.after_dispatch.append(completed)
