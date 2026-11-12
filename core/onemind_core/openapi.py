# SPDX-License-Identifier: Apache-2.0
"""Export the gateway's OpenAPI document without running a server (SDK.md §3.2, DEV-SDK-1).

    python -m onemind_core.openapi                 # print to stdout
    python -m onemind_core.openapi --out FILE      # write FILE
    python -m onemind_core.openapi --check FILE    # exit 1 if FILE differs (CI staleness check)

The gateway is built with throwaway settings (temporary SQLite and audit file, noop executor,
no NATS, no tokens), so the export is the same on every machine. Keys are sorted and the text
ends with a newline; the committed copy is sdk/openapi/onemind-v1.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .config import Settings


def document() -> dict:
    from .app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "apps").mkdir()
        settings = Settings(
            tokens_file=None, db_url=f"sqlite:///{t / 'export.db'}", apps_dir=t / "apps", dashboard_dist=None,
            executor="noop", nats_url=None, audit_path=t / "audit.jsonl", node_id="export", instance_name="export",
            app_schema_path=None, kubectl="kubectl", executor_timeout_s=1, host="127.0.0.1", port=8080,
        )
        return create_app(settings).openapi()


def render() -> str:
    return json.dumps(document(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m onemind_core.openapi", description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--out", type=Path, help="write the document to this file")
    g.add_argument("--check", type=Path, help="fail if this file is not the current export")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        current = args.check.read_text(encoding="utf-8") if args.check.exists() else ""
        if current != text:
            print(f"{args.check} is stale: run `make -C sdk openapi` and commit the result", file=sys.stderr)
            return 1
        return 0
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
