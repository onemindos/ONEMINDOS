"""App catalog built from ONEMIND_APPS_DIR/*/onemind.app.yaml (contract sections 3 and 4).

If sdk/schema/onemind.app.schema.json exists (written by the apps stream), every manifest is
validated against it. Otherwise a minimal built-in check runs. Invalid manifests are skipped and
reported in `errors`, so one broken app never hides the rest of the Market.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .appsecrets.spec import SecretDecl, parse_secrets, secret_spec_errors
from .scan import ScanRecord, read_scan

log = logging.getLogger("onemind.catalog")

# app-<id> must stay a valid Kubernetes namespace (DNS label, max 63 chars).
APP_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?$")
MANIFEST = "onemind.app.yaml"
# Kubernetes Secret names are DNS-1123 subdomains.
SECRET_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
LINK_KEYS = ("docs", "github", "website", "support")
TIERS = ("verified", "community", "blocked")


def _http_url(value: object) -> str | None:
    """Only absolute http(s) links reach the dashboard (never javascript: or data: URLs)."""
    if isinstance(value, str) and re.match(r"^https?://[^\s/]+", value, re.IGNORECASE):
        return value
    return None


@dataclass(frozen=True)
class AgentSpec:
    """§11.2 spec.agent: the app gets its own agent principal, delivered in Secret `secret`."""

    principal_id: str
    secret: str


def agent_spec_errors(spec: object) -> list[str]:
    agent = spec.get("agent") if isinstance(spec, dict) else None
    if agent is None:
        return []
    if not isinstance(agent, dict) or not isinstance(agent.get("principal", False), bool):
        return ["spec.agent must be a mapping {principal: bool, secret: <name>}"]
    if agent.get("principal"):
        secret = agent.get("secret")
        if not isinstance(secret, str) or len(secret) > 253 or not SECRET_NAME_RE.match(secret):
            return ["spec.agent.secret must be a Kubernetes Secret name (DNS-1123 subdomain)"]
    return []


@dataclass(frozen=True)
class AppEntry:
    id: str
    dir: Path
    manifest: dict

    @property
    def manifests_dir(self) -> Path:
        rel = (self.manifest.get("spec") or {}).get("manifests") or "manifests/"
        path = (self.dir / rel).resolve()
        if not path.is_relative_to(self.dir.resolve()):
            raise ValueError(f"app {self.id}: spec.manifests escapes the app folder")
        return path

    @property
    def agent(self) -> AgentSpec | None:
        agent = (self.manifest.get("spec") or {}).get("agent")
        if isinstance(agent, dict) and agent.get("principal") is True:
            return AgentSpec(principal_id=f"agent:{self.id}", secret=str(agent["secret"]))
        return None

    @property
    def secrets(self) -> tuple[SecretDecl, ...]:
        """The declared spec.secrets (DEPLOYMENTS.md §7); () when none. Validated at load."""
        agent = self.agent
        return parse_secrets(self.manifest.get("spec") or {}, agent.secret if agent else None)[0]

    @property
    def scan(self) -> ScanRecord | None:
        return read_scan(self.dir)

    def summary(self) -> dict:
        md = self.manifest.get("metadata") or {}
        spec = self.manifest.get("spec") or {}
        # Defensive: a JSON Schema from the apps stream may be looser than builtin_check.
        requires, web, archs = spec.get("requires"), spec.get("web"), spec.get("archs")
        links = md.get("links") if isinstance(md.get("links"), dict) else {}
        scan = self.scan
        return {
            "id": self.id,
            "name": md.get("name"),
            "version": str(md.get("version")) if md.get("version") is not None else None,
            "description": md.get("description"),
            "category": md.get("category"),
            "icon": md.get("icon"),
            "license": md.get("license"),
            "source": md.get("source"),
            "archs": list(archs) if isinstance(archs, list) else [],
            "requires": dict(requires) if isinstance(requires, dict) else {},
            "web_port": web.get("port") if isinstance(web, dict) else None,
            # §11.4 additions.
            "links": {k: _http_url(links.get(k)) for k in LINK_KEYS},
            "tier": md.get("tier") if md.get("tier") in TIERS else None,
            "scan": scan.summary() if scan is not None else None,
        }


def builtin_check(doc: object) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["manifest is not a mapping"]
    if doc.get("apiVersion") != "onemind.app/v1alpha1":
        errs.append("apiVersion must be onemind.app/v1alpha1")
    if doc.get("kind") != "App":
        errs.append("kind must be App")
    md, spec = doc.get("metadata"), doc.get("spec")
    if not isinstance(md, dict):
        errs.append("metadata missing")
        md = {}
    if not isinstance(spec, dict):
        errs.append("spec missing")
        spec = {}
    if not isinstance(md.get("id"), str) or not APP_ID_RE.match(md.get("id", "")):
        errs.append("metadata.id must be a lowercase DNS label (max 59 chars)")
    for key in ("name", "version"):
        if md.get(key) in (None, ""):
            errs.append(f"metadata.{key} is required")
    archs = spec.get("archs")
    if not isinstance(archs, list) or not archs or not all(a in ("amd64", "arm64") for a in archs):
        errs.append("spec.archs must be a non-empty list of amd64/arm64")
    for key in ("requires", "web"):
        if spec.get(key) is not None and not isinstance(spec.get(key), dict):
            errs.append(f"spec.{key} must be a mapping")
    port = (spec.get("web") or {}).get("port") if isinstance(spec.get("web"), dict) else None
    if port is not None and not (isinstance(port, int) and 1 <= port <= 65535):
        errs.append("spec.web.port must be 1-65535")
    errs.extend(agent_spec_errors(spec))
    errs.extend(secret_spec_errors(spec))
    return errs


class Catalog:
    def __init__(self, apps_dir: Path, schema_path: Path | None = None):
        self.apps_dir = apps_dir
        self.schema_path = schema_path
        self._validator = None
        if schema_path is not None and schema_path.is_file():
            from jsonschema.validators import validator_for

            schema = json.loads(schema_path.read_text())
            cls = validator_for(schema)
            cls.check_schema(schema)
            self._validator = cls(schema)
            log.info("validating app manifests against %s", schema_path.name)
        else:
            log.info("no app schema found; using the built-in manifest check")
        self.errors: dict[str, list[str]] = {}

    @property
    def validation_mode(self) -> str:
        return "schema" if self._validator is not None else "builtin"

    def _validate(self, doc: object) -> list[str]:
        errs = builtin_check(doc) if self._validator is None else []
        if self._validator is not None:
            errs = [
                f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
                for e in self._validator.iter_errors(doc)
            ]
            md = doc.get("metadata") if isinstance(doc, dict) else None
            app_id = md.get("id") if isinstance(md, dict) else None
            if not isinstance(app_id, str) or not APP_ID_RE.match(app_id):
                errs.append("metadata.id must be a lowercase DNS label (max 59 chars)")
            errs.extend(agent_spec_errors(doc.get("spec") if isinstance(doc, dict) else None))
            # Rules a JSON Schema cannot say: unique names and keys, no clash with spec.agent.
            errs.extend(secret_spec_errors(doc.get("spec") if isinstance(doc, dict) else None))
        return errs

    def load(self) -> dict[str, AppEntry]:
        """Re-scan the apps folder. Cheap enough to do per request for a home-sized Market."""
        apps: dict[str, AppEntry] = {}
        errors: dict[str, list[str]] = {}
        if not self.apps_dir.is_dir():
            self.errors = {}
            return apps
        for path in sorted(self.apps_dir.glob(f"*/{MANIFEST}")):
            folder = path.parent.name
            try:
                doc = yaml.safe_load(path.read_text())
            except (OSError, yaml.YAMLError) as exc:
                errors[folder] = [f"cannot parse: {exc.__class__.__name__}"]
                continue
            errs = self._validate(doc)
            if not errs and doc["metadata"]["id"] != folder:
                errs.append(f"metadata.id {doc['metadata']['id']!r} must match folder name {folder!r}")
            if errs:
                errors[folder] = errs
                log.warning("skipping app %s: %s", folder, "; ".join(errs))
                continue
            apps[folder] = AppEntry(id=folder, dir=path.parent, manifest=doc)
        self.errors = errors
        return apps

    def get(self, app_id: str) -> AppEntry | None:
        return self.load().get(app_id)
