# SPDX-License-Identifier: Apache-2.0
"""WebAuthn ceremonies over py_webauthn (BSD-3-Clause). Pure functions; state lives in service.py.

py_webauthn is imported inside each ceremony, not at module import: with pyasn1, pyOpenSSL and cbor2 it is
about 100 modules and 4 MiB that an idle gateway never needs (perf budget, issue #849).
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from .crypto import b64url, unb64url

if TYPE_CHECKING:
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor

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
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor

    return [PublicKeyCredentialDescriptor(id=unb64url(i)) for i in ids]


def registration_options(*, rp_id: str, rp_name: str, user_id: str, user_name: str, display_name: str,
                         challenge: bytes, exclude: list[str]) -> dict:
    import webauthn
    from webauthn.helpers.structs import (
        AttestationConveyancePreference,
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    # "direct" (design 3.11): a security key may then prove its make and model, which L2 needs. A phone's
    # synced passkey answers "none" anyway, and the browser may ask the person first; either way the key
    # still enrols, at L1.
    opts = webauthn.generate_registration_options(
        rp_id=rp_id, rp_name=rp_name, user_id=user_id.encode(), user_name=user_name,
        user_display_name=display_name, challenge=challenge, timeout=TIMEOUT_MS,
        attestation=AttestationConveyancePreference.DIRECT,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=_descriptors(exclude),
    )
    return json.loads(webauthn.options_to_json(opts))


def authentication_options(*, rp_id: str, challenge: bytes, allow: list[str]) -> dict:
    import webauthn
    from webauthn.helpers.structs import UserVerificationRequirement

    opts = webauthn.generate_authentication_options(
        rp_id=rp_id, challenge=challenge, timeout=TIMEOUT_MS, allow_credentials=_descriptors(allow),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return json.loads(webauthn.options_to_json(opts))


def _strip_attestation(credential: dict) -> dict | None:
    """The same response with its attestation replaced by "none" (authData untouched), or None when the
    attestation object can't be read. Verifying that copy proves exactly what a "none" response proves:
    challenge, origin, RP id and user verification, never the model."""
    import cbor2

    try:
        att = cbor2.loads(unb64url(credential["response"]["attestationObject"]))
        auth_data = att["authData"]
    except (KeyError, TypeError, ValueError, cbor2.CBORDecodeError):
        return None
    out = json.loads(json.dumps(credential))
    out["response"]["attestationObject"] = b64url(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data}))
    return out


AAGUID_EXT = "1.3.6.1.4.1.45724.1.1.4"  # id-fido-gen-ce-aaguid


def _leaf_aaguid_matches(leaf_der: bytes, aaguid: str) -> bool:
    """WebAuthn §8.2.1 (packed): when the attestation certificate names a model, it must be the model in
    authenticatorData. py_webauthn 3.0.1 does not check this, so a model claim is checked here."""
    from cryptography import x509

    try:
        cert = x509.load_der_x509_certificate(leaf_der)
        ext = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(AAGUID_EXT)).value
    except x509.ExtensionNotFound:
        return True
    except ValueError:
        return False
    raw = getattr(ext, "value", b"")
    return len(raw) == 18 and raw[:2] == b"\x04\x10" and raw[2:].hex() == aaguid.replace("-", "")


def verify_registration(*, credential: dict, challenge: bytes, rp_id: str, origins: list[str],
                        roots_for: Any = None) -> dict:
    """Verify a registration and report what its attestation proves.

    roots_for(aaguid) -> list of PEM roots for that model on the allow-list (empty when untrusted). The
    attestation counts only when its chain leads to one of those roots: a chain checked against no
    root proves nothing (py_webauthn then skips the root check), so it is checked again here.
    A response whose attestation can't be verified at all (an unknown format, an outdated root) still
    enrols, as "none": the device check (UV) is what L1 needs.
    """
    import webauthn
    from webauthn.helpers import parse_attestation_object
    from webauthn.helpers.exceptions import WebAuthnException

    def run(cred: dict, roots: dict | None = None):
        return webauthn.verify_registration_response(
            credential=cred, expected_challenge=challenge, expected_rp_id=rp_id,
            expected_origin=origins, require_user_verification=True, pem_root_certs_bytes_by_fmt=roots)

    bad = (WebAuthnException, ValueError, KeyError, TypeError)
    try:
        v = run(credential)
    except bad as exc:
        stripped = _strip_attestation(credential)
        if stripped is None:
            raise PasskeyError(f"registration did not verify: {exc}") from exc
        try:
            v = run(stripped)  # challenge, origin and UV still checked; only the model proof is dropped
        except bad as exc2:
            raise PasskeyError(f"registration did not verify: {exc2}") from exc2
    fmt = str(getattr(v.fmt, "value", v.fmt))
    x5c = [] if fmt == "none" else list(parse_attestation_object(v.attestation_object).att_stmt.x5c or [])
    chain_ok = False
    roots = list(roots_for(v.aaguid)) if (roots_for and x5c) else []
    if roots and _leaf_aaguid_matches(x5c[0], v.aaguid):
        try:
            run(credential, {v.fmt: roots})
            chain_ok = True
        except bad:
            chain_ok = False
    transports = credential.get("response", {}).get("transports") or []
    return {"id": b64url(v.credential_id), "public_key": v.credential_public_key, "sign_count": v.sign_count,
            "transports": [t for t in transports if isinstance(t, str)][:8], "aaguid": v.aaguid, "fmt": fmt,
            "has_chain": bool(x5c), "chain_ok": chain_ok,
            "chain_sha256": ("sha256:" + hashlib.sha256(b"".join(x5c)).hexdigest()) if x5c else None,
            "backup_eligible": str(getattr(v.credential_device_type, "value", "")) == "multi_device",
            "backed_up": bool(v.credential_backed_up)}


def verify_assertion(*, credential: dict, challenge: bytes, rp_id: str, origins: list[str],
                     public_key: bytes, sign_count: int) -> int:
    """Returns the new sign count."""
    import webauthn
    from webauthn.helpers.exceptions import InvalidAuthenticationResponse

    try:
        v = webauthn.verify_authentication_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=rp_id, expected_origin=origins,
            credential_public_key=public_key, credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError) as exc:
        raise PasskeyError(f"assertion did not verify: {exc}") from exc
    return v.new_sign_count
