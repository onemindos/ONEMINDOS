# SPDX-License-Identifier: Apache-2.0
"""Radio-found cards (issue #732): every USB serial line the machines report, known radios named.

The node agent (internal/detect) reports a known dongle as a radio {kind, interface: ttyUSB0, device:
/dev/onemind/lora0} only while udev's stable name exists and the USB device behind it still matches the
table in sdk/schema/onemind.radios.json. Here each machine's USB serial lines (tty_ports) are joined with
those radios. A line with no radio is listed with kind and device null: never named, never granted.
Cards come from the latest heartbeat, so an unplugged radio is gone with the next one.

A card for a known radio carries a stable id, `<node_id>.<kind><n>` (3f9c2a1b7d4e.lora0): the machine plus
the stable name udev gave it. Every later radio route addresses a radio by it (/v1/radios/{id}/...).

A kind the table lists under `confirm` (lora) needs an owner to say what it is on its card ("MeshCore
companion (USB)") before a grant (#854) may pass it to an app: the ThinkNode-M2's CH340K id is a generic
USB-serial chip, and OneMind never probes a device to find out. The confirmation is a statement, not an
action: it opens nothing and sends nothing. It is stored in the gateway database for that radio on that
machine and USB port (kind, port, USB id), so a gateway restart, an OS update or unplugging and plugging
the radio back into the same port keeps it; the same radio on another port needs a new one.

Only validated profiles reach this (nodes.py drops a profile that is not exactly NodeCapabilities).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .apimodels import RADIO_ID, SERIAL_RADIO_KINDS
from .ledger import Base, iso
from .store import Database, FeatureSchema, SqlRepository
from .subjects import _SCHEMA_DIR_CANDIDATES

log = logging.getLogger("onemind.radios")

TABLE_FILE = "onemind.radios.json"

SCHEMA = FeatureSchema("radios")  # v1 = the shape below


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


def radio_id(node_id: str, device: str) -> str:
    """The stable id of the radio named `device` on `node_id`: 3f9c2a1b7d4e.lora0 (apimodels.RADIO_ID)."""
    return f"{node_id}.{device.rsplit('/', 1)[-1]}"


def parse_radio_id(rid: str) -> tuple[str, str] | None:
    """(node_id, device) of a radio id, None when it is not one."""
    if not re.match(RADIO_ID, rid):
        return None
    node_id, name = rid.rsplit(".", 1)
    return node_id, f"/dev/onemind/{name}"


class RadioConfirmationRow(Base):
    """An owner's confirmation of a radio: the machine, the kind and the physical USB port and id it is on."""

    __tablename__ = "radios_confirmations"
    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    usb_port: Mapped[str] = mapped_column(String(64), primary_key=True)
    usb_id: Mapped[str] = mapped_column(String(9), primary_key=True)
    profile: Mapped[str] = mapped_column(String(64))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str] = mapped_column(String(200))


Key = tuple[str, str, str, str]  # node_id, kind, usb_port, usb_id


class RadioService(SqlRepository):
    """The cards and the owners' confirmations. One per gateway (routers/radios.py)."""

    def __init__(self, db: Database, clock: Callable[[], datetime]):
        super().__init__(db)
        self.clock = clock

    @staticmethod
    def _key(card: dict) -> Key:
        return (card["node_id"], card["kind"] or "", card["usb_port"] or "", card["usb_id"] or "")

    def _confirmed(self, node_id: str) -> dict[Key, RadioConfirmationRow]:
        with self.db.session() as s:
            rows = s.scalars(select(RadioConfirmationRow).where(RadioConfirmationRow.node_id == node_id)).all()
        return {(r.node_id, r.kind, r.usb_port, r.usb_id): r for r in rows}

    def node_cards(self, n: dict) -> list[dict]:
        caps = n.get("capabilities") or {}
        named = {r["interface"]: r for r in caps.get("radios") or [] if r.get("kind") in SERIAL_RADIO_KINDS and r.get("device")}
        confirmed: dict[Key, RadioConfirmationRow] | None = None
        out: list[dict] = []
        for tp in caps.get("tty_ports") or []:
            if tp.get("kind") != "usb" or not str(tp.get("name", "")).startswith(("ttyUSB", "ttyACM")):
                continue
            radio = named.get(tp["name"]) if tp.get("usb_port") and tp.get("usb_id") else None
            kind = radio["kind"] if radio else None
            model, match = label(tp.get("usb_id"), kind) if kind else (None, None)
            card = {
                "id": radio_id(n["node_id"], radio["device"]) if radio else None,
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
                if confirmed is None:
                    confirmed = self._confirmed(n["node_id"])
                done = confirmed.get(self._key(card))
                ok = done is not None and done.profile == CONFIRM[kind]["profile"]
                card["confirm"] = {**CONFIRM[kind], "confirmed": ok, "confirmed_at": iso(done.confirmed_at) if ok else None}
            out.append(card)
        return out

    def cards(self, nodes: list[dict]) -> list[dict]:
        return [c for n in nodes for c in self.node_cards(n)]

    def confirm(self, card: dict, profile: str, by: dict) -> dict:
        """Record an owner's confirmation of this card. The caller checked the card is a current radio of a
        kind that needs it; this opens nothing and sends nothing."""
        node_id, kind, usb_port, usb_id = self._key(card)
        values = {"profile": profile, "confirmed_at": self.clock(), "confirmed_by": by["id"]}
        insert = self.db.insert()(RadioConfirmationRow).values(node_id=node_id, kind=kind, usb_port=usb_port, usb_id=usb_id, **values)
        with self.db.session.begin() as s:
            s.execute(insert.on_conflict_do_update(
                index_elements=[RadioConfirmationRow.node_id, RadioConfirmationRow.kind,
                                RadioConfirmationRow.usb_port, RadioConfirmationRow.usb_id], set_=values))
        return card
