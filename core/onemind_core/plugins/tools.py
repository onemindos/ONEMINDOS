# SPDX-License-Identifier: Apache-2.0
"""Installed tool snapshots: reads are direct; mutations are owner-approved actions."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update

from ..ledger import AppStateRow

from ..actions import FeatureAction
from ..errors import ApiError
from ..executors import ExecResult
from . import dispatch
from .auth import plugin_app_id
from .models import PluginInstallRow


class InvokeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    tool: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    args: dict[str, Any]
    args_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    bundle_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    effect: Literal["write", "destructive"]


class Tools:
    def __init__(self, gw, identity):
        self.gw, self.identity = gw, identity
        gw.actions.register_type("plugin.invoke", FeatureAction(
            risk="write", risk_for=lambda params: params["effect"], run=self.run,
            requesters=frozenset({"person", "agent", "plugin"}), params_model=InvokeParams,
            check_request=self.check_request, check=self.check, claim=self.claim, release=self.release,
        ))

    def installed(self, app_id: str, action_id=None):
        state = self.gw.repo.get_app_state(app_id)
        row = self.identity.repo.get(PluginInstallRow, app_id)
        receipt = self.gw.repo.get_runtime(app_id)
        if (plugin_app_id(f"plugin:{app_id}") != app_id or state is None or not (state.status == "installed" or
                    (action_id and state.status == "configuring" and state.action_id == action_id))
                or row is None or receipt is None or receipt.bundle_sha256 != row.bundle_sha256):
            raise ApiError(404, "not_found", "no enabled installed plugin")
        return row

    def lookup(self, app_id: str, name: str, action_id=None):
        row = self.installed(app_id, action_id)
        try:
            if row.manifest["metadata"]["id"] != app_id:
                raise ValueError("identity mismatch")
            spec = row.manifest["spec"]
            backend = spec["plugin"]["backend"]
            declarations = spec["extensions"]["tools"]
            matches = [item for item in declarations if item["name"] == name]
            if len(matches) != 1:
                raise ValueError("unknown or duplicate tool")
            tool = matches[0]
            if not isinstance(tool.get("exposure"), dict):
                raise ValueError("invalid exposure declaration")
            if tool.get("effect") not in {"read", "write", "destructive"} or tool.get("exposure", {}).get("rest") is not True:
                raise ValueError("not a REST tool")
            dispatch.backend_url(app_id, backend, name)
            dispatch.schema_validator(tool["input"])
            if "output" in tool:
                dispatch.schema_validator(tool["output"])
            return row, backend, tool
        except (KeyError, TypeError, ValueError, ApiError) as exc:
            raise ApiError(404, "not_found", "no enabled installed plugin tool") from exc

    def visible(self, app_id, principal):
        if not self.identity.can_open(principal, app_id):
            raise ApiError(404, "not_found", "no enabled installed plugin")

    def params(self, app_id, name, arguments):
        row, _, tool = self.lookup(app_id, name)
        dispatch.validate_data(tool["input"], arguments)
        if tool["effect"] == "read":
            raise ApiError(422, "conflict", "read tools do not create actions")
        return {"app_id": app_id, "tool": name, "args": arguments,
                "args_sha256": dispatch.arguments_hash(arguments), "bundle_sha256": row.bundle_sha256,
                "effect": tool["effect"]}

    def check_request(self, params, principal):
        self.visible(params["app_id"], principal)
        self.bound(params)

    def bound(self, params, action_id=None):
        row, backend, tool = self.lookup(params["app_id"], params["tool"], action_id)
        if (row.bundle_sha256 != params["bundle_sha256"] or tool["effect"] != params["effect"]
                or tool["effect"] == "read" or dispatch.arguments_hash(params["args"]) != params["args_sha256"]):
            raise ApiError(409, "stale_precondition", "installed plugin or tool arguments changed")
        dispatch.validate_data(tool["input"], params["args"])
        return backend, tool

    def check(self, action):
        try:
            self.bound(action.params)
        except ApiError:
            return "installed plugin or tool arguments changed"
        return None

    def claim(self, action):
        with self.gw.db.session.begin() as session:
            changed = session.execute(update(AppStateRow).where(
                AppStateRow.app_id == action.params["app_id"], AppStateRow.status == "installed",
            ).values(status="configuring", action_id=action.id, updated_at=self.gw.clock()).returning(AppStateRow.app_id)).first()
        return None if changed else "plugin is busy or no longer installed"

    def release(self, action):
        with self.gw.db.session.begin() as session:
            session.execute(update(AppStateRow).where(
                AppStateRow.app_id == action.params["app_id"], AppStateRow.status == "configuring",
                AppStateRow.action_id == action.id,
            ).values(status="installed", updated_at=self.gw.clock()))

    def run(self, action, finish):
        try:
            backend, tool = self.bound(action.params, action.id)  # last look after acceptance, before I/O
        except ApiError:
            finish(ExecResult("failed", "installed plugin or tool arguments changed"))
            return
        try:
            output = dispatch.invoke(self.gw, action.params["app_id"], backend, tool, action.params["args"], action_id=action.id)
        except ApiError:
            # A timeout or invalid result cannot prove a mutating handler did nothing.
            finish(ExecResult("outcome_unknown", "plugin dispatch or result validation failed; do not retry automatically"))
            return
        finish(ExecResult("succeeded", "plugin tool completed", [{"tool": tool["name"], "output": output}]))

    def read(self, principal, app_id, name, arguments):
        self.visible(app_id, principal)
        _, backend, tool = self.lookup(app_id, name)
        if tool["effect"] != "read":
            raise ApiError(403, "permission_denied", "mutating tool requires an action")
        facts = {"app_id": app_id, "tool": name, "args_sha256": dispatch.arguments_hash(arguments)}
        try:
            output = dispatch.invoke(self.gw, app_id, backend, tool, arguments)
        except ApiError:
            self.gw.audit.append("plugin.tool.read", principal.as_dict(), None, {**facts, "outcome": "failed"})
            raise
        self.gw.audit.append("plugin.tool.read", principal.as_dict(), None, {**facts, "outcome": "succeeded"})
        return output
