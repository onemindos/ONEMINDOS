# SPDX-License-Identifier: Apache-2.0
"""Request bodies of the secrets routes and of the approve body's `sealed` field.

Only sealed (encrypted) values are accepted: a plaintext value would sit in proxies' and
clients' request logs, and a validation error would describe it. Field limits keep a malformed
body small; error messages name fields, never values.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .crypto import MAX_SEALED_CT


class SealedInput(BaseModel):
    """`{"alg": "X25519-AES256GCM", "kid"?, "epk", "ct"}`, encrypted to GET /v1/secrets/public-key."""

    model_config = ConfigDict(extra="forbid")
    alg: str = Field(max_length=40)
    epk: str = Field(min_length=1, max_length=100)
    ct: str = Field(min_length=1, max_length=2 * MAX_SEALED_CT)
    kid: str | None = Field(default=None, max_length=64)


class SecretsChange(BaseModel):
    """POST /v1/apps/{id}/secrets: what to change. An empty body re-applies the current values."""

    model_config = ConfigDict(extra="forbid")
    sealed: SealedInput | None = None
    generate: list[str] = Field(default_factory=list, max_length=64, description="<secret>/<key> to rotate")
    clear: list[str] = Field(default_factory=list, max_length=64, description="<secret>/<key> to unset")
    reason: str | None = Field(default=None, max_length=500)
    expires_at: AwareDatetime | None = None
