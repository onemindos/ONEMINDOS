"""App catalog built from ONEMIND_APPS_DIR/*/onemind.app.yaml (contract sections 3 and 4).

If sdk/schema/onemind.app.schema.json exists (written by the apps stream), every manifest is
validated against it. Otherwise a minimal built-in check runs. Invalid manifests are skipped and
reported in `errors`, so one broken app never hides the rest of the Market.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from .ai_policy import UNKNOWN, catalog_policy
from .appsecrets.spec import SecretDecl, parse_secrets, secret_spec_errors
from .filesig import cache_signature
from .manifest_convert import CURRENT, OLDER
from .manifest_rules import ManifestRules
from .scan import ScanRecord, read_scan
from .systemlist import SYSTEM_DIR

log = logging.getLogger("onemind.catalog")

# app-<id> must stay a valid Kubernetes namespace (DNS label, max 63 chars).
APP_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?$")
MANIFEST = "onemind.app.yaml"
# PLAN-E6: v1 is the frozen manifest; v1alpha1 stays readable until every app is converted.
API_VERSIONS = (CURRENT, *OLDER)  # one list, shared with the converter (manifest_convert)
# Kubernetes Secret names are DNS-1123 subdomains.
SECRET_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
LINK_KEYS = ("docs", "github", "website", "support")
TIERS = ("verified", "community", "blocked")


def _http_url(value: object) -> str | None:
    """Only absolute http(s) links reach the dashboard (never javascript: or data: URLs)."""
    if isinstance(value, str) and re.match(r"^https?://[^\s/]+", value, re.IGNORECASE):
        return value
    return None


def build_summary(raw: object) -> dict | None:
    """metadata.build for the Market: plain strings only, and only the factory's own fields."""
    if not isinstance(raw, dict) or raw.get("builder") != "onemind-app-factory":
        return None
    try:
        patched = [str(p) for p in raw.get("patched") or []]
        return {"builder": "onemind-app-factory", "revision": int(raw["revision"]), "upstream_tag": str(raw["upstreamTag"]),
                "base": str(raw["base"]), "patched": patched, "built_at": str(raw["builtAt"]), "image": str(raw["image"])}
    except (KeyError, TypeError, ValueError):
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


# metadata.licenceClass (#173). L1 permissive and L2 copyleft are green: the Market shows them by default
# and an owner approval is enough. blocked and unknown are not green: installing one needs the owner to
# confirm the licence by name (actions.py). Anything else a manifest might carry reads as unknown.
LICENCE_CLASSES = ("L1", "L2", "blocked", "unknown")
GREEN_LICENCE_CLASSES = ("L1", "L2")


@dataclass(frozen=True)
class AppEntry:
    id: str
    dir: Path
    manifest: dict

    @property
    def manifests_dir(self) -> Path:
        spec = self.manifest.get("spec") or {}
        rel = spec.get("manifests")
        if not rel:
            # Extension apps declare no workload; never fall back to an undeclared folder.
            if spec.get("extensions"):
                raise ValueError(f"app {self.id}: extension app declares no spec.manifests")
            rel = "manifests/"
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

    @property
    def licence_class(self) -> str:
        declared = (self.manifest.get("metadata") or {}).get("licenceClass")
        return declared if declared in LICENCE_CLASSES else "unknown"

    def summary(self) -> dict:
        md = self.manifest.get("metadata") or {}
        spec = self.manifest.get("spec") or {}
        # Defensive: a JSON Schema from the apps stream may be looser than builtin_check.
        requires, web, archs = spec.get("requires"), spec.get("web"), spec.get("archs")
        links = md.get("links") if isinstance(md.get("links"), dict) else {}
        scan = self.scan
        return {
            # An explicit null is a declared value the gateway does not know: "unknown" (deny), so a
            # null in a row always means "none declared" (ai_policy.catalog_visible_to_ai).
            **({"aiPolicy": UNKNOWN if catalog_policy(self.manifest) is None else catalog_policy(self.manifest)}
               if "aiPolicy" in spec or catalog_policy(self.manifest) is not None else {}),
            "id": self.id,
            "name": md.get("name"),
            "version": str(md.get("version")) if md.get("version") is not None else None,
            "description": md.get("description"),
            "category": md.get("category"),
            "icon": md.get("icon"),
            "license": md.get("license"),
            "licence_class": self.licence_class,
            "source": md.get("source"),
            "archs": list(archs) if isinstance(archs, list) else [],
            "requires": dict(requires) if isinstance(requires, dict) else {},
            "web_port": web.get("port") if isinstance(web, dict) else None,
            # #692: opened in a dashboard browser window with a per-person profile (browsers.py), not on its own name.
            "browser": isinstance(spec.get("browser"), dict) and isinstance(web, dict),
            # §11.4 additions.
            "links": {k: _http_url(links.get(k)) for k in LINK_KEYS},
            "tier": md.get("tier") if md.get("tier") in TIERS else None,
            "scan": scan.summary() if scan is not None else None,
            "build": build_summary(md.get("build")),
            # §12.22: set by a community source's entry; the official catalog has none.
            "catalog_source": None,
        }


def builtin_check(doc: object) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["manifest is not a mapping"]
    if doc.get("apiVersion") not in API_VERSIONS:
        errs.append("apiVersion must be onemind.app/v1 (or onemind.app/v1alpha1, until converted)")
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
    # H-18: the Market renders source as a link; only https:// (never javascript: or data:).
    if md.get("source") is not None and not (isinstance(md.get("source"), str) and md["source"].startswith("https://")):
        errs.append("metadata.source must be an https:// URL")
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


def _system_problem(entry: AppEntry, in_system_dir: bool, system_ids: frozenset[str]) -> str | None:
    """The system apps rules: spec.system, the apps/_system/ folder and the signed list go together."""
    claims = "system" in (entry.manifest.get("spec") or {})
    if in_system_dir:
        if entry.id not in system_ids:
            return f"{entry.id} is in apps/{SYSTEM_DIR}/ but not on the signed system apps list"
        if not claims:
            return f"{entry.id} is a system app and must declare spec.system"
        return None
    if claims:
        return "spec.system is only allowed in apps/_system/ for ids on the signed system apps list"
    if entry.id in system_ids:
        return f"{entry.id} is reserved for a system app"
    return None


class Catalog:
    def __init__(self, apps_dir: Path, schema_path: Path | None = None, channel_dir: Path | None = None):
        self.apps_dir = apps_dir
        # The signed catalog channel (`onemind catalog sync`, internal/update/catalog.go) keeps its
        # newest verified catalog under channel_dir/current -> releases/<version>. An app there
        # replaces the same id from the image (the image's apps stay the fallback).
        self.channel_dir = channel_dir
        self.schema_path = schema_path
        self._validator = None
        self._rules: ManifestRules | None = None
        if schema_path is not None and schema_path.is_file():
            from jsonschema.validators import validator_for

            schema = json.loads(schema_path.read_text())
            cls = validator_for(schema)
            cls.check_schema(schema)
            self._validator = cls(schema, format_checker=cls.FORMAT_CHECKER)
            # Manifest v1 (#604): the rules a schema cannot say, shared with the Go validator.
            self._rules = ManifestRules.for_schema(schema)
            if self._rules is None:
                log.warning("%s has no manifest v1 credential patterns; v1 block rules are off", schema_path.name)
            log.info("validating app manifests against %s", schema_path.name)
        else:
            log.info("no app schema found; using the built-in manifest check")
        self.errors: dict[str, list[str]] = {}
        # manifest path -> (stat signature, parsed AppEntry or error list). A manifest is parsed and
        # validated once, and again only when its file changes (see _outcome).
        self._parsed: dict[Path, tuple[tuple, AppEntry | list[str]]] = {}
        self.parse_count = 0  # manifests actually parsed; tests use it to prove load() is cached
        # More apps from elsewhere (community sources, §12.22): fn(official ids) -> {id: AppEntry}.
        # An id the official folder already has always wins.
        self.providers: list[Callable[[set[str]], dict[str, AppEntry]]] = []
        # The ids on the signed system apps list (systemlist.py), set by the app store. Only these
        # may live in apps/_system/ and only these may carry spec.system.
        self.system_ids: Callable[[], frozenset[str]] = lambda: frozenset()

    def validate(self, doc: object) -> list[str]:
        """The same manifest check the apps folder gets (schema, or the built-in one), plus: a manifest
        that arrives from anywhere else (a community source) may never claim spec.system."""
        errs = self._validate(doc)
        spec = doc.get("spec") if isinstance(doc, dict) else None
        if isinstance(spec, dict) and "system" in spec:
            errs.append("spec.system: only apps on the signed system apps list may claim it")
        return errs

    def check_manifest(self, doc: object) -> list[str]:
        """The folder check only (schema, or the built-in one), without the community-source rule:
        validate-apps uses it, because apps/_system/ manifests legitimately carry spec.system."""
        return self._validate(doc)

    @property
    def validation_mode(self) -> str:
        return "schema" if self._validator is not None else "builtin"

    def _validate(self, doc: object) -> list[str]:
        errs = builtin_check(doc) if self._validator is None else []
        if self._validator is not None:
            rules = self._rules
            # A schema message can quote a whole block, credential and all, and hide() only spots values
            # that look like one, not a value under a credential name. So a manifest that holds a
            # credential gets the credential errors alone (they name the field, never the value), as the
            # Go validator does by running validateCredentials before the schema.
            if rules is not None:
                cred = list(rules.credential_errors(doc))
                if cred:
                    return cred
            errs = [
                f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
                for e in self._validator.iter_errors(doc)
            ]
            if rules is not None:
                errs = [rules.hide(e) for e in errs] + rules.errors(doc)
            md = doc.get("metadata") if isinstance(doc, dict) else None
            app_id = md.get("id") if isinstance(md, dict) else None
            if not isinstance(app_id, str) or not APP_ID_RE.match(app_id):
                errs.append("metadata.id must be a lowercase DNS label (max 59 chars)")
            errs.extend(agent_spec_errors(doc.get("spec") if isinstance(doc, dict) else None))
            # Rules a JSON Schema cannot say: unique names and keys, no clash with spec.agent.
            errs.extend(secret_spec_errors(doc.get("spec") if isinstance(doc, dict) else None))
        return errs

    def _outcome(self, path: Path) -> AppEntry | list[str]:
        """The AppEntry for one manifest, or its list of errors. Parsed again only if the file changed.

        Why: yaml.safe_load is pure Python and the JSON Schema check is slow, so re-reading every
        manifest on every request made GET /v1/apps cost about 2 ms per app (perf-smoke p95 grew
        with the catalog). A file's identity (mtime, ctime, size, inode) changes whenever it is
        edited or replaced, so an edit is picked up on the next request, same as before. A manifest
        changed in the last moments is parsed but not cached (filesig.cache_signature), because a
        same-size edit within one clock tick leaves that identity unchanged.
        """
        folder = path.parent.name
        try:
            st = path.stat()
        except OSError as exc:
            return [f"cannot parse: {exc.__class__.__name__}"]
        sig = cache_signature(st)
        hit = self._parsed.get(path)
        if sig is not None and hit is not None and hit[0] == sig:
            return hit[1]
        self.parse_count += 1
        outcome: AppEntry | list[str]
        try:
            doc = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            outcome = [f"cannot parse: {exc.__class__.__name__}"]
        else:
            errs = self._validate(doc)
            if not errs and doc["metadata"]["id"] != folder:
                errs.append(f"metadata.id {doc['metadata']['id']!r} must match folder name {folder!r}")
            if errs:
                log.warning("skipping app %s: %s", folder, "; ".join(errs))
                outcome = errs
            else:
                outcome = AppEntry(id=folder, dir=path.parent, manifest=doc)
        if sig is None:
            self._parsed.pop(path, None)
        else:
            self._parsed[path] = (sig, outcome)
        return outcome

    def _channel_manifests(self) -> list[Path]:
        """Manifests of the active channel catalog, or [] when there is none.

        `current` must be a link that resolves to a folder inside channel_dir/releases: the
        gateway never follows a link out of the channel's own folder.
        """
        if self.channel_dir is None:
            return []
        try:
            real = (self.channel_dir / "current").resolve(strict=True)
            if not real.is_relative_to((self.channel_dir / "releases").resolve()):
                log.warning("catalog channel: current points outside releases/; ignored")
                return []
            apps = (real / "apps").resolve(strict=True)
            if not apps.is_relative_to(real):
                return []
            return sorted(apps.glob(f"*/{MANIFEST}"))
        except OSError:
            return []

    def load(self) -> dict[str, AppEntry]:
        """The current catalog. Lists the folder on every call (new and removed apps show at once);
        a manifest is only re-parsed when its file changed."""
        apps: dict[str, AppEntry] = {}
        errors: dict[str, list[str]] = {}
        if not self.apps_dir.is_dir():
            self.errors = {}
            self._parsed.clear()
            return apps
        paths = sorted(self.apps_dir.glob(f"*/{MANIFEST}")) + sorted(self.apps_dir.glob(f"{SYSTEM_DIR}/*/{MANIFEST}"))
        channel_paths = self._channel_manifests()
        system_ids = self.system_ids()
        for stale in set(self._parsed) - set(paths) - set(channel_paths):
            del self._parsed[stale]
        for path in paths:
            outcome = self._outcome(path)
            if isinstance(outcome, AppEntry):
                problem = _system_problem(outcome, path.parent.parent.name == SYSTEM_DIR, system_ids)
                if problem:
                    log.warning("skipping app %s: %s", outcome.id, problem)
                    errors[path.parent.name] = [problem]
                    continue
                apps[outcome.id] = outcome
            else:
                errors[path.parent.name] = list(outcome)
        for path in channel_paths:
            outcome = self._outcome(path)
            if isinstance(outcome, AppEntry):
                # System apps update only with the signed image, never from a channel.
                problem = _system_problem(outcome, False, system_ids)
                if problem:
                    log.warning("skipping channel app %s: %s", outcome.id, problem)
                    errors[f"channel/{path.parent.name}"] = [problem]
                    continue
                apps[outcome.id] = outcome  # newer than the image's copy: it wins
            else:
                # A bad channel entry never hides the image's app; it is only reported.
                errors[f"channel/{path.parent.name}"] = list(outcome)
        self.errors = errors
        for provide in self.providers:
            try:
                extra = provide(set(apps))
            except Exception:  # one broken source must not hide the official Market
                log.exception("catalog provider %r failed", provide)
                continue
            for app_id, entry in extra.items():
                apps.setdefault(app_id, entry)
        return apps

    def get(self, app_id: str) -> AppEntry | None:
        return self.load().get(app_id)
