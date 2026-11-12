"""Gateway settings, read from the ONEMIND_* environment variables of contract section 1."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# Repo-relative location of the app manifest schema (owned by the apps/sdk stream).
_REPO_SCHEMA = Path(__file__).resolve().parents[2] / "sdk" / "schema" / "onemind.app.schema.json"
# Location inside the container image (the Dockerfile copies sdk/schema there when it exists).
_IMAGE_SCHEMA = Path("/opt/onemind/sdk/schema/onemind.app.schema.json")


def derive_node_id(machine_id_path: Path = Path("/etc/machine-id")) -> str | None:
    """Stable node id: sha256 of /etc/machine-id, first 12 hex chars. Never the raw machine-id."""
    try:
        raw = machine_id_path.read_text().strip()
    except OSError:
        return None
    if not raw:
        return None
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


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
        return cls(
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
        )
