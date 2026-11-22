# SPDX-License-Identifier: Apache-2.0
"""Radio-found cards (issue #732): every USB serial line the machines report, known radios named.

The node agent (internal/detect) reports a known dongle as a radio {kind, interface: ttyACM0} only
while udev's stable name /dev/onemind/<kind>-<usb_port> exists and still matches the table in
sdk/schema/onemind.radios.json. Here each machine's USB serial lines (tty_ports) are joined with those
radios. A line with no radio is listed with kind and device null: never named, never granted. Cards
come from the latest heartbeat, so an unplugged radio is gone with the next one.

Only validated profiles reach this (nodes.py drops a profile that is not exactly NodeCapabilities).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from .apimodels import SERIAL_RADIO_KINDS
from .subjects import _SCHEMA_DIR_CANDIDATES

log = logging.getLogger("onemind.radios")

TABLE_FILE = "onemind.radios.json"
RADIO_DIR = "/dev/onemind"


@lru_cache(maxsize=1)
def table_rows() -> tuple[dict, ...]:
    """The table's rows; empty when the file is missing (cards still carry kind and port, model null)."""
    for d in _SCHEMA_DIR_CANDIDATES:
        p = d / TABLE_FILE
        if p.is_file():
            try:
                doc = json.loads(p.read_text())
                return tuple(r for r in doc["devices"] if isinstance(r, dict))
            except (OSError, ValueError, KeyError, TypeError):
                log.warning("cannot read %s; radio cards carry no model", p)
                return ()
    return ()


def label(usb_id: str | None, kind: str) -> tuple[str | None, str | None]:
    """(model, match) of a radio of kind on usb_id. The product string is not in the heartbeat, so a
    model is named only when one product of that kind uses the id; any chip row makes it chip."""
    rows = [r for r in table_rows() if r.get("id") == usb_id and r.get("kind") == kind]
    models = {r.get("model") for r in rows}
    matches = {r.get("match") for r in rows}
    model = models.pop() if len(models) == 1 else None
    match = "chip" if "chip" in matches else ("product" if "product" in matches else None)
    return model, match


def cards(nodes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n in nodes:
        caps = n.get("capabilities") or {}
        named = {r["interface"]: r["kind"] for r in caps.get("radios") or [] if r.get("kind") in SERIAL_RADIO_KINDS}
        for tp in caps.get("tty_ports") or []:
            if tp.get("kind") != "usb" or not str(tp.get("name", "")).startswith(("ttyUSB", "ttyACM")):
                continue
            port = tp.get("usb_port")
            kind = named.get(tp["name"]) if port else None
            model, match = label(tp.get("usb_id"), kind) if kind else (None, None)
            out.append({
                "node_id": n["node_id"],
                "hostname": n.get("hostname"),
                "node_status": n["status"],
                "kind": kind,
                "model": model,
                "match": match,
                "tty": tp["name"],
                "device": f"{RADIO_DIR}/{kind}-{port}" if kind else None,
                "usb_id": tp.get("usb_id"),
                "usb_port": port,
            })
    return out
