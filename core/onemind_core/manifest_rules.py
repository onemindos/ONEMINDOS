# SPDX-License-Identifier: Apache-2.0
"""Manifest v1 rules a JSON Schema cannot say (#604), run by Catalog.validate: the credential scan
before the schema (a manifest that holds a credential gets those errors alone), the rest after it.

The Go validator behind `onemind plugin validate` (internal/plugin/validate/blocks.go) runs the same
rules with the same messages, and sdk/testdata/manifest-v1/cases.yaml holds the shared golden cases,
so a bad manifest fails in CI and on the box alike. The credential patterns live once, in the app
schema's $defs (credentialValue, credentialName). Errors name the field, never the value.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

BLOCKS = ("bridge", "connector", "videoSource")
# A field with a credential name may hold this word only (spec.credentials.password: generated).
GENERATED = "generated"


class ManifestRules:
    def __init__(self, schema: dict):
        defs = schema.get("$defs", {})
        self.value_re = re.compile(defs["credentialValue"]["pattern"])
        self.name_re = re.compile(defs["credentialName"]["pattern"])

    @classmethod
    def for_schema(cls, schema: object) -> ManifestRules | None:
        """The rules for a manifest v1 schema, or None for a schema without the credential $defs.

        Only the v1 app schema carries the patterns; an older or hand-written schema (tests, a
        channel's own) still validates manifests, without the v1 cross-field rules.
        """
        defs = schema.get("$defs") if isinstance(schema, dict) else None
        if not isinstance(defs, dict) or not all(
            isinstance(defs.get(k), dict) and isinstance(defs[k].get("pattern"), str)
            for k in ("credentialValue", "credentialName")
        ):
            return None
        return cls(schema)

    def errors(self, doc: object) -> list[str]:
        """The cross-field errors. Catalog.validate checks credential_errors first and stops there,
        so these run only on a manifest that holds no credential."""
        if not isinstance(doc, dict):
            return []
        errs = list(self.credential_errors(doc))
        spec = doc.get("spec")
        if isinstance(spec, dict):
            errs.extend(self.hide(e) for e in block_errors(spec))
        return errs

    def hide(self, message: str) -> str:
        """A message that would repeat a credential keeps only its field."""
        if self.value_re.search(message):
            return f"{message.split(':', 1)[0]}: value refused (hidden: it looks like a credential)"
        return message

    def credential_errors(self, value: object, path: str = "") -> Iterator[str]:
        if isinstance(value, dict):
            for key, item in value.items():
                where = f"{path}/{key}" if path else str(key)
                if (isinstance(key, str) and isinstance(item, str) and item and item != GENERATED
                        and self.name_re.search(key)):
                    yield f"{where}: holds a credential value; name a spec.secrets entry instead"
                else:
                    yield from self.credential_errors(item, where)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                yield from self.credential_errors(item, f"{path}/{i}")
        elif isinstance(value, str) and self.value_re.search(value):
            yield f"{path or '<root>'}: holds a credential value; name a spec.secrets entry instead"


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def block_errors(spec: dict) -> list[str]:
    """Cross-field rules: hosts, providers, interval floors, own layers, declared tools, recording."""
    errs: list[str] = []
    ext = _dict(spec.get("extensions"))
    egress = {e for e in _list(spec.get("egress")) if isinstance(e, str)}
    providers = {p.get("id"): p for p in _list(_dict(spec.get("terms")).get("providers")) if isinstance(p, dict)}
    for name in BLOCKS:
        block = ext.get(name)
        if not isinstance(block, dict):
            continue
        where = f"spec/extensions/{name}"
        for host in _list(block.get("hosts")):
            if host not in egress:
                errs.append(f"{where}/hosts: {host} is not in spec.egress")
        provider = providers.get(block.get("provider"))
        if provider is None:
            errs.append(f"{where}/provider: {block.get('provider')} has no terms record in spec.terms.providers")
            continue
        every, floor = block.get("everySeconds"), provider.get("minIntervalSeconds")
        if isinstance(every, int) and isinstance(floor, int) and every < floor:
            errs.append(f"{where}/everySeconds: {every} is below the provider's minIntervalSeconds ({floor})")
        if name == "videoSource" and block.get("record") is True and (
                provider.get("display") != "full" or provider.get("store") == "none"):
            errs.append(f"{where}/record: record needs a provider with display full and a store")
    layers = {layer.get("id") for layer in _list(spec.get("mapLayers"))
              if isinstance(layer, dict) and layer.get("source") == "emits"}
    for i, emit in enumerate(_list(_dict(ext.get("bridge")).get("emits"))):
        if isinstance(emit, dict) and emit.get("kind") == "layer" and emit.get("name") not in layers:
            errs.append(f"spec/extensions/bridge/emits/{i}: layer {emit.get('name')} is not one of this app's mapLayers with source emits")
    tools = {t.get("name"): t.get("effect") for t in _list(ext.get("tools")) if isinstance(t, dict)}
    for i, job in enumerate(_list(spec.get("jobs"))):
        tool = _dict(job).get("tool")
        if tool not in tools:
            errs.append(f"spec/jobs/{i}/tool: {tool} is not a declared tool")
        elif tools[tool] == "destructive":
            errs.append(f"spec/jobs/{i}/tool: a job may not call a destructive tool ({tool})")
    for t, topic in enumerate(_list(_dict(spec.get("notifications")).get("topics"))):
        for a, action in enumerate(_list(_dict(topic).get("actions"))):
            tool = _dict(action).get("tool")
            if tool not in tools:
                errs.append(f"spec/notifications/topics/{t}/actions/{a}/tool: {tool} is not a declared tool")
    return errs
