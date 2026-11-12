# SPDX-License-Identifier: Apache-2.0
"""Prefixed ULIDs for new tables (contract §12.1 "Ids and times": `alrt_`, `ntf_`, `chn_`, `dev_`)."""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid(now_ms: int | None = None) -> str:
    """26 characters: 48-bit millisecond time, then 80 random bits, Crockford base32."""
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    value = (ms & ((1 << 48) - 1)) << 80 | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    return f"{prefix}_{ulid()}"
