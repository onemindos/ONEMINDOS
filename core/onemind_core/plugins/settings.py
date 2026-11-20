# SPDX-License-Identifier: Apache-2.0
"""Owner-approved plugin settings, pinned to the installed schema and receipt."""
import json
from pathlib import Path

from jsonschema import ValidationError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update

from ..actions import FeatureAction
from ..catalog import AppEntry
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import AppStateRow, ActionRow
from .models import PluginInstallRow, PluginSettingsRow
from .settings_schema import compile_schema


class ConfigureParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$", max_length=59)
    bundle_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    settings: dict


class PluginSettings:
    def __init__(self, gw, identity):
        self.gw, self.identity, self.repo = gw, identity, identity.repo
        gw.actions.register_type("plugin.configure", FeatureAction(
            risk="write", run=self.run, params_model=ConfigureParams, check_request=self.check_request,
            check=self.check, claim=self.claim, release=self.release,
        ))

    def record(self, app_id, principal=None, claimed=None):
        row = self.repo.get(PluginInstallRow, app_id)
        state = self.gw.repo.get_app_state(app_id)
        runtime = self.gw.repo.get_runtime(app_id)
        if principal is not None and not self.identity.can_open(principal, app_id):
            raise ApiError(404, "not_found", "no such plugin settings")
        if row is None or row.settings_schema is None:
            raise ApiError(404, "not_found", "no such plugin settings")
        valid = state and ((state.status in {"installed", "stopped"}) if claimed is None else (
            state.status == "configuring" and state.action_id == claimed))
        if not valid or runtime is None or runtime.bundle_sha256 != row.bundle_sha256:
            raise ApiError(409, "stale_precondition", "plugin installation changed or is busy")
        return row

    def view(self, app_id, principal):
        row = self.record(app_id, principal)
        saved = self.repo.get(PluginSettingsRow, app_id)
        return {"schema": row.settings_schema, "settings": saved.values if saved else {},
                "bundle_sha256": row.bundle_sha256}

    def validate(self, params, claimed=None):
        row = self.record(params["app_id"], claimed=claimed)
        if row.bundle_sha256 != params["bundle_sha256"]:
            raise ApiError(409, "stale_precondition", "plugin receipt changed; reload settings")
        try:
            encoded = json.dumps(params["settings"], allow_nan=False)
        except (ValueError, TypeError, RecursionError) as exc:
            raise ApiError(422, "conflict", "plugin settings must be bounded JSON") from exc
        if len(encoded.encode()) > 65536:
            raise ApiError(422, "conflict", "plugin settings exceed 64 KiB")

        def bounded(v, depth=0):
            if depth > 16 or (isinstance(v, str) and len(v) > 256):
                raise ValueError("plugin settings exceed value limits")
            if isinstance(v, dict):
                for k, item in v.items():
                    bounded(k, depth + 1)
                    bounded(item, depth + 1)
            elif isinstance(v, list):
                for item in v:
                    bounded(item, depth + 1)
        try:
            bounded(params["settings"])
            compile_schema(row.settings_schema).validate(params["settings"])
        except (ValueError, ValidationError) as exc:
            raise ApiError(422, "conflict", "plugin settings do not match the installed schema") from exc
        return row

    def check_request(self, params, principal):
        if not principal.is_owner:
            raise ApiError(403, "permission_denied", "only an owner may configure a plugin")
        self.record(params["app_id"], principal)
        self.validate(params)

    def check(self, action):
        try:
            self.validate(action.params)
        except ApiError as exc:
            return exc.message
        return None

    def claim(self, action):
        params = action.params
        with self.repo.db.session.begin() as s:
            state = s.get(AppStateRow, params["app_id"])
            receipt = s.get(PluginInstallRow, params["app_id"])
            if (not state or state.status not in {"installed", "stopped"} or not receipt
                    or receipt.bundle_sha256 != params["bundle_sha256"]):
                return "plugin installation changed or is busy"
            prior = state.status
            ids = s.execute(update(AppStateRow).where(
                AppStateRow.app_id == params["app_id"], AppStateRow.status == prior,
            ).values(status="configuring", action_id=action.id, updated_at=self.gw.clock())
              .returning(AppStateRow.app_id)).scalars().all()
            if not ids:
                return "plugin installation was claimed concurrently"
            saved = s.get(PluginSettingsRow, params["app_id"])
            s.merge(PluginSettingsRow(app_id=params["app_id"], values=saved.values if saved else {},
                                      claim_action=action.id, prior_status=prior))
        return None

    def release(self, action):
        with self.repo.db.session.begin() as s:
            saved = s.get(PluginSettingsRow, action.params["app_id"])
            if saved and saved.claim_action == action.id:
                outcome = s.get(ActionRow, action.id)
                status = "unknown" if outcome and outcome.state == "outcome_unknown" else saved.prior_status
                s.execute(update(AppStateRow).where(
                    AppStateRow.app_id == saved.app_id, AppStateRow.action_id == action.id,
                    AppStateRow.status == "configuring",
                ).values(status=status, updated_at=self.gw.clock()))
                saved.claim_action, saved.prior_status = None, None

    def run(self, action, finish):
        row = self.validate(action.params, claimed=action.id)
        app = AppEntry(row.app_id, Path(self.gw.settings.apps_dir) / row.app_id, row.manifest)
        executor = getattr(self.gw.executor, "configure_plugin", None)
        result = (executor(app, action.params["settings"]) if executor else
                  ExecResult("failed", "executor does not support plugin settings"))
        if result.outcome == "succeeded":
            self.repo.update(PluginSettingsRow, [PluginSettingsRow.app_id == row.app_id,
                                               PluginSettingsRow.claim_action == action.id],
                             {"values": action.params["settings"]})
        finish(result)
