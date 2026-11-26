# SPDX-License-Identifier: Apache-2.0
"""Verification levels (D-028; gateway permissions design 3.11): how strongly a person was checked.

- L0 "Signed in": a live session.
- L1 "Device check": a passkey with user verification (face, fingerprint or device PIN; WebAuthn never
  says which). Synced passkeys (iCloud Keychain, Google Password Manager) stop here.
- L2 "Proven key": L1, plus an attestation checked at enrolment against the allow-list, a model whose
  metadata lists a biometric method, and a device-bound key (backup-eligible flag BE=0).
- L3 "Biometric-only key": L2, plus proof the hardware unlocks the key only with a biometric. Nothing
  enrols at L3 yet (the Android approver key in design PR 18b, OneMind devices later).

OneMind never receives or stores biometric data: only the public key, the AAGUID (a model number), the
attestation format, a digest of the certificate chain, the BE/BS flags and the level.

Pure functions and tables here; state lives in verification.py and service.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LEVELS = ("L0", "L1", "L2", "L3")
LevelName = str

# FIDO Registry of Predefined Values, "User Verification Methods": the internal biometric methods.
# A model whose metadata lists one of these is "biometric-capable"; that proves the model, never
# that a biometric was used for one sign-in (many such keys also accept a PIN).
BIOMETRIC_UV = frozenset({"fingerprint_internal", "voiceprint_internal", "faceprint_internal",
                          "eyeprint_internal", "handprint_internal"})
ALLOWLIST_KINDS = ("fido_aaguid", "android_key_attestation", "onemind_device_root")
SHIPPED_ALLOWLIST = Path(__file__).resolve().parent / "authenticator-allowlist.json"


def rank(level: str) -> int:
    return LEVELS.index(level)


def name(n: int) -> str:
    return LEVELS[n]


@dataclass(frozen=True)
class Row:
    """One line of the owner-editable verification table."""

    label: str
    default: str
    minimum: str  # the floor: no edit goes below it
    maximum: str = "L3"
    strict: bool = False  # never eased while the household has no proven key (physical actions)


# Design 3.11, "Which actions need which level" (B-1, B-2, B-3; N-3 as recommended).
ROWS: dict[str, Row] = {
    "data.access": Row("Data access: sign in, read, download and export your own files, restore into a new "
                       "folder, run a backup", "L0", "L0", maximum="L1"),
    "tier.T0": Row("Approve a read-only action", "L1", "L1"),
    "tier.T1": Row("Approve a reversible change", "L1", "L1"),
    "tier.T2": Row("Approve a sensitive change (install an app, add a backup destination)", "L1", "L1"),
    "tier.T3": Row("Approve a destructive action (restore over live data, remove a node, roll back)", "L2", "L1"),
    "tier.T4": Row("Approve a restart or reboot", "L1", "L1"),
    "tier.P": Row("Approve a physical action (it moves or switches something)", "L2", "L2", strict=True),
    "physical.lockout_off": Row("Turn the motion lockout off", "L2", "L2", strict=True),
    "admin.high_risk": Row("Add a sign-in key, an approver or a contact; change a person's role; declare what "
                           "an agent reads; export recovery or backup keys", "L2", "L1"),
    "security.settings": Row("Security settings: sharing, certificates, update channel, trusted key models, "
                             "permission rules", "L2", "L2"),
    "verification.table": Row("Change this table", "L2", "L2"),
}

RISK_TIER = {"read": "tier.T0", "write": "tier.T1", "sensitive": "tier.T2", "destructive": "tier.T3",
             "actuate": "tier.T4"}

# Action types that are themselves a security-related setting or a high-risk administration step:
# approving one needs at least that row's level as well as its risk tier's.
TYPE_ROWS = {
    "verification.requirement.set": "verification.table",
    "authenticator.allowlist.add": "security.settings",
    "tls.acme.set": "security.settings",
    "os.update.settings": "security.settings",
    "backup.kit.issue": "admin.high_risk",
}

# Owner routes that add power, by operation id: the row their step-up meets (body-bound for L2+).
STEP_UP_ROWS = {
    "auth.passkeys.register": "admin.high_risk",
    "auth.approver_keys.register": "admin.high_risk",
    "users.create": "admin.high_risk",
    "users.update": "admin.high_risk",
    "agents.inputs.set": "admin.high_risk",
    "apps.access.set": "security.settings",
    "approvals.policies.create": "security.settings",
    "approvals.policies.confirm": "security.settings",
    "physical.lockout.set": "physical.lockout_off",
}

# Owner and member routes that only need a fresh passkey (L1), never more: taking power away (design
# 3.11, revoke is L0 plus the session's own proof). A step-up made in place stands in for signing in again.
FRESH_OPS = frozenset({"auth.passkeys.delete"})

TYPE_KEY_PREFIX = "type:"


def valid_key(key: str) -> bool:
    if key in ROWS:
        return True
    from ..automation import registry  # late: the registry imports the action ledger

    return key.startswith(TYPE_KEY_PREFIX) and registry.known(key[len(TYPE_KEY_PREFIX):])


def bounds(key: str) -> tuple[str, str, str]:
    """(default, minimum, maximum) for a row or a per-type override. A per-type row only raises: its
    floor is the level its tier already asks for, so lowering is done on the tier row."""
    if key in ROWS:
        r = ROWS[key]
        return r.default, r.minimum, r.maximum
    return "L1", "L1", "L3"


def check_edit(key: str, level: str) -> tuple[str, str] | None:
    """(reason, message) when this edit is refused (422), or None."""
    if not valid_key(key):
        return "unknown_row", f"unknown row {key!r}: use a row id from GET /v1/verification-requirements or type:<action type>"
    if level not in LEVELS:
        return "invalid_level", "level must be L0, L1, L2 or L3"
    _, low, high = bounds(key)
    if rank(level) < rank(low):
        return "below_floor", f"{key} can't go below {low}"
    if rank(level) > rank(high):
        return "above_ceiling", f"{key} can't go above {high}: your data never depends on a strong key"
    return None


# ---- the authenticator allow-list ------------------------------------------------------------------
@dataclass(frozen=True)
class Model:
    aaguid: str
    name: str
    roots: tuple[bytes, ...]  # PEM attestation roots
    user_verification: tuple[str, ...]
    source: str  # shipped | owner

    @property
    def biometric(self) -> bool:
        return bool(BIOMETRIC_UV & set(self.user_verification))

    def json(self) -> dict:
        return {"aaguid": self.aaguid, "name": self.name, "user_verification": list(self.user_verification),
                "biometric": self.biometric, "roots": len(self.roots), "source": self.source}


def clean_aaguid(raw: str) -> str | None:
    s = raw.strip().lower()
    hexpart = s.replace("-", "")
    if len(hexpart) != 32 or any(c not in "0123456789abcdef" for c in hexpart) or hexpart == "0" * 32:
        return None
    return f"{hexpart[:8]}-{hexpart[8:12]}-{hexpart[12:16]}-{hexpart[16:20]}-{hexpart[20:]}"


def check_root(pem: str) -> str | None:
    """Why this PEM is not a usable attestation root, or None."""
    from cryptography import x509

    try:
        cert = x509.load_pem_x509_certificate(pem.encode())
    except ValueError:
        return "a root must be one PEM certificate"
    try:
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    except x509.ExtensionNotFound:
        return "a root must be a CA certificate (basicConstraints CA:TRUE)"
    return None if bc.ca else "a root must be a CA certificate (basicConstraints CA:TRUE)"


def load_file(path: Path) -> list[Model]:
    """The shipped list (signed OS image, updated with RAUC). A missing or broken file means no
    shipped models: keys still enrol, at L1, and the log says why."""
    import logging

    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logging.getLogger(__name__).exception("authenticator allow-list %s is unreadable; using none", path)
        return []
    out = []
    for e in doc.get("entries") or []:
        if not isinstance(e, dict) or e.get("kind") != "fido_aaguid":
            continue  # android_key_attestation and onemind_device_root are read by later PRs (L3)
        aaguid = clean_aaguid(str(e.get("aaguid") or ""))
        roots = [r for r in e.get("roots") or [] if isinstance(r, str) and check_root(r) is None]
        if aaguid is None or not roots:
            continue
        out.append(Model(aaguid, str(e.get("name") or aaguid)[:100], tuple(r.encode() for r in roots),
                         tuple(str(u) for u in e.get("user_verification") or [])[:16], "shipped"))
    return out


# ---- the level a new credential earns --------------------------------------------------------------
def credential_level(*, fmt: str, has_chain: bool, backup_eligible: bool, model: Model | None,
                     chain_ok: bool) -> tuple[str, str]:
    """(level, reason) for a credential at enrolment. The reason is shown on the Sign-in keys screen."""
    if fmt == "none" or not has_chain:
        return "L1", "no_attestation"
    if backup_eligible:
        return "L1", "synced"
    if model is None:
        return "L1", "model_not_trusted"
    if not chain_ok:
        return "L1", "chain_untrusted"
    if not model.biometric:
        return "L1", "not_biometric_capable"
    return "L2", "proven"


REASON_TEXT = {
    "no_attestation": "This passkey can't prove its make and model. It works for everyday approvals; add a "
                      "security key or the OneMind app key for actions that need a proven key.",
    "synced": "This passkey is synced between devices (iCloud Keychain, Google Password Manager or a "
              "password manager), so it stays at Device check.",
    "model_not_trusted": "This key's model isn't on the trusted list. An owner can add it under Trusted key "
                         "models; until then it works at Device check.",
    "chain_untrusted": "This key's certificate doesn't lead to the trusted root for its model, so it stays "
                       "at Device check.",
    "not_biometric_capable": "This key's model lists no fingerprint or face check, so it stays at Device check.",
    "proven": "A proven key: its model is trusted, it can check a fingerprint or face, and it never leaves "
              "this device.",
    "legacy": "Added before verification levels existed; it works at Device check.",
}
