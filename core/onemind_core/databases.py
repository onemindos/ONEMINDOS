# SPDX-License-Identifier: Apache-2.0
"""Shared PostgreSQL on the hub (DB-SHARED-1): one database, role and Secret per app that asks.

An app manifest says `spec.database: {engine: postgres, secret: <name>}`. When the owner approves
its install, before any of the app's manifests are applied, the gateway:

1. makes sure the shared PostgreSQL runs (namespace `onemind-db`, StatefulSet `postgres`, the
   pinned image and Retain storage of deploy/platform/postgres/), creating it the first time an
   app needs it, so small boxes without such apps never pay for it;
2. creates role and database `app_<id>` (or gives the role a new password on a reinstall), with
   CONNECT revoked from everyone else;
3. writes Secret `<name>` in `app-<id>` with PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD and
   DATABASE_URL.

The password is random, goes to PostgreSQL on psql's stdin and to Kubernetes in the Secret, and
nowhere else: not the gateway database, not the action result, not the audit log. SQL runs through
`kubectl exec` in the PostgreSQL pod over its local socket, so the gateway needs no superuser
password and PostgreSQL needs no admin port. Removing the app keeps its database (like its
volumes, Retain); a later install of the same app gets its data back with a fresh password.

Backups: before each run the gateway dumps every app database with `pg_dump -Fc` into
`onemind-dumps/` on the PostgreSQL volume, and the agent snapshots that file as part of the app's
own unit. Restoring the app recreates its database from the restored dump (`pg_restore`).
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path

from .backups.kube import Kube, KubeError
from .backups.manifest import DatabaseSpec, database_spec, db_name
from .catalog import AppEntry
from .sections import config_section

log = logging.getLogger("onemind.databases")

_REPO_PLATFORM = Path(__file__).resolve().parents[2] / "deploy" / "platform" / "postgres"
PLATFORM_DIRS = (Path("/usr/share/onemind/platform/postgres"), Path("/opt/onemind/platform/postgres"), _REPO_PLATFORM)

STATEFULSET = "postgres"
POD = "postgres-0"
CONTAINER = "postgres"
CLAIM = "data-postgres-0"
DATA_DIR = "/var/lib/postgresql/data"
DUMP_SUBDIR = "onemind-dumps"


@config_section("databases")
@dataclass(frozen=True)
class DatabasesSettings:
    # Kustomization of the shared PostgreSQL. Unset: the image's, the developer install's, the repo's.
    platform_dir: Path | None = None
    namespace: str = "onemind-db"
    rollout_timeout_s: int = 300

    def validate(self) -> None:
        if self.namespace != "onemind-db" and not self.namespace.startswith("onemind-"):
            raise ValueError("ONEMIND_DATABASES_NAMESPACE must start with onemind-")


def _b64(v: str) -> str:
    return base64.b64encode(v.encode()).decode()


class SharedPostgres:
    def __init__(self, kube: Kube, settings: DatabasesSettings, *, dry_run: bool = False):
        self.kube = kube
        self.s = settings
        self.dry_run = dry_run

    @property
    def ns(self) -> str:
        return self.s.namespace

    @property
    def host(self) -> str:
        return f"{STATEFULSET}.{self.ns}.svc.cluster.local"

    def platform_dir(self) -> Path:
        for d in ((self.s.platform_dir,) if self.s.platform_dir else PLATFORM_DIRS):
            if d is not None and (d / "kustomization.yaml").is_file():
                return d
        raise KubeError("the shared PostgreSQL manifests were not found (ONEMIND_DATABASES_PLATFORM_DIR)")

    # ---- the platform service ----------------------------------------------------------------
    def ensure(self) -> list[dict]:
        """Create the shared PostgreSQL if it is missing, then wait until it is ready."""
        steps = []
        if not self.kube.exists("statefulset", STATEFULSET, "-n", self.ns):
            self.kube.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {
                "name": self.ns, "labels": {"app.kubernetes.io/part-of": "onemind", "onemind.io/platform": "postgres"}}})
            if not self.kube.exists("secret", "postgres-admin", "-n", self.ns):
                # Only the image's first start uses it; the gateway talks over the pod's local socket.
                self.kube.apply({"apiVersion": "v1", "kind": "Secret", "type": "Opaque", "metadata": {
                    "name": "postgres-admin", "namespace": self.ns},
                    "data": {"POSTGRES_PASSWORD": _b64(secrets.token_hex(24))}}, server_side=True)
            self.kube.run(["apply", "-k", str(self.platform_dir())])
            steps.append({"step": f"created the shared PostgreSQL in {self.ns}"})
        self.kube.run(["rollout", "status", f"statefulset/{STATEFULSET}", "-n", self.ns,
                       f"--timeout={self.s.rollout_timeout_s}s"], timeout=self.s.rollout_timeout_s + 30)
        steps.append({"step": "shared PostgreSQL is ready"})
        return steps

    def _psql(self, sql: str, db: str = "postgres") -> str:
        return self.kube.exec(self.ns, POD, ["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-U", "postgres", "-d", db, "-f", "-"],
                              container=CONTAINER, stdin=sql, timeout=120)

    # ---- per app -----------------------------------------------------------------------------
    def prepare_install(self, app: AppEntry) -> list[dict]:
        """Install hook (actions.InstallHook): database, role and Secret before the app starts."""
        spec = database_spec(app)
        if spec is None:
            return []
        name = db_name(app.id)
        if self.dry_run:
            return [{"would": f"create database and role {name} on the shared PostgreSQL",
                     "secret": f"{spec.secret} in app-{app.id}"}]
        steps = self.ensure()
        password = secrets.token_hex(24)  # [0-9a-f]: nothing to quote in SQL or in a URL
        self._psql(
            f"SELECT 'CREATE ROLE {name} LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{name}')\\gexec\n"
            f"ALTER ROLE {name} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{password}';\n"
            f"SELECT 'CREATE DATABASE {name} OWNER {name}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{name}')\\gexec\n"
            f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
            f"GRANT CONNECT, TEMPORARY ON DATABASE {name} TO {name};\n"
            # An app role reaches its own database only, not the maintenance ones either.
            "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;\n"
            "REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;\n"
        )
        steps.append({"step": f"database and role {name} ready (password rotated)"})
        self._write_secret(app.id, spec, name, password)
        steps.append({"step": f"Secret {spec.secret} written in app-{app.id}",
                      "keys": ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "DATABASE_URL"]})
        return steps

    def _write_secret(self, app_id: str, spec: DatabaseSpec, name: str, password: str) -> None:
        ns = f"app-{app_id}"
        # The executor applies the same Namespace right after; creating it here lets the Secret
        # exist before the app's pods start.
        self.kube.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": {"onemind.io/app": app_id}}})
        url = f"postgresql://{name}:{password}@{self.host}:5432/{name}"
        doc = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
               "metadata": {"name": spec.secret, "namespace": ns,
                            "labels": {"onemind.io/app": app_id, "onemind.io/database": "postgres"}},
               "data": {"PGHOST": _b64(self.host), "PGPORT": _b64("5432"), "PGDATABASE": _b64(name),
                        "PGUSER": _b64(name), "PGPASSWORD": _b64(password), "DATABASE_URL": _b64(url)}}
        # Server-side apply: no last-applied annotation carrying the password (as executors.py does).
        self.kube.apply(json.dumps(doc), namespace=ns, server_side=True)

    def volume(self) -> dict:
        """The PostgreSQL volume as the backup agent names it."""
        for p in self.kube.pvcs(self.ns):
            if p["claim"] == CLAIM and p["volume"]:
                return {"namespace": self.ns, "claim": CLAIM, "volume": p["volume"]}
        raise KubeError(f"the shared PostgreSQL volume {CLAIM} is not bound")

    def dump_file(self, app_id: str) -> dict:
        """Where app_id's dump lives, as an agent VolumeFile (no dump is taken)."""
        return {**self.volume(), "path": f"{DUMP_SUBDIR}/{db_name(app_id)}.pgdump"}

    def dump(self, app_id: str) -> dict:
        """pg_dump -Fc the app's database into the PostgreSQL volume; returns the VolumeFile."""
        name = db_name(app_id)
        final = f"{DATA_DIR}/{DUMP_SUBDIR}/{name}.pgdump"
        self.kube.exec(self.ns, POD, ["mkdir", "-p", f"{DATA_DIR}/{DUMP_SUBDIR}"], container=CONTAINER)
        self.kube.exec(self.ns, POD, ["pg_dump", "-U", "postgres", "-Fc", "-d", name, "-f", final + ".tmp"],
                       container=CONTAINER, timeout=3600)
        self.kube.exec(self.ns, POD, ["mv", "-f", final + ".tmp", final], container=CONTAINER)
        return self.dump_file(app_id)

    def restore(self, app_id: str) -> None:
        """Recreate the app's database from the dump file on the volume (the app is stopped)."""
        name = db_name(app_id)
        self._psql(
            f"DROP DATABASE IF EXISTS {name} WITH (FORCE);\n"
            f"CREATE DATABASE {name} OWNER {name};\n"
            f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
            f"GRANT CONNECT, TEMPORARY ON DATABASE {name} TO {name};\n"
        )
        self.kube.exec(self.ns, POD, ["pg_restore", "-U", "postgres", "--no-owner", f"--role={name}",
                                      "--exit-on-error", "--single-transaction", "-d", name,
                                      f"{DATA_DIR}/{DUMP_SUBDIR}/{name}.pgdump"], container=CONTAINER, timeout=3600)

    def describe(self, apps: list[AppEntry], installed: set[str]) -> list[dict]:
        out = []
        for app in apps:
            spec = database_spec(app)
            if spec is None:
                continue
            name = db_name(app.id)
            out.append({"app_id": app.id, "engine": "postgres", "database": name, "role": name,
                        "secret": spec.secret, "namespace": f"app-{app.id}", "host": self.host, "port": 5432,
                        "installed": app.id in installed})
        return out
