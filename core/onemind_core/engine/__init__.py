# SPDX-License-Identifier: Apache-2.0
"""The Engine feed (issue #619): what the hub's NATS server says about the bus, for GET /v1/engine.

NATS is the message bus every OneMind machine talks over. The hub's nats-server publishes its own
state on a monitoring port that listens on loopback only (127.0.0.1:8222, written by
onemind-firstboot and deploy/install.sh). `monitor.MonitorReader` reads that port with a 2 second
cache and keeps only allow-listed numbers; `feed.view` turns them, the gateway's JetStream state
(#601, `gw.jetstream`) and the heartbeat registry into the answer, cut to what the caller may see.

Nothing here can change NATS: every request is a GET to the monitor, and no credential, client
address, user name, file path or subject is ever kept, so none can be returned.
"""

from .feed import EngineView, Scope, scope_for, view
from .monitor import DEFAULT_URL, MonitorError, MonitorReader, Snapshot, check_url

__all__ = ["DEFAULT_URL", "EngineView", "MonitorError", "MonitorReader", "Scope", "Snapshot", "check_url",
           "scope_for", "view"]
