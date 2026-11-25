# SPDX-License-Identifier: Apache-2.0
"""Bounded gateway-to-plugin calls: one signed, short-lived dispatch credential."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid

import httpx
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.exceptions import NoSuchResource

from ..backups.jobs import load_or_create_job_key
from ..appstore.appsettings import pattern_risk
from ..errors import ApiError
from .auth import plugin_app_id

MAX_BYTES = 64 * 1024
_TOOL = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
_SERVICE = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?\Z")


def canonical(value) -> bytes:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                            allow_nan=False).encode("ascii")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ApiError(422, "conflict", "tool arguments must be finite JSON") from exc
    if len(result) > MAX_BYTES:
        raise ApiError(413, "payload_too_large", "plugin tool data exceeds 64 KiB")
    return result


def arguments_hash(arguments: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(arguments)).hexdigest()


def _no_remote(uri):
    raise NoSuchResource(ref=uri)


def schema_validator(schema: object):
    """No network resolution or implicit older dialect, including nested references."""
    try:
        if (not isinstance(schema, dict) or schema.get("type") != "object"
                or schema.get("additionalProperties") is not False
                or schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
                not in {"https://json-schema.org/draft/2020-12/schema", "https://json-schema.org/draft/2020-12/schema#"}):
            raise ValueError("expected a closed JSON Schema 2020-12 object")
        Draft202012Validator.check_schema(schema)
        stack = [schema]
        count = 0
        while stack:
            count += 1
            if count > 2048:
                raise ValueError("schema exceeds complexity bound")
            value = stack.pop()
            if isinstance(value, dict):
                if "patternProperties" in value:
                    raise ValueError("patternProperties unsupported")
                if "pattern" in value:
                    pattern = value["pattern"]
                    if not isinstance(pattern, str) or len(pattern) > 128 or pattern_risk(pattern):
                        raise ValueError("unbounded schema pattern")
                for name, child in value.items():
                    if name in {"$ref", "$dynamicRef"} and (not isinstance(child, str) or not child.startswith("#")):
                        raise ValueError("external schema reference")
                    stack.append(child)
            elif isinstance(value, list):
                stack.extend(value)
        return Draft202012Validator(schema, registry=Registry(retrieve=_no_remote),
                                     format_checker=Draft202012Validator.FORMAT_CHECKER)
    except Exception as exc:
        # Do not include backend data or arguments in a public error or audit message.
        raise ApiError(422, "conflict", "plugin tool data failed offline schema validation") from exc


def validate_data(schema: object, data: object) -> None:
    try:
        schema_validator(schema).validate(data)
    except Exception as exc:
        raise ApiError(422, "conflict", "plugin tool data failed offline schema validation") from exc


def backend_url(app_id: str, backend: dict, tool: str) -> str:
    if not isinstance(backend, dict):
        raise ApiError(409, "stale_precondition", "invalid installed plugin backend")
    service, port = backend.get("service"), backend.get("port")
    if (plugin_app_id(f"plugin:{app_id}") != app_id or not _TOOL.fullmatch(tool)
            or not isinstance(service, str) or not _SERVICE.fullmatch(service)
            or type(port) is not int or not 1 <= port <= 65535):
        raise ApiError(409, "stale_precondition", "invalid installed plugin backend")
    return f"http://{service}.app-{app_id}.svc.cluster.local:{port}/onemind/v1/tools/{tool}"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def dispatch_token(gw, app_id: str, tool: str, arguments: dict, action_id: str | None) -> str:
    now = int(gw.clock().timestamp())
    claims = {"aud": f"plugin:{app_id}", "tool": tool, "args_sha256": arguments_hash(arguments),
              "iat": now, "exp": now + 60, "jti": uuid.uuid4().hex}
    if action_id is not None:
        claims["action_id"] = action_id
    head = _b64(canonical({"alg": "EdDSA", "typ": "JWT"}))
    payload = _b64(canonical(claims))
    key = load_or_create_job_key(gw.settings.audit_path.parent / "plugins" / "dispatch.key")
    signing_input = f"{head}.{payload}"
    return signing_input + "." + _b64(key.sign(signing_input.encode("ascii")))


def client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(5, connect=2), follow_redirects=False, trust_env=False)


def invoke(gw, app_id: str, backend: dict, tool: dict, arguments: dict, *, action_id: str | None = None):
    validate_data(tool.get("input"), arguments)
    if "output" in tool:
        schema_validator(tool["output"])
    effect = tool.get("effect")
    if effect not in {"read", "write", "destructive"} or (effect != "read" and not action_id):
        raise ApiError(403, "permission_denied", "mutating tool requires an approved action")
    if effect != "read":
        action = gw.repo.get(action_id)
        if (action is None or action.type != "plugin.invoke" or action.state != "dispatched"
                or not action.approved_by or action.params.get("app_id") != app_id
                or action.params.get("tool") != tool["name"]
                or action.params.get("args_sha256") != arguments_hash(arguments)):
            raise ApiError(403, "permission_denied", "tool dispatch is not bound to an approved action")
    url = backend_url(app_id, backend, tool["name"])
    token = dispatch_token(gw, app_id, tool["name"], arguments, action_id)
    try:
        with client() as transport, transport.stream("POST", url, content=canonical(arguments),
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}) as response:
            if response.status_code != 200:
                raise ValueError("plugin returned non-success status")
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > MAX_BYTES:
                    raise ValueError("plugin result exceeds 64 KiB")
                body.extend(chunk)
            result = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")))
            if not isinstance(result, dict):
                raise ValueError("plugin result must be an object")
            canonical(result)
            if "output" in tool:
                validate_data(tool["output"], result)
            return result
    except Exception as exc:
        raise ApiError(503, "unavailable", "plugin tool dispatch or result validation failed") from exc
