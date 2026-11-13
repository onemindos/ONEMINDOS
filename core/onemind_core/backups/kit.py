# SPDX-License-Identifier: Apache-2.0
"""The emergency kit (BACKUPS.md §5): the owner recovery key, shown once, typed back to prove it.

The key is 256 random bits written as 13 groups of 4 base32 letters (A-Z, 2-7) plus a check group.
The restic password is the 13 groups joined with dashes, exactly as printed, so the owner can
restore with plain restic and no OneMind at all. The box never stores the key: only a short
fingerprint and, for the type-back check, two random groups as salted hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime

GROUPS = 13


@dataclass(frozen=True)
class OwnerKey:
    groups: tuple[str, ...]
    check: str

    @property
    def password(self) -> str:
        return "-".join(self.groups)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.password.encode()).hexdigest()[:16]


def new_owner_key() -> OwnerKey:
    raw = secrets.token_bytes(32)
    text = base64.b32encode(raw).decode().rstrip("=")  # 52 characters
    groups = tuple(text[i:i + 4] for i in range(0, 52, 4))
    check = base64.b32encode(hashlib.sha256(text.encode()).digest()).decode()[:4]
    return OwnerKey(groups, check)


def check_group_ok(groups: list[str], check: str) -> bool:
    """For a typed-in kit: does the check group match the 13 groups?"""
    text = "".join(g.strip().upper() for g in groups)
    want = base64.b32encode(hashlib.sha256(text.encode()).digest()).decode()[:4]
    return len(text) == 52 and hmac.compare_digest(want, check.strip().upper())


def _h(salt: str, value: str) -> str:
    return hashlib.sha256((salt + ":" + value.strip().upper()).encode()).hexdigest()


def challenge(key: OwnerKey) -> dict:
    """Two distinct random groups the owner must type back (1-based positions)."""
    rng = secrets.SystemRandom()
    picks = sorted(rng.sample(range(GROUPS), 2))
    salt = secrets.token_hex(16)
    return {"positions": [i + 1 for i in picks], "salt": salt, "hashes": [_h(salt, key.groups[i]) for i in picks]}


def answer_ok(ch: dict, answers: dict[str, str]) -> bool:
    ok = True
    for pos, want in zip(ch["positions"], ch["hashes"], strict=True):
        got = answers.get(str(pos), "")
        ok &= hmac.compare_digest(_h(ch["salt"], got), want)
    return ok


def kit_text(*, box_name: str, instance_id: str, key: OwnerKey, destinations: list[dict], issued_at: datetime) -> str:
    lines = [
        "ONEMIND EMERGENCY KIT",
        "=====================",
        f"Box: {box_name}    Instance: {instance_id}",
        f"Issued: {issued_at.replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        "",
        "Owner recovery key (restic password, type it exactly as printed, dashes included):",
        "",
        "    " + "-".join(key.groups),
        "",
        f"Check group: {key.check}   (proves you copied the 13 groups correctly)",
        "",
        "Keep this page offline, somewhere safe. Anyone with it and a backup disk can read your data.",
        "OneMind does not keep this key. If you lose it and the box, your backups cannot be opened.",
        "",
        "Where your backups are:",
    ]
    for d in destinations:
        cfg = d.get("config") or {}
        where = cfg.get("usb_uuid") or cfg.get("url") or "/".join(x for x in (cfg.get("endpoint"), cfg.get("bucket"), cfg.get("prefix")) if x)
        lines.append(f"  - {d['label']} ({d['kind']}): {where}")
    lines += [
        "",
        "Restore without OneMind (any computer with restic 0.19 or newer):",
        "  USB disk:     restic -r /media/<disk>/onemind-restic snapshots --tag onemind",
        "  OneMind box:  restic -r rest:https://<box>:<port>/<repo>/ snapshots --tag onemind",
        "  S3 bucket:    restic -r s3:<endpoint>/<bucket>/<prefix> snapshots --tag onemind",
        "  then:         restic -r <same> restore <snapshot-id> --target ./restored",
        "Each snapshot is tagged unit=system|k3s|app|node and app=<id>, so `--tag app=<id>` finds one app.",
        "App databases are in each app's snapshot as onemind-dumps/<db>.pgdump (pg_restore reads them).",
    ]
    return "\n".join(lines) + "\n"
