# SPDX-License-Identifier: Apache-2.0
"""Signed jobs to the backup agent (contract §12.11 `onemind.job/v1`; FABRIC.md §5.4).

The envelope is signed over canonical JSON: `json.dumps(sort_keys=True, separators=(",", ":"),
ensure_ascii=True)`. internal/backup/canonical.go produces the same bytes (a shared test vector
checks it), so the agent verifies exactly what the gateway signed. Floats are refused on both
sides because their text form differs between languages.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

log = logging.getLogger("onemind.backups")

JOB_SCHEMA = "onemind.job/v1"
JOB_TTL = timedelta(minutes=10)


def _check_no_floats(obj: object, where: str = "params") -> None:
    if isinstance(obj, float):
        raise TypeError(f"{where}: floats are not allowed in signed jobs")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"{where}: keys must be strings")
            _check_no_floats(v, f"{where}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check_no_floats(v, f"{where}[{i}]")


def canonical(obj: object) -> bytes:
    _check_no_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_or_create_job_key(path: Path) -> Ed25519PrivateKey:
    """The gateway's job key (PEM PKCS#8, 0600); created with its public half on first use."""
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"{path.name} is not an Ed25519 key")
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = path.with_suffix(".pub")
    pub.write_bytes(public_pem(key))
    pub.chmod(0o644)
    log.info("created the backup job key and %s", pub.name)
    return key


def public_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def sign_job(
    key: Ed25519PrivateKey, kind: str, params: dict, now: datetime, *, action_id: str | None = None,
    ttl: timedelta = JOB_TTL,
) -> dict:
    env = {
        "schema": JOB_SCHEMA,
        "job_id": "job_" + secrets.token_hex(13),
        "action_id": action_id,
        "kind": kind,
        "params": params,
        "params_sha256": "sha256:" + hashlib.sha256(canonical(params)).hexdigest(),
        "issued_at": _iso(now),
        "expires_at": _iso(now + ttl),
    }
    env["sig"] = base64.b64encode(key.sign(canonical(env))).decode("ascii")
    return env


class AgentError(Exception):
    """The agent could not be reached, refused the envelope, or the job failed."""

    def __init__(self, kind: str, message: str, *, reason: str, result: object = None):
        super().__init__(message)
        self.kind = kind
        self.reason = reason  # agent_unreachable | refused:<code> | failed
        self.result = result


class AgentClient:
    """Posts signed jobs to the agent's loopback API (`POST /api/v1/backup/jobs`)."""

    def __init__(self, url: str, key: Ed25519PrivateKey, clock: Callable[[], datetime], timeout_s: float):
        self.url = url.rstrip("/") + "/api/v1/backup/jobs"
        self.key = key
        self.clock = clock
        self.timeout_s = timeout_s

    def _post(self, kind: str, params: dict, action_id: str | None, timeout: float | None):
        body = json.dumps(sign_job(self.key, kind, params, self.clock(), action_id=action_id)).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=timeout or self.timeout_s)  # noqa: S310 (loopback URL, validated)
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"{}")
            except ValueError:
                detail = {}
            code = detail.get("error", str(e.code))
            raise AgentError(kind, f"the backup agent refused the job: {detail.get('detail', e.reason)}",
                             reason=f"refused:{code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise AgentError(kind, f"the backup agent is not reachable ({e.__class__.__name__})",
                             reason="agent_unreachable") from None

    def job(self, kind: str, params: dict, *, action_id: str | None = None, timeout: float | None = None) -> object:
        with self._post(kind, params, action_id, timeout) as resp:
            out = json.loads(resp.read() or b"{}")
        if out.get("state") != "succeeded":
            raise AgentError(kind, out.get("error") or "the job failed", reason="failed", result=out.get("result"))
        return out.get("result")

    def file(self, params: dict, chunk: int = 1 << 16) -> tuple[Iterator[bytes], dict]:
        """Stream one file out of a snapshot. A body shorter than Content-Length raises."""
        resp = self._post("backup.file", params, None, None)
        if resp.headers.get("OneMind-Job-State") != "succeeded":
            with resp:
                out = json.loads(resp.read() or b"{}")
            raise AgentError("backup.file", out.get("error") or "the file could not be read", reason="failed")
        headers = {"Content-Length": resp.headers.get("Content-Length", "0"),
                   "name": resp.headers.get("OneMind-File-Name", "file")}

        def gen() -> Iterator[bytes]:
            with resp:
                while True:
                    b = resp.read(chunk)
                    if not b:
                        return
                    yield b

        return gen(), headers
