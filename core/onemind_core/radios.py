# SPDX-License-Identifier: Apache-2.0
"""Radio-found cards (issue #732): every USB serial line the machines report, known radios named.

The node agent (internal/detect) reports a known dongle as a radio {kind, interface: ttyUSB0, device:
/dev/onemind/lora0} only while udev's stable name exists and the USB device behind it still matches the
table in sdk/schema/onemind.radios.json. Here each machine's USB serial lines (tty_ports) are joined with
those radios. A line with no radio is listed with kind and device null: never named, never granted.
Cards come from the latest heartbeat, so an unplugged radio is gone with the next one.

A kind the table lists under `confirm` (lora) needs an owner to say what it is on its card ("MeshCore
companion (USB)") before a grant (#854) may pass it to an app: the ThinkNode-M2's CH340K id is a generic
USB-serial chip, and OneMind never probes a device to find out. The confirmation is a statement, not an
action: it opens nothing and sends nothing. It is kept in memory for that radio on that port and dropped
when a heartbeat no longer shows it (unplugged, moved, renamed) and when the gateway restarts.

Only validated profiles reach this (nodes.py drops a profile that is not exactly NodeCapabilities).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache

from .apimodels import SERIAL_RADIO_KINDS
from .ledger import iso
from .subjects import _SCHEMA_DIR_CANDIDATES

log = logging.getLogger("onemind.radios")

TABLE_FILE = "onemind.radios.json"


@lru_cache(maxsize=1)
def table() -> dict:
    """The table; {} when the file is missing (cards still carry kind and port, model null, and a
    LoRa radio still needs confirming: the confirm rule below does not depend on the file)."""
    for d in _SCHEMA_DIR_CANDIDATES:
        p = d / TABLE_FILE
        if p.is_file():
            try:
                doc = json.loads(p.read_text())
                return doc if isinstance(doc, dict) else {}
            except (OSError, ValueError):
                log.warning("cannot read %s; radio cards carry no model", p)
                return {}
    return {}


# What a LoRa radio's card asks, whatever the table file says (fail closed: never "nothing to confirm").
CONFIRM = {"lora": {"profile": "meshcore-companion-usb", "label": "MeshCore companion (USB)"}}


def label(usb_id: str | None, kind: str) -> tuple[str | None, str | None]:
    """(model, match) of a radio of kind on usb_id. The product string is not in the heartbeat, so a
    model is named only when one product of that kind uses the id; any id row makes it id."""
    rows = [r for r in table().get("devices") or [] if isinstance(r, dict) and r.get("id") == usb_id and r.get("kind") == kind]
    models = {r.get("model") for r in rows}
    matches = {r.get("match") for r in rows}
    model = models.pop() if len(models) == 1 else None
    match = "id" if "id" in matches else ("product" if "product" in matches else None)
    return model, match


Key = tuple[str, str, str, str]  # node_id, device, usb_port, usb_id


class RadioService:
    """The cards and the owners' confirmations. One per gateway (routers/nodes.py)."""

    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock
        self._lock = threading.Lock()
        self._confirmed: dict[Key, dict] = {}

    @staticmethod
    def _key(card: dict) -> Key:
        return (card["node_id"], card["device"] or "", card["usb_port"] or "", card["usb_id"] or "")

    def node_cards(self, n: dict) -> list[dict]:
        caps = n.get("capabilities") or {}
        named = {r["interface"]: r for r in caps.get("radios") or [] if r.get("kind") in SERIAL_RADIO_KINDS and r.get("device")}
        out: list[dict] = []
        for tp in caps.get("tty_ports") or []:
            if tp.get("kind") != "usb" or not str(tp.get("name", "")).startswith(("ttyUSB", "ttyACM")):
                continue
            radio = named.get(tp["name"]) if tp.get("usb_port") and tp.get("usb_id") else None
            kind = radio["kind"] if radio else None
            model, match = label(tp.get("usb_id"), kind) if kind else (None, None)
            card = {
                "node_id": n["node_id"],
                "hostname": n.get("hostname"),
                "node_status": n["status"],
                "kind": kind,
                "model": model,
                "match": match,
                "tty": tp["name"],
                "device": radio["device"] if radio else None,
                "usb_id": tp.get("usb_id"),
                "usb_port": tp.get("usb_port"),
                "confirm": None,
            }
            if kind in CONFIRM:
                with self._lock:
                    done = self._confirmed.get(self._key(card))
                card["confirm"] = {**CONFIRM[kind], "confirmed": done is not None,
                                   "confirmed_at": done["confirmed_at"] if done else None}
            out.append(card)
        return out

    def cards(self, nodes: list[dict]) -> list[dict]:
        return [c for n in nodes for c in self.node_cards(n)]

    def on_heartbeat(self, hb: dict) -> None:
        """Drop a node's confirmations for radios its latest heartbeat no longer shows (registry listener)."""
        present = {self._key(c) for c in self.node_cards({**hb, "status": "online"}) if c["kind"]}
        with self._lock:
            for k in [k for k in self._confirmed if k[0] == hb.get("node_id") and k not in present]:
                del self._confirmed[k]

    def confirm(self, card: dict, profile: str, by: dict) -> dict:
        """Record an owner's confirmation of this card. The caller checked the card is a current radio of a
        kind that needs it; this opens nothing and sends nothing."""
        with self._lock:
            self._confirmed[self._key(card)] = {"profile": profile, "confirmed_at": iso(self.clock()), "by": by["id"]}
        return card
