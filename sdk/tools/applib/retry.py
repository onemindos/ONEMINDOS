# SPDX-License-Identifier: Apache-2.0
"""Bounded retry for registry pulls, and registry credentials for them (no network in this module).

Why: every app image is pulled by crane, Trivy and cosign. Docker Hub and ghcr.io answer a burst of
pulls from shared CI runners with TOOMANYREQUESTS / 429, and registries sometimes drop a connection
or answer 5xx. Those are temporary: waiting a little and asking again works. A real failure (image
not found, signature invalid, CVE) is never retried, so the gate's verdicts do not change; only how
patient it is with the network does.
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import tempfile
import time
from pathlib import Path
from typing import Callable

ATTEMPTS = 5
BASE_DELAY = 2.0   # seconds; doubles each retry (2, 4, 8, 16), then jitter
MAX_DELAY = 120.0  # also caps a Retry-After a registry asks for

# What a temporary registry or network failure looks like in crane, Trivy and cosign output.
# Deliberately narrow: "not found", "unauthorized" and "denied" are real answers and never match.
TRANSIENT_RE = re.compile(
    r"TOOMANYREQUESTS|too many requests|rate limit|\b429\b"
    r"|(?:status(?: code)?|http|error)[: ]+(?:5\d\d)\b"
    r"|\b50[0-4] (?:internal server error|bad gateway|service unavailable|gateway time-?out)"
    r"|connection reset|connection refused|broken pipe|unexpected eof|tls handshake timeout"
    r"|i/o timeout|timeout awaiting response|temporary failure|server misbehaving|http2: server sent goaway",
    re.IGNORECASE,
)
RETRY_AFTER_RE = re.compile(r"retry[- ]after[\"':= ]+(\d{1,5})", re.IGNORECASE)


def is_transient(text: str) -> bool:
    return bool(TRANSIENT_RE.search(text or ""))


def retry_after(text: str) -> float | None:
    m = RETRY_AFTER_RE.search(text or "")
    return float(m.group(1)) if m else None


def delay_for(attempt: int, text: str = "", *, base: float = BASE_DELAY, cap: float = MAX_DELAY,
              rand: Callable[[], float] = random.random) -> float:
    """Seconds to wait before retry number `attempt` (0 = after the first failure).

    A Retry-After the registry sent wins (capped); otherwise exponential backoff. Jitter of up to
    +50% keeps parallel matrix jobs from retrying in lockstep."""
    asked = retry_after(text)
    wait = min(asked, cap) if asked is not None else min(cap, base * (2 ** attempt))
    return wait * (1 + 0.5 * rand())


def run_retry(runner: Callable, argv: list[str], *, attempts: int = ATTEMPTS,
              sleep: Callable[[float], None] | None = None,
              rand: Callable[[], float] = random.random, **kwargs):
    """runner(argv, **kwargs) -> CompletedProcess, repeated while it fails with a transient error."""
    for attempt in range(attempts):
        proc = runner(argv, **kwargs)
        if proc.returncode == 0 or attempt == attempts - 1:
            return proc
        text = (proc.stderr or "") + "\n" + (proc.stdout or "")[-2000:]
        if not is_transient(text):
            return proc
        wait = delay_for(attempt, text, rand=rand)
        print(f"retry: {argv[0].rsplit('/', 1)[-1]} hit a temporary registry/network error; "
              f"attempt {attempt + 2}/{attempts} in {wait:.0f}s", flush=True)
        (sleep or time.sleep)(wait)
    return proc  # pragma: no cover (attempts >= 1)


def retry_call(fn: Callable, exc_types: tuple, *, attempts: int = ATTEMPTS,
               sleep: Callable[[float], None] | None = None,
               rand: Callable[[], float] = random.random):
    """fn() raising one of exc_types with a transient message is repeated; anything else propagates."""
    for attempt in range(attempts):
        try:
            return fn()
        except exc_types as exc:
            if attempt == attempts - 1 or not is_transient(str(exc)):
                raise
            wait = delay_for(attempt, str(exc), rand=rand)
            print(f"retry: temporary registry/network error; attempt {attempt + 2}/{attempts} in {wait:.0f}s",
                  flush=True)
            (sleep or time.sleep)(wait)


# --- registry credentials --------------------------------------------------------------------

def docker_auths(env: dict) -> dict:
    """{registry: {"auth": base64(user:token)}} for the credentials present in env.

    ghcr.io: GITHUB_TOKEN (the workflow's read-only token; any user name works with a token).
    Docker Hub: only if DOCKERHUB_USERNAME and DOCKERHUB_TOKEN are both set (none exist yet)."""
    def entry(user: str, secret: str) -> dict:
        return {"auth": base64.b64encode(f"{user}:{secret}".encode()).decode()}
    auths = {}
    if env.get("GITHUB_TOKEN"):
        auths["ghcr.io"] = entry(env.get("GITHUB_ACTOR") or "onemind-ci", env["GITHUB_TOKEN"])
    if env.get("DOCKERHUB_USERNAME") and env.get("DOCKERHUB_TOKEN"):
        auths["https://index.docker.io/v1/"] = entry(env["DOCKERHUB_USERNAME"], env["DOCKERHUB_TOKEN"])
    return auths


def setup_registry_auth(env: dict | None = None, parent: str | None = None) -> Path | None:
    """Write a private docker config.json and point DOCKER_CONFIG at it, so crane, Trivy and cosign
    (all read it) authenticate. Returns the directory, or None when there is nothing to log in with.
    The secret goes only into a 0600 file in a 0700 temp dir; it is never printed or put in argv."""
    env = os.environ if env is None else env
    auths = docker_auths(env)
    if not auths:
        return None
    d = Path(tempfile.mkdtemp(prefix="onemind-docker-", dir=parent))  # mkdtemp is 0700
    cfg = d / "config.json"
    fd = os.open(cfg, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"auths": auths}, fh)
    env["DOCKER_CONFIG"] = str(d)
    return d
