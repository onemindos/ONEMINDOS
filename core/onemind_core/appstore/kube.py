# SPDX-License-Identifier: Apache-2.0
"""A minimal kubectl runner for the appstore feature: argv lists only (never a shell), stdin for
documents, a timeout on every call, and errors that never echo stdin."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[..., subprocess.CompletedProcess]


class KubeError(Exception):
    """kubectl could not run, timed out or exited non-zero. `unknown` means the effect is unknown."""

    def __init__(self, message: str, *, unknown: bool = False):
        super().__init__(message)
        self.unknown = unknown


class Kube:
    def __init__(self, kubectl: str = "kubectl", timeout_s: float = 30, runner: Runner = subprocess.run):
        self.kubectl, self.timeout_s, self.runner = kubectl, timeout_s, runner

    def run(self, args: Sequence[str], stdin: str | None = None, *, timeout_s: float | None = None) -> str:
        argv = [self.kubectl, *args]
        try:
            cp = self.runner(argv, input=stdin, capture_output=True, text=True,
                             timeout=timeout_s or self.timeout_s, check=False)
        except FileNotFoundError as exc:
            raise KubeError(f"{self.kubectl} not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise KubeError(f"kubectl {args[0]} timed out after {timeout_s or self.timeout_s}s", unknown=True) from exc
        if cp.returncode != 0:
            err = (cp.stderr or "").strip().splitlines()
            raise KubeError(f"kubectl {args[0]} exited {cp.returncode}: {err[-1][:300] if err else ''}")
        return cp.stdout or ""
