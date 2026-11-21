# SPDX-License-Identifier: Apache-2.0
"""The link to the host executor (#146, #142): no routes of its own.

It makes the one `HostLink` the gateway uses (`app.state.hostlink`) and runs its poller, so a feature
that acts on the box (OS updates now; restart, shutdown and factory reset, #355) shares one client and
one journal reader. Registered before those features, which read `app.state.hostlink`.
"""

from __future__ import annotations

from fastapi import FastAPI

from ..context import Gateway
from ..hostlink import HostLink

ORDER = 20  # before every feature that acts on the host


def register(app: FastAPI, gw: Gateway) -> None:
    link = HostLink(gw)
    app.state.hostlink = link
    gw.on_startup(link.start)
    gw.on_shutdown(link.stop)
