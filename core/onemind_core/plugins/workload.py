# SPDX-License-Identifier: Apache-2.0
"""An approved install hands a scoped plugin identity to its workload, never a caller."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import re

from .. import lifecycle as lc
from ..backups.jobs import load_or_create_job_key, public_pem
from ..errors import ApiError
from ..executors import AgentSecret
from ..identity.crypto import new_id, new_secret, sha256_hex
from ..identity.models import TokenRow
from .auth import plugin_app_id, request_types
from .models import PluginInstallRow

_SECRET = re.compile(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?\Z")


def declaration(app) -> tuple[str, list[str]] | None:
    spec = app.manifest.get("spec") or {}
    plugin = spec.get("plugin")
    if plugin is None:
        return None
    if (not isinstance(plugin, dict) or plugin.get("principal") is not True
            or plugin_app_id(f"plugin:{app.id}") is None):
        raise ValueError("invalid plugin principal declaration")
    if spec.get("agent") is not None:
        raise ValueError("a plugin cannot also declare an agent identity")
    secret = plugin.get("secret")
    if (not isinstance(secret, str) or not 1 <= len(secret) <= 253 or not _SECRET.fullmatch(secret)
            or any(not part or len(part) > 63 for part in secret.split("."))):
        raise ValueError("invalid plugin credential Secret name")
    if any(row.name == secret for row in app.secrets):
        raise ValueError("plugin credential Secret collides with app secrets")
    scopes = spec.get("permissions", [])
    if request_types(scopes) is None:
        raise ValueError("plugin requests unsupported runtime permissions")
    return secret, sorted(set(scopes))


@dataclass(frozen=True)
class PluginSecret(AgentSecret):
    dispatch_pubkey: str = ""

    def keys(self):
        return ["ONEMIND_GATEWAY_URL", "ONEMIND_PLUGIN_TOKEN", "ONEMIND_DISPATCH_PUBKEY",
                *(["ONEMIND_GATEWAY_CA"] if self.ca_pem else [])]

    def manifest(self, namespace: str, app_id: str) -> str:
        doc = json.loads(super().manifest(namespace, app_id))
        doc["data"]["ONEMIND_PLUGIN_TOKEN"] = doc["data"].pop("ONEMIND_AGENT_TOKEN")
        doc["data"]["ONEMIND_DISPATCH_PUBKEY"] = base64.b64encode(self.dispatch_pubkey.encode()).decode()
        doc["metadata"]["labels"].pop("onemind.io/agent-principal")
        doc["metadata"]["labels"]["onemind.io/plugin-principal"] = "true"
        return json.dumps(doc)


def register_workloads(gw, identity) -> None:
    def check(type_, _params, app, _phase):
        if type_ not in {"app.install", "app.update"}:
            return
        try:
            declaration(app)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc), reason="invalid_request") from exc
        if type_ == "app.update" and app.manifest.get("spec", {}).get("plugin"):
            # Updating a running identity needs grant-diff approval and receipt migration.
            # Do not keep a token with stale privileges while changing its workload.
            raise ApiError(409, "conflict", "plugin updates require removal and a fresh approved install")

    def credential(action, app):
        record = identity.repo.get(PluginInstallRow, app.id)
        if action.type == "app.remove":
            return PluginSecret(record.secret_name, f"plugin:{app.id}") if record else None
        if action.type != "app.install":
            if record:
                return PluginSecret(record.secret_name, f"plugin:{app.id}", gateway_url=gw.actions.gateway_url)
            return None
        parsed = declaration(app)
        if parsed is None:
            return None
        name, scopes = parsed
        digest = lc.bundle_sha256(app)
        if digest is None:
            raise ValueError("plugin workload bundle is unavailable")
        # Separate key from backup jobs, persistent across restarts. Only the public half leaves.
        key = load_or_create_job_key(gw.settings.audit_path.parent / "plugins" / "dispatch.key")
        token = new_secret("plg")
        now = gw.clock()
        approved = gw.repo.get(action.id)
        row = TokenRow(id=new_id("tok"), prefix=token[:11], name=f"Plugin {app.id}",
                       hash=sha256_hex(token), kind="plugin", principal_id=f"plugin:{app.id}",
                       scopes=scopes, source="app-install", created_by=approved.approved_by if approved and approved.approved_by else action.requested_by["id"],
                       created_at=now)
        with identity.repo.db.session.begin() as session:
            session.merge(PluginInstallRow(app_id=app.id, secret_name=name, bundle_sha256=digest,
                                           manifest=json.loads(json.dumps(app.manifest))))
            session.add(row)
        gw.audit.append("plugin.principal.issued", None, action.id, {
            "principal_id": row.principal_id, "app_id": app.id, "scopes": scopes,
        })
        return PluginSecret(name, row.principal_id, gateway_url=gw.actions.gateway_url, token=token,
                            ca_pem=gw.actions.gateway_ca(), dispatch_pubkey=public_pem(key).decode())

    gw.actions.app_checks.append(check)
    gw.actions.workload_credential = credential
