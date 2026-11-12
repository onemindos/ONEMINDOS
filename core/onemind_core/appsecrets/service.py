# SPDX-License-Identifier: Apache-2.0
"""App secret store: owner-entered and generated values, bound to the approval that applies them.

Two ways a value reaches the store, both through an owner's approval (docs/leap/core/SECRETS.md):

1. **Install.** The approval of `app.install` carries the form, sealed in the browser
   (`POST /v1/actions/{id}/approve` body `{"sealed": ...}`). The gateway opens it, checks it
   against `spec.secrets`, refuses the approval (409, the action stays awaiting) while a required
   key is missing, and generates every `generate: true` key that has no value yet.
2. **Change or rotate.** `POST /v1/apps/{id}/secrets` (owner) files an `app.configure` action
   whose params list each change with a keyed fingerprint, never the value; the values wait
   encrypted in `secrets_staged` until that action is approved, and are purged if it is denied
   or expires.

After acceptance the values are committed (AES-256-GCM, a new version per key) and handed to the
executor, which applies them as Kubernetes Secrets by server-side apply. Values are never
returned by any route, never written to the audit log, events, action params or logs, and never
reachable by agent principals (owner-only writes; reads return names and set flags only).
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets as pysecrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag

from ..audit import AuditLog
from ..auth import Principal
from ..catalog import AppEntry, Catalog
from ..errors import ApiError
from ..events import EventHub
from ..executors import AppSecret
from ..ledger import Action, ActionRepository, utc
from ..sections import config_section
from .crypto import SealedInputError, StoreKey, sealed_context
from .spec import KeyDecl
from .store import NewValue, SecretsRepository, StagedValue, StoredValue

log = logging.getLogger("onemind.secrets")

CREDENTIAL_NAME = "onemind-secrets-key"  # systemd LoadCredential(Encrypted)= name
MIN_VALUE, MAX_VALUE = 4, 8192
GENERATED_BYTES = 32
LIVE_STATES = frozenset({"requested", "awaiting_approval", "accepted", "dispatched"})
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE = re.compile(r"\s")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*$")
DEFAULT_TTL = timedelta(hours=24)
MAX_TTL = timedelta(days=7)


@config_section("secrets")
@dataclass(frozen=True)
class SecretsSettings:
    # The secret-store key. None: $ONEMIND_DATA_DIR/custodian/secrets.key, or next to the audit
    # log when Settings was built in code. A systemd credential named onemind-secrets-key wins
    # when present ($CREDENTIALS_DIRECTORY), so the image can seal the key to the TPM.
    key_file: Path | None = None
    create_key: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "SecretsSettings":
        explicit = (env.get("ONEMIND_SECRETS_KEY_FILE") or "").strip()
        if explicit:
            return cls(key_file=Path(explicit))
        creds = (env.get("CREDENTIALS_DIRECTORY") or "").strip()
        if creds and (Path(creds) / CREDENTIAL_NAME).is_file():
            return cls(key_file=Path(creds) / CREDENTIAL_NAME, create_key=False)
        data_dir = (env.get("ONEMIND_DATA_DIR") or "").strip()
        return cls(key_file=Path(data_dir) / "custodian" / "secrets.key" if data_dir else None)


Ref = tuple[str, str]  # (secret name, key)


def ref_text(ref: Ref) -> str:
    return f"{ref[0]}/{ref[1]}"


def parse_ref(text: str) -> Ref | None:
    name, sep, key = text.partition("/")
    return (name, key) if sep and name and key else None


@dataclass(frozen=True)
class Prepared:
    """What an approval will commit. Holds plaintext only in memory, never in repr."""

    app_id: str
    sets: dict[Ref, str] = field(default_factory=dict, repr=False)
    generate: frozenset[Ref] = frozenset()
    clear: frozenset[Ref] = frozenset()


def _aad(app_id: str, ref: Ref, version: int) -> bytes:
    return "\x00".join(("onemind/app-secret/v1", app_id, ref[0], ref[1], str(version))).encode()


def _staged_aad(action_id: str, app_id: str, ref: Ref) -> bytes:
    return "\x00".join(("onemind/app-secret-staged/v1", action_id, app_id, ref[0], ref[1])).encode()


def value_problem(decl: KeyDecl, value: object) -> str | None:
    """Why value cannot be stored for decl, or None. Never quotes the value."""
    if not isinstance(value, str):
        return "must be text"
    if not MIN_VALUE <= len(value) <= MAX_VALUE:
        return f"must be {MIN_VALUE} to {MAX_VALUE} characters"
    if CONTROL.search(value):
        return "must not contain control characters or line breaks"
    if decl.kind in ("api-key", "token", "url") and WHITESPACE.search(value):
        return "must not contain spaces"
    if decl.kind == "url":
        parts = urlsplit(value)
        if not SCHEME.match(parts.scheme or "") or not parts.netloc:
            return "must be a URL with a scheme and a host, such as https://host:port/path"
    return None


class AppSecretsService:
    def __init__(
        self,
        repo: SecretsRepository,
        key: StoreKey,
        catalog: Catalog,
        actions_repo: ActionRepository,
        audit: AuditLog,
        events: EventHub,
        clock: Callable[[], datetime],
    ):
        self.repo = repo
        self.key = key
        self.catalog = catalog
        self.actions_repo = actions_repo
        self.audit = audit
        self.events = events
        self.clock = clock

    # ---- reads -------------------------------------------------------------------------------
    def public_key(self) -> dict:
        return self.key.public_key_json()

    def app(self, app_id: str) -> AppEntry:
        app = self.catalog.get(app_id)
        if app is None:
            raise ApiError(404, "not_found", f"app {app_id!r} is not in the catalog")
        return app

    def describe(self, app: AppEntry) -> dict:
        """Declarations plus which keys are set. Never a value; the same answer for every principal."""
        current = self.repo.current(app.id)
        out = []
        for decl in app.secrets:
            keys = []
            for k in decl.keys:
                v = current.get((decl.name, k.key))
                keys.append({
                    "key": k.key, "kind": k.kind, "description": k.description, "required": k.required,
                    "source": k.source, "set": v is not None,
                    "version": v.version if v else None,
                    "updated_at": utc(v.updated_at).isoformat().replace("+00:00", "Z") if v else None,
                })
            out.append({"name": decl.name, "description": decl.description, "keys": keys})
        missing = [ref_text(r) for r in self._missing_required(app, set(current))]
        return {"app_id": app.id, "secrets": out, "missing_required": missing, "key_id": self.key.key_id}

    # ---- form input --------------------------------------------------------------------------
    def _decl(self, app: AppEntry, ref: Ref) -> KeyDecl | None:
        secret = next((s for s in app.secrets if s.name == ref[0]), None)
        return secret.key(ref[1]) if secret else None

    def open_form(self, app: AppEntry, sealed: object) -> dict[Ref, str]:
        """Open a sealed form and check every value against the app's declaration (422 otherwise)."""
        if not app.secrets:
            raise ApiError(422, "conflict", f"app {app.id!r} declares no secrets")
        try:
            doc = json.loads(self.key.open_sealed(sealed, sealed_context(app.id)))
        except SealedInputError as exc:
            raise ApiError(422, "conflict", f"sealed: {exc}") from None
        except ValueError:
            raise ApiError(422, "conflict", "sealed: the opened form is not JSON") from None
        values = doc.get("values") if isinstance(doc, dict) else None
        if not isinstance(values, dict):
            raise ApiError(422, "conflict", "sealed: the form must be {\"values\": {<secret>: {<key>: <value>}}}")
        out: dict[Ref, str] = {}
        problems: list[str] = []
        for name, keys in values.items():
            if not isinstance(keys, dict):
                problems.append(f"{name}: must map keys to values")
                continue
            for key, value in keys.items():
                ref = (str(name), str(key))
                decl = self._decl(app, ref)
                if decl is None:
                    problems.append(f"{ref_text(ref)}: not declared by the app")
                elif decl.generate:
                    problems.append(f"{ref_text(ref)}: generated by the box; it cannot be entered")
                elif (why := value_problem(decl, value)) is not None:
                    problems.append(f"{ref_text(ref)}: {why}")
                else:
                    out[ref] = value
        if problems:
            raise ApiError(422, "conflict", "secrets: " + "; ".join(problems)[:900])
        return out

    def _missing_required(self, app: AppEntry, have: set[Ref]) -> list[Ref]:
        return [(s.name, k.key) for s in app.secrets for k in s.keys if k.required and (s.name, k.key) not in have]

    def _check_current_opens(
        self, app: AppEntry, current: dict[Ref, StoredValue], replaced: set[Ref], can_rotate: bool
    ) -> None:
        """Refuse when a stored value that this approval keeps cannot be opened.

        Values the approval replaces (entered, rotated or cleared) are not checked, so entering a
        value again is how the owner recovers after a restore without the key file. Rows the
        manifest no longer declares are never applied, so they are not checked either.
        """
        for ref, v in current.items():
            decl = self._decl(app, ref)
            if ref in replaced or decl is None:
                continue
            try:
                self.key.decrypt(v.nonce, v.ciphertext, _aad(app.id, ref, v.version))
            except InvalidTag:
                if not decl.generate:
                    fix = "enter it again"
                elif can_rotate:
                    fix = "rotate it in the same change"
                else:
                    fix = "restore the key file (a generated value cannot be entered)"
                raise ApiError(
                    409, "stale_precondition",
                    f"stored secret {ref_text(ref)} does not open with this box's key "
                    f"(was the database restored without its key file?); {fix}",
                ) from None

    # ---- change requests (app.configure) -----------------------------------------------------
    def request_change(
        self, actions, principal: Principal, app_id: str, *, sealed: object | None, generate: list[str],
        clear: list[str], reason: str | None, idempotency_key: str | None, expires_at: datetime | None,
    ) -> tuple[dict, bool]:
        """File an app.configure action with the owner's changes staged until it is approved."""
        if not principal.is_owner:
            self.audit.append("authz.denied", principal.as_dict(), None,
                              {"attempted": "change app secrets", "app_id": app_id, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not change app secrets")
        app = self.app(app_id)
        if not app.secrets:
            raise ApiError(409, "stale_precondition", f"app {app_id!r} declares no secrets")
        sets = self.open_form(app, sealed) if sealed is not None else {}
        gen = self._refs(app, generate, "generate", lambda d: d.generate, "only generated keys can be rotated")
        clr = self._refs(app, clear, "clear", lambda d: not d.generate and not d.required,
                         "only optional owner-entered keys can be cleared")
        overlap = (set(sets) & clr) | (set(sets) & gen) | (gen & clr)
        if overlap:
            raise ApiError(422, "conflict", "a key appears in more than one change: "
                           + ", ".join(sorted(ref_text(r) for r in overlap)))
        changes = (
            [{"secret": r[0], "key": r[1], "op": "set", "fingerprint": self._fp(app.id, r, v)} for r, v in sets.items()]
            + [{"secret": r[0], "key": r[1], "op": "generate"} for r in gen]
            + [{"secret": r[0], "key": r[1], "op": "clear"} for r in clr]
        )
        changes.sort(key=lambda c: (c["secret"], c["key"]))
        now = self.clock()
        expires = utc(expires_at) if expires_at else now + DEFAULT_TTL
        if expires > now + MAX_TTL:
            raise ApiError(422, "conflict", "expires_at may be at most 7 days ahead")
        self.purge()
        body, created = actions.request(
            principal, "app.configure", {"app_id": app.id, "secrets": changes},
            idempotency_key or f"secrets-{uuid.uuid4()}", expires, reason,
        )
        if created:
            staged = [self._stage_value(body["id"], app.id, r, "set", v) for r, v in sets.items()]
            staged += [StagedValue(r[0], r[1], "generate", None, None, None, None) for r in gen]
            staged += [StagedValue(r[0], r[1], "clear", None, None, None, None) for r in clr]
            self.repo.stage(body["id"], app.id, staged, principal.id, now)
        return body, created

    def _refs(self, app: AppEntry, texts: list[str], op: str, ok, why: str) -> frozenset[Ref]:
        refs = set()
        for text in texts:
            ref = parse_ref(text)
            decl = self._decl(app, ref) if ref else None
            if decl is None:
                raise ApiError(422, "conflict", f"{op}: {text!r} is not a declared <secret>/<key>")
            if not ok(decl):
                raise ApiError(422, "conflict", f"{op}: {text}: {why}")
            refs.add(ref)
        return frozenset(refs)

    def _fp(self, app_id: str, ref: Ref, value: str) -> str:
        return self.key.fingerprint(app_id, ref[0], ref[1], value)

    def _stage_value(self, action_id: str, app_id: str, ref: Ref, op: str, value: str) -> StagedValue:
        nonce, ct = self.key.encrypt(value.encode("utf-8"), _staged_aad(action_id, app_id, ref))
        return StagedValue(ref[0], ref[1], op, ct, nonce, self.key.key_id, self._fp(app_id, ref, value))

    def purge(self) -> int:
        """Drop staged values whose action was denied, expired, failed or is gone."""
        stale = set()
        for action_id in self.repo.staged_action_ids():
            a = self.actions_repo.get(action_id)
            if a is None or a.state not in LIVE_STATES or (
                a.state in ("requested", "awaiting_approval") and self.clock() >= utc(a.expires_at)
            ):
                stale.add(action_id)
        n = self.repo.drop_staged(stale)
        if n:
            log.info("purged %d staged secret values of %d undecided-and-closed actions", n, len(stale))
        return n

    # ---- ActionService bridge ----------------------------------------------------------------
    def prepare(self, a: Action, app: AppEntry, sealed: object | None) -> Prepared | None:
        """Before an approval is accepted: everything that can refuse it. Raises ApiError (the
        action stays awaiting_approval); returns None when the action touches no secrets."""
        if a.type == "app.install":
            if not app.secrets:
                if sealed is not None:
                    raise ApiError(422, "conflict", f"app {app.id!r} declares no secrets")
                return None
            sets = self.open_form(app, sealed) if sealed is not None else {}
            current = self.repo.current(app.id)
            self._check_current_opens(app, current, set(sets), can_rotate=False)
            missing = self._missing_required(app, set(current) | set(sets))
            if missing:
                raise ApiError(409, "stale_precondition", "enter the required secrets before approving: "
                               + ", ".join(ref_text(r) for r in missing))
            gen = frozenset((s.name, k.key) for s in app.secrets for k in s.keys
                            if k.generate and (s.name, k.key) not in current)
            return Prepared(app.id, sets, gen)
        if sealed is not None:
            raise ApiError(422, "conflict", "secrets are entered with the install approval or POST /v1/apps/{id}/secrets")
        if a.type != "app.configure":
            return None
        return self._prepare_configure(a, app)

    def _prepare_configure(self, a: Action, app: AppEntry) -> Prepared:
        staged = {(v.name, v.key): v for v in self.repo.staged(a.id)}
        wanted = {(c["secret"], c["key"]): c["op"] for c in a.params.get("secrets") or []}
        if {r: v.op for r, v in staged.items()} != wanted:
            raise ApiError(409, "stale_precondition",
                           "the entered values are no longer on the box; submit the secrets form again")
        sets: dict[Ref, str] = {}
        for ref, v in staged.items():
            decl = self._decl(app, ref)
            if decl is None or (v.op == "generate") != decl.generate or (v.op == "clear" and decl.required):
                raise ApiError(409, "stale_precondition", f"the app's declaration of {ref_text(ref)} changed; "
                               "submit the secrets form again")
            if v.op == "set":
                try:
                    sets[ref] = self.key.decrypt(v.nonce, v.ciphertext, _staged_aad(a.id, app.id, ref)).decode("utf-8")
                except InvalidTag:
                    raise ApiError(409, "stale_precondition", "the entered values do not open with this box's key; "
                                   "submit the secrets form again") from None
        current = self.repo.current(app.id)
        clear = frozenset(r for r, v in staged.items() if v.op == "clear")
        gen = frozenset(r for r, v in staged.items() if v.op == "generate")
        self._check_current_opens(app, current, set(sets) | gen | clear, can_rotate=True)
        missing = self._missing_required(app, (set(current) - clear) | set(sets))
        if missing:
            raise ApiError(409, "stale_precondition", "required secrets would be unset: "
                           + ", ".join(ref_text(r) for r in missing))
        return Prepared(app.id, sets, gen, clear)

    def commit(self, a: Action, app: AppEntry, prep: Prepared, approver: Principal) -> list[AppSecret]:
        """After acceptance: write the new values (one transaction) and return what to apply."""
        now = self.clock()
        current = self.repo.current(app.id)
        writes: list[NewValue] = []
        changes: list[dict] = []
        decided = [(r, v, "set", "owner") for r, v in prep.sets.items()]
        decided += [(r, pysecrets.token_urlsafe(GENERATED_BYTES), "generate", "generated") for r in prep.generate]
        for ref, value, op, source in sorted(decided, key=lambda x: x[0]):
            version = current[ref].version + 1 if ref in current else 1
            nonce, ct = self.key.encrypt(value.encode("utf-8"), _aad(app.id, ref, version))
            fp = self._fp(app.id, ref, value)
            writes.append(NewValue(ref[0], ref[1], ct, nonce, self.key.key_id, version, source, fp))
            changes.append({"secret": ref[0], "key": ref[1], "op": op, "version": version, "fingerprint": fp})
        clears = sorted(r for r in prep.clear if r in current)
        changes += [{"secret": r[0], "key": r[1], "op": "clear"} for r in clears]
        self.repo.commit(app.id, writes, clears, a.id, approver.id, now)
        if changes:
            self.events.publish_event(
                "app", "secrets.changed", {"app_id": app.id, "changes": changes},
                principal=approver.as_dict(), action_id=a.id, resource={"kind": "app", "id": app.id},
            )
        return self.materialize(app)

    def materialize(self, app: AppEntry) -> list[AppSecret]:
        """One AppSecret per declared Secret, holding every key that has a value."""
        current = self.repo.current(app.id)
        out = []
        for decl in app.secrets:
            data = {}
            for k in decl.keys:
                v = current.get((decl.name, k.key))
                if v is not None:
                    data[k.key] = self.key.decrypt(v.nonce, v.ciphertext, _aad(app.id, (decl.name, k.key), v.version)).decode("utf-8")
            out.append(AppSecret(decl.name, data))
        return out


def load_store_key(cfg: SecretsSettings, audit_path: Path) -> StoreKey:
    path = cfg.key_file or audit_path.parent / "custodian" / "secrets.key"
    existed = path.exists()
    key = StoreKey.load(path, create=cfg.create_key)
    if not existed:
        log.warning("created the app secret-store key %s (%s); back it up with the box (BACKUPS.md §6.4)",
                    os.path.basename(str(path)), key.key_id)
    return key
