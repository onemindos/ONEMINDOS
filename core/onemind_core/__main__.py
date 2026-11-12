"""Run the gateway: `python -m onemind_core` (ONEMIND_HOST:ONEMIND_PORT, default :8080; HTTPS: serve.py)."""

from __future__ import annotations

import logging

from . import serve
from .app import create_app
from .config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    serve.run(create_app(settings), settings)  # HTTP, or HTTPS + redirect with ONEMIND_NET_TLS=1


if __name__ == "__main__":
    main()
