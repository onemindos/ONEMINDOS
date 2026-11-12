# SPDX-License-Identifier: Apache-2.0
"""WebAuthn ceremonies over py_webauthn (BSD-3-Clause). Pure functions; state lives in service.py."""

from __future__ import annotations

import json
from typing import Any

import webauthn
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .crypto import b64url, unb64url

TIMEOUT_MS = 120_000


class PasskeyError(ValueError):
    """The browser's response did not verify (bad signature, wrong origin, wrong challenge, ...)."""


def normalize(credential: Any) -> dict:
    """Accept the WebAuthn JSON shape ({id, rawId, response: {...}, type}) or the flat §12.4 one
    ({id, clientDataJSON, authenticatorData, signature, userHandle?})."""
    if not isinstance(credential, dict) or not isinstance(credential.get("id"), str):
        raise PasskeyError("credential must be an object with an id")
    if isinstance(credential.get("response"), dict):
        out = dict(credential)
        out.setdefault("rawId", credential["id"])
        out.setdefault("type", "public-key")
        return out
    response = {k: credential[k] for k in ("clientDataJSON", "authenticatorData", "signature", "userHandle",
                                           "attestationObject", "transports") if credential.get(k) is not None}
    return {"id": credential["id"], "rawId": credential["id"], "response": response, "type": "public-key"}


def client_challenge(credential: dict) -> str:
    """The base64url challenge the browser signed, read from clientDataJSON (verified again later)."""
    try:
        data = json.loads(unb64url(credential["response"]["clientDataJSON"]))
        challenge = data["challenge"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PasskeyError("clientDataJSON is missing or malformed") from exc
    if not isinstance(challenge, str) or not 16 <= len(challenge) <= 128:
        raise PasskeyError("clientDataJSON challenge is malformed")
    return challenge


def _descriptors(ids: list[str]) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=unb64url(i)) for i in ids]


def registration_options(*, rp_id: str, rp_name: str, user_id: str, user_name: str, display_name: str,
                         challenge: bytes, exclude: list[str]) -> dict:
    opts = webauthn.generate_registration_options(
        rp_id=rp_id, rp_name=rp_name, user_id=user_id.encode(), user_name=user_name,
        user_display_name=display_name, challenge=challenge, timeout=TIMEOUT_MS,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=_descriptors(exclude),
    )
    return json.loads(webauthn.options_to_json(opts))


def authentication_options(*, rp_id: str, challenge: bytes, allow: list[str]) -> dict:
    opts = webauthn.generate_authentication_options(
        rp_id=rp_id, challenge=challenge, timeout=TIMEOUT_MS, allow_credentials=_descriptors(allow),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return json.loads(webauthn.options_to_json(opts))


def verify_registration(*, credential: dict, challenge: bytes, rp_id: str, origins: list[str]) -> dict:
    try:
        v = webauthn.verify_registration_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=rp_id,
            expected_origin=origins, require_user_verification=True,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as exc:
        raise PasskeyError(f"registration did not verify: {exc}") from exc
    transports = credential.get("response", {}).get("transports") or []
    return {"id": b64url(v.credential_id), "public_key": v.credential_public_key, "sign_count": v.sign_count,
            "transports": [t for t in transports if isinstance(t, str)][:8]}


def verify_assertion(*, credential: dict, challenge: bytes, rp_id: str, origins: list[str],
                     public_key: bytes, sign_count: int) -> int:
    """Returns the new sign count."""
    try:
        v = webauthn.verify_authentication_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=rp_id, expected_origin=origins,
            credential_public_key=public_key, credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError) as exc:
        raise PasskeyError(f"assertion did not verify: {exc}") from exc
    return v.new_sign_count
