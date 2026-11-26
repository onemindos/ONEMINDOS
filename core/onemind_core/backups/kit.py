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
import re
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


_NOT_BASE32 = re.compile(r"[^A-Z2-7]")


def parse_typed_key(typed: str) -> str | None:
    """The owner key as typed at the box's console: dashes, spaces and case do not matter, and the check
    group may follow the 13 groups. Returns the password exactly as printed, or None when it is not a
    whole kit key (wrong length, or the check group does not match: a typo, not a guess)."""
    text = _NOT_BASE32.sub("", typed.upper())
    if len(text) == 56:
        text, check = text[:52], text[52:]
        if not check_group_ok([text[i:i + 4] for i in range(0, 52, 4)], check):
            return None
    if len(text) != 52:
        return None
    return "-".join(text[i:i + 4] for i in range(0, 52, 4))


def fingerprint_of(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()[:16]


def verifier(password: str) -> dict:
    """What the box keeps to check a key typed at its console (D-028): a random salt and the full SHA-256 of
    salt + key. The key has 256 random bits, so the hash cannot be searched; and unlike the 16-hex-digit
    fingerprint (64 bits, shown on screen and in events) it is never shown anywhere."""
    salt = secrets.token_hex(16)
    return {"salt": salt, "hash": hashlib.sha256((salt + ":" + password).encode()).hexdigest()}


def verifier_ok(v: dict, password: str) -> bool:
    got = hashlib.sha256((str(v.get("salt", "")) + ":" + password).encode()).hexdigest()
    return hmac.compare_digest(got, str(v.get("hash", "")))


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


def kit_text(*, box_name: str, instance_id: str, key: OwnerKey, destinations: list[dict], issued_at: datetime,
             disk_key: str | None = None, disk_key_marker: dict | None = None) -> str:
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
    ]
    if disk_key:
        lines += [
            "Disk recovery key (unlocks this box's encrypted data disk if its automatic unlock fails;",
            "type it at the box's own console when the boot prompt asks):",
            "",
            "    " + disk_key,
            "",
            "Shown once, on this page only. The box does not keep it.",
            "",
        ]
    elif disk_key_marker:
        lines += [
            "Disk recovery key: it is NOT on this page. It was printed once, on the kit issued "
            f"{disk_key_marker.get('issued_at')} (fingerprint {disk_key_marker.get('fingerprint')}).",
            "Keep that page: the box no longer holds the disk key and cannot show it again.",
            "",
        ]
    lines += ["Owner access at the box: if you lose every passkey, open the box's rescue console on the box itself",
              "and type the owner recovery key above. Nothing is deleted and the disk stays encrypted.", ""]
    lines.append("Where your backups are:" if destinations else "Where your backups are: none yet (add a backup destination, then issue a new kit to cover it).")
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
