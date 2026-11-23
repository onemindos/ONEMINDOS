# SPDX-License-Identifier: Apache-2.0
"""Gateway idle memory (issue #849, perf budget test/perf/budget.json idle_memory_mib.gateway = 100).

perf-smoke measured the idle gateway at 103.4 MiB of private ("anon") memory. Two causes are fixed and
guarded here, because perf-smoke itself only runs on main, nightly and by hand:

- glibc malloc gives each thread that allocates its own arena (a private heap). The gateway has about
  eight threads (event loop, thread pool, SQLite), so freed memory is spread over many arenas and never
  reused across them. MALLOC_ARENA_MAX=2 in both gateway units caps that (about 10 MiB on the hub).
- py_webauthn (with pyasn1, pyOpenSSL and cbor2, about 100 modules and 4 MiB) was imported at startup,
  although only the passkey ceremonies use it. It now loads on the first ceremony.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
UNITS = (
    ROOT / "deploy" / "systemd" / "onemind-gateway.service",
    ROOT / "os" / "rootfs" / "layers" / "onemind" / "usr" / "lib" / "systemd" / "system" / "onemind-gateway.service",
)
# Imported only by routes that need them, never at gateway startup (the idle hub never pays for them).
LAZY = ("webauthn",)


def _environment(unit: Path) -> dict[str, str]:
    """Environment= assignments of a systemd unit (KEY=VALUE words, several per line allowed)."""
    env: dict[str, str] = {}
    for line in unit.read_text(encoding="utf-8").splitlines():
        if line.startswith("Environment="):
            for word in line.removeprefix("Environment=").split():
                key, _, value = word.partition("=")
                env[key] = value
    return env


def test_both_gateway_units_cap_malloc_arenas():
    for unit in UNITS:
        assert _environment(unit).get("MALLOC_ARENA_MAX") == "2", unit.relative_to(ROOT)


def test_startup_does_not_import_route_only_modules(tmp_path):
    """A fresh interpreter builds the app exactly as `python -m onemind_core` does, then reports what it loaded."""
    data = tmp_path / "data"
    data.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("ONEMIND_")}
    env.update(ONEMIND_TOKENS_FILE=str(EXAMPLES / "tokens.example.yaml"), ONEMIND_DATA_DIR=str(data),
               ONEMIND_DB_URL=f"sqlite:///{data / 'onemind.db'}", ONEMIND_AUDIT_PATH=str(data / "audit.jsonl"),
               ONEMIND_NATS_URL="nats://127.0.0.1:1")
    code = ("import json, sys\n"
            "from onemind_core import serve\n"
            "from onemind_core.app import create_app\n"
            "from onemind_core.config import Settings\n"
            "app = create_app(Settings.from_env())\n"
            f"print(json.dumps(sorted(m for m in {LAZY!r} if m in sys.modules)))\n")
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path, capture_output=True, text=True,
                         timeout=120, check=True)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == []


def test_passkey_ceremony_loads_webauthn_on_demand():
    from onemind_core.identity import passkeys

    opts = passkeys.authentication_options(rp_id="hub.local", challenge=b"c" * 32, allow=[])
    assert opts["rpId"] == "hub.local" and opts["userVerification"] == "required"
    assert "webauthn" in sys.modules
