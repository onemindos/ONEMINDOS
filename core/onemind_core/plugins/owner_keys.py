# SPDX-License-Identifier: Apache-2.0
"""Owner enrollment is distinct from a valid signature by an arbitrary key."""
import base64
from datetime import timedelta
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..actions import ActionRequest, FeatureAction
from ..errors import ApiError
from ..executors import ExecResult
from ..identity.models import IdentityRepository, utc
from .key_models import KeyCandidateRow, SigningKeyRow


class EnrollmentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    key_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    name: str = Field(min_length=1, max_length=80)


class RevocationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


def parse_public_key(pem: str):
    try:
        if len(pem.encode()) > 16384:
            raise ValueError()
        lines = pem.strip().splitlines()
        if lines[0] != "-----BEGIN PUBLIC KEY-----" or lines[-1] != "-----END PUBLIC KEY-----":
            raise ValueError()
        der = base64.b64decode("".join(lines[1:-1]), validate=True)
        key = serialization.load_der_public_key(der)
        if isinstance(key, rsa.RSAPublicKey):
            if key.key_size < 2048 or key.public_numbers().e.bit_length() > 31:
                raise ValueError()
        elif isinstance(key, ec.EllipticCurvePublicKey):
            if not isinstance(key.curve, (ec.SECP256R1, ec.SECP384R1, ec.SECP521R1)):
                raise ValueError()
        elif not isinstance(key, ed25519.Ed25519PublicKey):
            raise ValueError()
        der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        canonical = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        return "sha256:" + hashlib.sha256(der).hexdigest(), canonical
    except Exception as exc:
        raise ApiError(422, "conflict", "provide one supported public SPKI PEM key; private keys are not accepted") from exc


MAX_PROPOSAL_AGE = timedelta(hours=24)


class OwnerKeys:
    def __init__(self, gw, identity):
        self.gw, self.repo, self.identity = gw, IdentityRepository(gw.db), identity
        gw.actions.register_type("plugin.key.enroll", FeatureAction(
            "sensitive", self.enroll, params_model=EnrollmentParams,
            check_request=self.check_enrollment, check=self.check_enrollment_action, risk_for=lambda _: "sensitive",
        ))
        gw.actions.register_type("plugin.key.revoke", FeatureAction(
            "sensitive", self.revoke, params_model=RevocationParams,
            check_request=self.check_revocation, check=self.check_revocation_action, risk_for=lambda _: "sensitive",
        ))

    def owner(self, principal):
        if not principal.is_owner:
            raise self.identity.deny(principal, "manage plugin signing trust")

    def keys(self, principal):
        self.owner(principal)
        return self.repo.all(select(SigningKeyRow).order_by(SigningKeyRow.enrolled_at, SigningKeyRow.id))

    def request_enrollment(self, principal, body):
        self.owner(principal)
        # Parse before filing/auditing an action, so an accidentally pasted private
        # key never enters candidate storage, the action ledger or its audit data.
        key_id, canonical = parse_public_key(body.public_key)
        if not body.name.strip():
            raise ApiError(422, "conflict", "signing key name must not be blank")
        if utc(body.expires_at) > self.gw.clock() + MAX_PROPOSAL_AGE:
            raise ApiError(422, "conflict", "a signing-key proposal may stay open for at most 24 hours")
        candidate_id = hashlib.sha256((principal.id + "\0" + body.idempotency_key).encode()).hexdigest()
        values = dict(id=candidate_id, key_id=key_id, name=body.name.strip(), public_key=canonical,
                      created_by=principal.id, expires_at=body.expires_at)
        with self.gw.db.session.begin() as session:
            session.execute(self.gw.db.insert()(KeyCandidateRow).values(**values)
                            .on_conflict_do_nothing(index_elements=[KeyCandidateRow.id]))
        candidate = self.repo.get(KeyCandidateRow, candidate_id)
        if candidate.public_key != canonical or candidate.name != body.name.strip():
            raise ApiError(409, "conflict", "idempotency key was already used for another signing key")
        return self.gw.actions.create(principal, ActionRequest(type="plugin.key.enroll",
            params={"candidate_id": candidate_id, "key_id": key_id, "name": candidate.name}, idempotency_key=body.idempotency_key, expires_at=body.expires_at))[0]

    def candidate(self, params):
        candidate = self.repo.get(KeyCandidateRow, params["candidate_id"])
        if candidate is None or utc(candidate.expires_at) <= self.gw.clock():
            raise ApiError(409, "stale_precondition", "signing-key proposal is missing or expired")
        if candidate.key_id != params["key_id"] or candidate.name != params["name"]:
            raise ApiError(409, "stale_precondition", "signing-key proposal changed")
        return candidate

    def check_enrollment(self, params, principal):
        self.owner(principal)
        if self.candidate(params).created_by != principal.id:
            raise ApiError(403, "permission_denied", "signing-key proposal belongs to another owner")

    def check_enrollment_action(self, action):
        try:
            self.candidate(action.params)
            self.not_revoked_since(action)
        except ApiError as exc:
            return exc.message
        return None

    def not_revoked_since(self, action):
        """A revocation is final for every proposal filed before it.

        Otherwise a stale proposal for the same key, approved after the owner revoked it as
        compromised, would re-activate the key.
        """
        row = self.repo.get(SigningKeyRow, action.params["key_id"])
        if row is not None and row.revoked_at is not None and utc(action.created_at) <= utc(row.revoked_at):
            raise ApiError(409, "stale_precondition",
                           "this signing key was revoked after the proposal was filed; propose it again")

    def check_revocation(self, params, principal):
        self.owner(principal)
        row = self.repo.get(SigningKeyRow, params["key_id"])
        if row is None or not row.active:
            raise ApiError(404, "not_found", "no active signing key")

    def check_revocation_action(self, action):
        row = self.repo.get(SigningKeyRow, action.params["key_id"])
        return None if row and row.active else "signing key is no longer active"

    def enroll(self, action, finish):
        candidate = self.candidate(action.params)
        try:
            self.not_revoked_since(action)
        except ApiError as exc:
            finish(ExecResult("failed", exc.message))
            return
        key_id, canonical = parse_public_key(candidate.public_key)
        if key_id != action.params["key_id"]:
            raise ApiError(409, "stale_precondition", "signing-key material changed")
        values = dict(id=key_id, name=candidate.name, public_key=canonical, active=True,
                      enrolled_at=self.gw.clock(), revoked_at=None, action_id=action.id)
        with self.gw.db.session.begin() as session:
            changed = session.execute(self.gw.db.insert()(SigningKeyRow).values(**values)
                .on_conflict_do_update(index_elements=[SigningKeyRow.id], set_=values,
                                      where=SigningKeyRow.active.is_(False)).returning(SigningKeyRow.id)).first()
        finish(ExecResult("succeeded" if changed else "failed",
                          "plugin signing trust enrolled" if changed else "signing key is already active"))

    def revoke(self, action, finish):
        changed = self.repo.update(SigningKeyRow, [SigningKeyRow.id == action.params["key_id"],
                                                  SigningKeyRow.active.is_(True)],
                                  {"active": False, "revoked_at": self.gw.clock(), "action_id": action.id})
        finish(ExecResult("succeeded" if changed else "failed",
                          "plugin signing trust revoked" if changed else "signing key is no longer active"))
