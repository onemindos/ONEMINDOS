"""Gateway settings, read from the ONEMIND_* environment variables of contract section 1."""

from __future__ import annotations

import hashlib
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

from .sections import load_section, load_sections, section_name

T = TypeVar("T")

# Repo-relative location of the app manifest schema (owned by the apps/sdk stream).
_REPO_SCHEMA = Path(__file__).resolve().parents[2] / "sdk" / "schema" / "onemind.app.schema.json"
# Location inside the container image (the Dockerfile copies sdk/schema there when it exists).
_IMAGE_SCHEMA = Path("/opt/onemind/sdk/schema/onemind.app.schema.json")


MACHINE_ID_PATHS = (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))


def _hash_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def derive_node_id(paths: tuple[Path, ...] = MACHINE_ID_PATHS, hostname: str | None = None) -> str:
    """Stable node id, the same chain onemindd uses (contract section 1); never the raw machine-id.

    sha256(/etc/machine-id), else sha256(/var/lib/dbus/machine-id), else sha256("hostname:" +
    hostname), first 12 hex characters each. Never None, so /v1/instance always has a string.
    """
    for path in paths:
        try:
            raw = path.read_text().strip()
        except OSError:
            continue
        if raw:
            return _hash_id(raw)
    return _hash_id("hostname:" + (hostname or socket.gethostname() or "unknown"))


def _opt_path(value: str | None) -> Path | None:
    return Path(value) if value else None


@dataclass(frozen=True)
class Settings:
    tokens_file: Path | None
    db_url: str
    apps_dir: Path
    dashboard_dist: Path | None
    executor: str
    nats_url: str | None
    audit_path: Path
    node_id: str | None
    instance_name: str
    app_schema_path: Path | None
    kubectl: str
    executor_timeout_s: float
    host: str
    port: int
    # §11.2: the gateway URL written into an app's agent Secret. None = derived (gateway_url()).
    public_url: str | None = None
    # §11.1 dev override: skip the §10.3 scan check. Only honoured with the noop executor.
    allow_unscanned: bool = False
    # Per-feature sections (sections.py), keyed by section name. Read them with section().
    sections: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def section(self, cls: type[T]) -> T:
        """The loaded settings section `cls`; its defaults if Settings was built without it."""
        found = self.sections.get(section_name(cls))
        return found if found is not None else load_section(cls, {})

    def gateway_url(self) -> str:
        """ONEMIND_PUBLIC_URL, else http://<host>:<port>.

        A wildcard listen address is replaced by this machine's hostname: on the hub, k3s's
        CoreDNS resolves node hostnames (its NodeHosts entries), so app pods can reach it.
        """
        if self.public_url:
            return self.public_url
        host = self.host
        if host in ("", "0.0.0.0", "::", "[::]"):
            host = socket.gethostname() or "localhost"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"

    def check(self) -> None:
        """Startup refusals that do not depend on how Settings was built."""
        if self.allow_unscanned and self.executor != "noop":
            raise ValueError(
                "ONEMIND_ALLOW_UNSCANNED=1 is refused with the kubernetes executor "
                "(contract §11.1: nothing unscanned runs)"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        data_dir = Path(env.get("ONEMIND_DATA_DIR", "./data"))
        schema = _opt_path(env.get("ONEMIND_APP_SCHEMA"))
        if schema is None:
            schema = next((p for p in (_REPO_SCHEMA, _IMAGE_SCHEMA) if p.is_file()), None)
        executor = env.get("ONEMIND_EXECUTOR", "noop")
        if executor not in ("noop", "kubernetes"):
            raise ValueError(f"ONEMIND_EXECUTOR must be 'noop' or 'kubernetes', got {executor!r}")
        nats_url = env.get("ONEMIND_NATS_URL", "nats://127.0.0.1:4222")
        public_url = (env.get("ONEMIND_PUBLIC_URL") or "").strip().rstrip("/") or None
        if public_url is not None:
            parsed = urlsplit(public_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("ONEMIND_PUBLIC_URL must be an http:// or https:// URL")
        allow = env.get("ONEMIND_ALLOW_UNSCANNED", "").strip().lower()
        if allow not in ("", "0", "false", "no", "1", "true", "yes"):
            raise ValueError("ONEMIND_ALLOW_UNSCANNED must be 1 or 0")
        settings = cls(
            tokens_file=_opt_path(env.get("ONEMIND_TOKENS_FILE")),
            db_url=env.get("ONEMIND_DB_URL", f"sqlite:///{data_dir / 'onemind.db'}"),
            apps_dir=Path(env.get("ONEMIND_APPS_DIR", "./apps")),
            dashboard_dist=_opt_path(env.get("ONEMIND_DASHBOARD_DIST")),
            executor=executor,
            nats_url=nats_url or None,
            audit_path=Path(env.get("ONEMIND_AUDIT_PATH", str(data_dir / "audit.jsonl"))),
            node_id=env.get("ONEMIND_NODE_ID") or derive_node_id(),
            instance_name=env.get("ONEMIND_INSTANCE_NAME", "OneMind"),
            app_schema_path=schema,
            kubectl=env.get("ONEMIND_KUBECTL", "kubectl"),
            executor_timeout_s=float(env.get("ONEMIND_EXECUTOR_TIMEOUT_S", "300")),
            host=env.get("ONEMIND_HOST", "0.0.0.0"),
            port=int(env.get("ONEMIND_PORT", "8080")),
            public_url=public_url,
            allow_unscanned=allow in ("1", "true", "yes"),
            sections=load_sections(env),
        )
        settings.check()
        return settings
