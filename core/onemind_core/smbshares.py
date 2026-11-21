# SPDX-License-Identifier: Apache-2.0
"""Network shares over SMB, one per person, plus a Time Machine target (FILES-SHARE-01, #235).

What this module owns is the *desired state*: which people have an SMB share of their Files home
(`home:<person>`, docs/leap/core/FILES.md) or a Time Machine share, and who approved it. The box side
(Samba and its config) is a separate program the gateway must not become: it faces the network, so it
never writes `smb.conf` or runs `smbd` itself. It hands the desired state to an `SmbHost`.

Rules this module keeps:
- Off by default. A share exists only after `files.share.create` is approved by an owner (an AI agent
  may never request it; exposing someone's files is a human call, contract §12.1, §12.3).
- One share per person and kind; a person's share maps to that person's own home and nothing else.
  Reach is LAN and mesh only; this module has no setting that could widen that.
- Removing a share (taking exposure away) is an owner-only, audited call; it is not an approval.
- The row is written before the host is asked, and kept until the host has confirmed the removal, so
  the table never under-reports what the box shares.

The gap, said plainly: no `SmbHost` exists yet. Samba is not in the image and `onemindd host serve`
has no share operation (docs/leap/core/FILE-SHARING.md has the plan, "part 2"). `NoSmbHost` says so,
the routes report `available: false`, and a request is refused with `smb_unavailable` instead of
filing an approval that could not run.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DateTime, String, delete, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .actions import FeatureAction
from .auth import Principal
from .context import Gateway
from .errors import ApiError
from .executors import ExecResult
from .files.access import HOME_ROLES
from .ledger import Base, iso
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("fileshare")  # version 1 = the shape below
ACTION = "files.share.create"
KINDS = ("home", "timemachine")
MAX_SHARES = 64
MIB = 1024**2
MIN_TM_BYTES = 1024**3          # a Mac needs room for at least one full backup and its snapshots
MAX_TM_BYTES = 10**15           # 1 PB: far above any box, exact as a JSON number
PERSON_RE = r"^[A-Za-z0-9_.@-]{1,64}$"
REACH = ["lan", "mesh"]
UNAVAILABLE = ("smb_unavailable",
               "This box has no file-sharing service yet, so nothing can be shared over SMB. "
               "Samba and its host-side service arrive with the second part of FILES-SHARE-01.")


class SmbHostError(Exception):
    """The host refused or could not do it: a stable `reason` and a sentence for the owner."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


class SmbHost(Protocol):
    """The box side. It receives the *whole* desired state each time and makes the box match it."""

    def status(self) -> tuple[bool, str, str]:
        """(available, reason, message). Reason and message explain `available == False`."""

    def apply(self, desired: list[dict]) -> None:
        """Make the shares on the box exactly `desired`. Raises SmbHostError."""


class NoSmbHost:
    def status(self) -> tuple[bool, str, str]:
        return False, *UNAVAILABLE

    def apply(self, desired: list[dict]) -> None:
        raise SmbHostError(*UNAVAILABLE)


class CreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=r"^(home|timemachine)$")
    person_id: str = Field(pattern=PERSON_RE)
    # Time Machine only: the most the backup may grow to. Without a cap a Mac fills the disk.
    quota_bytes: int | None = Field(default=None, ge=MIN_TM_BYTES, le=MAX_TM_BYTES)


class ShareRow(Base):
    __tablename__ = "fileshare_shares"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(12))                # home | timemachine
    person_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)   # the SMB share name, lower case
    quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    state: Mapped[str] = mapped_column(String(10))               # applying | active
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def root(self) -> str:
        return f"home:{self.person_id}"

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "person_id": self.person_id, "name": self.name, "root": self.root,
                "quota_bytes": int(self.quota_bytes) if self.quota_bytes is not None else None,
                "state": self.state, "reach": REACH, "created_at": iso(self.created_at)}


def share_name(kind: str, person_id: str) -> str:
    """An SMB share name: 1 to 40 characters, no characters Windows or macOS reject, lower case."""
    base = re.sub(r"[^a-z0-9_-]+", "-", person_id.lower()).strip("-")[:28] or "person"
    return base if kind == "home" else f"{base}-timemachine"


class ShareRepository(SqlRepository):
    def all(self, person_id: str | None = None) -> list[ShareRow]:
        with self.db.session() as s:
            q = select(ShareRow).order_by(ShareRow.created_at, ShareRow.id)
            if person_id is not None:
                q = q.where(ShareRow.person_id == person_id)
            rows = list(s.scalars(q))
            s.expunge_all()
            return rows

    def get(self, share_id: str) -> ShareRow | None:
        with self.db.session() as s:
            row = s.get(ShareRow, share_id)
            if row:
                s.expunge(row)
            return row

    def count(self) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(ShareRow)) or 0

    def add(self, row: ShareRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def set_state(self, share_id: str, state: str) -> None:
        with self.db.session.begin() as s:
            s.execute(update(ShareRow).where(ShareRow.id == share_id).values(state=state))

    def remove(self, share_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(ShareRow).where(ShareRow.id == share_id))


def desired(rows: list[ShareRow]) -> list[dict]:
    """What the host is told: names, owners, kinds and caps. Never a password or a host path."""
    return [{"id": r.id, "kind": r.kind, "name": r.name, "person_id": r.person_id, "root": r.root,
             "quota_bytes": int(r.quota_bytes) if r.quota_bytes is not None else None} for r in rows]


class ShareService:
    def __init__(self, gw: Gateway, host: SmbHost | None = None):
        self.gw = gw
        self.repo = ShareRepository(gw.db)
        self.host: SmbHost = host or NoSmbHost()
        self._lock = threading.Lock()

    # ---- who the household is ------------------------------------------------------------
    def people(self) -> dict[str, str]:
        """person id -> role: the tokens file, then every feature's people source (identity accounts)."""
        out: dict[str, str] = {}
        for p in self.gw.tokens.principals():
            if p.kind == "person":
                out.setdefault(p.id, p.role)
        for source in self.gw.people_sources:
            for pid, role in source().items():
                out.setdefault(pid, role)
        return out

    # ---- reads -----------------------------------------------------------------------------
    def view(self, p: Principal) -> dict:
        ok, reason, message = self.host.status()
        service = {"available": ok, "reason": None if ok else reason, "message": None if ok else message,
                   "off_by_default": True, "reach": REACH, "time_machine": True}
        people = self.people()
        mine = {p.id: people[p.id]} if p.id in people else {}
        shown = people if p.is_owner else mine
        shares = self.repo.all(None if p.is_owner else p.id)
        return {"service": service,
                "people": [{"person_id": pid, "role": role, "home": role in HOME_ROLES}
                           for pid, role in sorted(shown.items())],
                "shares": [r.to_json() for r in shares]}

    # ---- files.share.create ----------------------------------------------------------------
    def refusal(self, params: dict) -> tuple[str, str] | None:
        """Why this share cannot be filed or approved now, as (reason, message), or None."""
        ok, reason, message = self.host.status()
        if not ok:
            return reason, message
        role = self.people().get(params["person_id"])
        if role is None:
            return "unknown_person", f"There is no household member {params['person_id']}."
        if role not in HOME_ROLES:
            return "no_home", f"A {role} has no private files, so there is nothing of theirs to share."
        if params["kind"] == "timemachine" and params.get("quota_bytes") is None:
            return "quota_required", "A Time Machine share needs a size limit (quota_bytes), at least 1 GiB."
        if params["kind"] == "home" and params.get("quota_bytes") is not None:
            return "quota_not_allowed", "Only a Time Machine share has a size limit here; the Files quota covers a home."
        name = share_name(params["kind"], params["person_id"])
        for r in self.repo.all():
            if r.person_id == params["person_id"] and r.kind == params["kind"]:
                return "already_shared", f"{params['person_id']} already has this share ({r.name})."
            if r.name == name:
                return "name_taken", f"A share named {name} already exists."
        if self.repo.count() >= MAX_SHARES:
            return "too_many_shares", f"This box allows at most {MAX_SHARES} shares."
        return None

    def _check_request(self, params: dict, _: Principal) -> None:
        # Who may ask is the action ledger's rule (an owner, in this version); this is the share's own check.
        if (r := self.refusal(params)) is not None:
            raise ApiError(409, "policy_refused", r[1], reason=r[0])

    def _recheck(self, a) -> str | None:
        r = self.refusal(a.params)
        return r[1] if r else None

    def _run(self, a, finish) -> None:
        p = a.params
        with self._lock:
            now = self.gw.clock()
            row = ShareRow(id="shr_" + a.id.replace("-", "")[:24], kind=p["kind"],
                           person_id=p["person_id"], name=share_name(p["kind"], p["person_id"]),
                           quota_bytes=p.get("quota_bytes"), state="applying", action_id=a.id,
                           approved_by=a.approved_by, created_at=now)
            self.repo.add(row)  # recorded first: the table never says less than the box shares
            try:
                self.host.apply(desired(self.repo.all()))
            except SmbHostError as e:
                self.repo.remove(row.id)
                finish(ExecResult("failed", e.message, steps=[{"step": "apply shares", "share": row.name, "result": e.reason}]))
                return
            self.repo.set_state(row.id, "active")
        finish(ExecResult("succeeded", f"Share {row.name} is on, for LAN and mesh only.",
                          steps=[{"step": "apply shares", "share": row.name, "result": "active"}]))

    # ---- remove: taking exposure away, owner only -----------------------------------------
    def remove(self, share_id: str, p: Principal) -> dict:
        with self._lock:
            row = self.repo.get(share_id)
            if row is None:
                raise ApiError(404, "not_found", f"There is no share {share_id}.")
            rest = [r for r in self.repo.all() if r.id != share_id]
            try:
                self.host.apply(desired(rest))
            except SmbHostError as e:
                # Not removed: the row stays, because the box may still share it.
                raise ApiError(409, "policy_refused", e.message, reason=e.reason) from None
            self.repo.remove(share_id)
        self.gw.audit.append("fileshare.stopped", p.as_dict(), None,
                             {"share_id": share_id, "name": row.name, "person_id": row.person_id, "kind": row.kind})
        return {"removed": True, "id": share_id}

    def register(self) -> None:
        # "actuate": the box starts offering someone's files on the network.
        self.gw.actions.register_type(ACTION, FeatureAction(
            "actuate", self._run, frozenset({"person"}), check=self._recheck,
            params_model=CreateParams, check_request=self._check_request))
