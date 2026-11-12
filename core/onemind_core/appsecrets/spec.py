# SPDX-License-Identifier: Apache-2.0
"""The manifest's `spec.secrets` declaration (contract §12.18, extended with `kind`).

    spec:
      secrets:
        - name: hermes-agent-credentials         # the Kubernetes Secret in app-<id>
          description: Model-provider keys
          keys:
            - {key: OPENROUTER_API_KEY, kind: api-key, description: OpenRouter key}
            - {key: OPENAI_BASE_URL, kind: url, description: Custom endpoint}
            - {key: SESSION_SECRET, kind: token, generate: true}

A key is either **owner-entered** (the owner types it into the approval form; `required: true`
means the install cannot be approved without it) or **generated** (`generate: true`: the box
creates a random value at install and can rotate it). The declaration never holds a value.

This module imports nothing from the rest of the gateway, so the catalog can use it to validate
manifests without an import cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = ("api-key", "password", "token", "url")
DEFAULT_KIND = "password"  # the most cautious display: masked, never echoed
# Kubernetes Secret names are DNS-1123 subdomains; data keys are [-._a-zA-Z0-9]+ (≤ 253).
SECRET_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
KEY_RE = re.compile(r"^[-._a-zA-Z0-9]{1,253}$")
MAX_SECRETS = 16
MAX_KEYS = 32
MAX_DESCRIPTION = 500
SECRET_FIELDS = {"name", "description", "keys"}
KEY_FIELDS = {"key", "kind", "description", "required", "generate"}


@dataclass(frozen=True)
class KeyDecl:
    key: str
    kind: str
    description: str
    required: bool
    generate: bool

    @property
    def source(self) -> str:
        return "generated" if self.generate else "owner"

    @property
    def ref(self) -> str:
        return self.key


@dataclass(frozen=True)
class SecretDecl:
    name: str
    description: str
    keys: tuple[KeyDecl, ...]

    def key(self, key: str) -> KeyDecl | None:
        return next((k for k in self.keys if k.key == key), None)


def _key_errors(where: str, raw: object, seen: set[str]) -> tuple[KeyDecl | None, list[str]]:
    if not isinstance(raw, dict):
        return None, [f"{where} must be a mapping {{key, kind, description, required, generate}}"]
    errs = [f"{where}: unknown field {f!r}" for f in sorted(set(raw) - KEY_FIELDS)]
    key = raw.get("key")
    if not isinstance(key, str) or not KEY_RE.match(key):
        errs.append(f"{where}.key must match {KEY_RE.pattern}")
        key = None
    elif key in seen:
        errs.append(f"{where}.key {key!r} is declared twice")
    kind = raw.get("kind", DEFAULT_KIND)
    if kind not in KINDS:
        errs.append(f"{where}.kind must be one of {', '.join(KINDS)}")
    desc = raw.get("description", "")
    if not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION:
        errs.append(f"{where}.description must be text of at most {MAX_DESCRIPTION} characters")
    required, generate = raw.get("required", False), raw.get("generate", False)
    for field_name, value in (("required", required), ("generate", generate)):
        if not isinstance(value, bool):
            errs.append(f"{where}.{field_name} must be true or false")
    if generate is True and required is True:
        errs.append(f"{where}: generate and required are exclusive (a generated key is always set)")
    if generate is True and kind == "url":
        errs.append(f"{where}: a url cannot be generated; the owner enters it")
    if errs or key is None:
        return None, errs
    seen.add(key)
    return KeyDecl(key=key, kind=kind, description=desc, required=bool(required), generate=bool(generate)), []


def parse_secrets(spec: object, agent_secret: str | None = None) -> tuple[tuple[SecretDecl, ...], list[str]]:
    """The declared secrets and the problems found. Any problem means the manifest is invalid."""
    raw = spec.get("secrets") if isinstance(spec, dict) else None
    if raw is None:
        return (), []
    if not isinstance(raw, list) or len(raw) > MAX_SECRETS:
        return (), [f"spec.secrets must be a list of at most {MAX_SECRETS} secrets"]
    decls: list[SecretDecl] = []
    errs: list[str] = []
    names: set[str] = set()
    for i, item in enumerate(raw):
        where = f"spec.secrets[{i}]"
        if not isinstance(item, dict):
            errs.append(f"{where} must be a mapping {{name, description, keys}}")
            continue
        errs += [f"{where}: unknown field {f!r}" for f in sorted(set(item) - SECRET_FIELDS)]
        name = item.get("name")
        if not isinstance(name, str) or len(name) > 253 or not SECRET_NAME_RE.match(name):
            errs.append(f"{where}.name must be a Kubernetes Secret name (DNS-1123 subdomain)")
            name = None
        elif name in names:
            errs.append(f"{where}.name {name!r} is declared twice")
        elif agent_secret is not None and name == agent_secret:
            errs.append(f"{where}.name {name!r} is the spec.agent Secret; the gateway owns that one")
        desc = item.get("description", "")
        if not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION:
            errs.append(f"{where}.description must be text of at most {MAX_DESCRIPTION} characters")
        keys_raw = item.get("keys")
        if not isinstance(keys_raw, list) or not keys_raw or len(keys_raw) > MAX_KEYS:
            errs.append(f"{where}.keys must be a list of 1 to {MAX_KEYS} keys")
            continue
        seen: set[str] = set()
        keys: list[KeyDecl] = []
        for j, k in enumerate(keys_raw):
            decl, kerrs = _key_errors(f"{where}.keys[{j}]", k, seen)
            errs += kerrs
            if decl is not None:
                keys.append(decl)
        if name is not None:
            names.add(name)
            decls.append(SecretDecl(name=name, description=desc if isinstance(desc, str) else "", keys=tuple(keys)))
    return (tuple(decls) if not errs else ()), errs


def secret_spec_errors(spec: object) -> list[str]:
    agent = spec.get("agent") if isinstance(spec, dict) else None
    agent_secret = agent.get("secret") if isinstance(agent, dict) and agent.get("principal") is True else None
    return parse_secrets(spec, agent_secret if isinstance(agent_secret, str) else None)[1]
