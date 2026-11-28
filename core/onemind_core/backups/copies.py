# SPDX-License-Identifier: Apache-2.0
"""Approval and first-run discovery for independent box copies."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from datetime import datetime, timedelta

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .. import __version__
from ..actions import FeatureAction
from ..boxbundle import box_config, sovereign as copy
from ..boxbundle.manifest import Source, canonical, sha256
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import utc
from .jobs import AgentError
from .service import BackupService, Unavailable

KIND = "backup.copy"


def snapshot_evidence(point: dict) -> tuple[list[dict], datetime]:
    snapshots = sorted(point["snapshots"], key=lambda s: s["id"])
    refs = [{k: s.get(k) or None for k in ("id", "unit", "app_id", "app_revision")} for s in snapshots]
    return refs, max(datetime.fromisoformat(s["taken_at"]) for s in snapshots)


class SovereignCopies:
    def __init__(self, backups: BackupService):
        self.backups = backups
        self.gw = backups.gw
        self._keys: dict[str, tuple[str, datetime]] = {}
        self._lock = threading.RLock()
        self.gw.actions.register_type("box.export", FeatureAction(
            "sensitive", self._execute, release=lambda action: self._take_key(action.id)))

    def _take_key(self, action_id: str):
        with self._lock:
            return self._keys.pop(action_id, None)

    def _target(self, destination_id: str) -> dict:
        self.backups._agent()
        for dest in self.backups.destinations():
            if dest["id"] == destination_id and dest["config"].get("sovereign") is True:
                return dest
        raise ApiError(404, "not_found", "no such sovereign backup destination")

    def _export_credentials(self, box: str) -> tuple[Ed25519PrivateKey, dict]:
        directory = self.backups.s.copy_keys_dir
        if directory is None:
            raise copy.CopyRefused("this box needs an owner-certified export key")
        keyfile = directory / "export.key"
        if keyfile.stat().st_mode & 0o077:
            raise copy.CopyRefused("the export key must be readable only by the gateway's user")
        key = load_pem_private_key(keyfile.read_bytes(), password=None)
        trust = copy.decode((directory / "trust.json").read_bytes())
        public = copy.export_key(trust, box, sha256(copy.unb64(trust["root"])))
        if not isinstance(key, Ed25519PrivateKey) or key.public_key().public_bytes_raw() != public.public_bytes_raw():
            raise copy.CopyRefused("the owner certificate does not match the export key")
        return key, trust

    def request(self, principal, destination_id: str, password: str, idempotency_key: str, reason: str | None):
        dest = self._target(destination_id)
        box = self.gw.settings.node_id
        if not box or self.backups.s.copy_keys_dir is None:
            raise ApiError(409, "stale_precondition", "provision the owner-certified export key on this box first")
        kit = self.backups.repo.kit()
        fingerprint = hashlib.sha256(password.encode()).hexdigest()[:16]
        if kit is None or kit.state != "confirmed" or not hmac.compare_digest(fingerprint, kit.fingerprint):
            raise ApiError(409, "stale_precondition", "the confirmed owner recovery key is required")
        # The latest complete box run on this destination is bound to the approval.
        for run in self.backups.repo.runs_for_destination(destination_id):
            snapshots = sorted(u["snapshot_id"] for u in run.units if u.get("snapshot_id"))
            if run.state == "succeeded" and any(u.get("unit") == "system" and u.get("snapshot_id") for u in run.units):
                break
        else:
            raise ApiError(409, "stale_precondition", "run a successful whole-box backup on this destination first")
        now = utc(self.gw.clock())
        expiry = now + timedelta(hours=1)
        with self._lock:
            self._keys = {id_: held for id_, held in self._keys.items() if held[1] > now}
            action, created = self.gw.actions.request_feature(
                principal, "box.export", {"destination_id": destination_id, "destination": dest["label"],
                                         "run_id": run.id, "snapshots": snapshots},
                idempotency_key=idempotency_key, expires_at=expiry, reason=reason)
            if created:
                self._keys[action["id"]] = (password, expiry)
        return action, created

    def _execute(self, action, finish):
        held = self._take_key(action.id)

        def work():
            if held is None or held[1] <= utc(self.gw.clock()):
                finish(ExecResult("failed", "the recovery key is no longer in memory; request the copy again"))
                return
            try:
                record = self._publish(action, held[0])
            except (AgentError, Unavailable, OSError, UnsupportedAlgorithm, *copy.INVALID_COPY):
                finish(ExecResult("failed", "the copy could not be published; check the export key, kit and destination"))
                return
            summary = {"copy_id": record.copy_id, "destination_id": action.params["destination_id"],
                       "sha256": record.sha256, "size": record.size, "layers": ["box_config", "app_data_refs"]}
            self.gw.audit.append("box.export.completed", action.requested_by, action.id, summary)
            finish(ExecResult("succeeded", "sovereign copy published", [summary]))

        self.backups.worker.submit(work)

    def _publish(self, action, password: str) -> copy.Completion:
        kit = self.backups.repo.kit()
        if kit is None or kit.state != "confirmed" or not hmac.compare_digest(
            hashlib.sha256(password.encode()).hexdigest()[:16], kit.fingerprint
        ):
            raise copy.CopyRefused("the recovery kit changed after approval")
        box = self.gw.settings.node_id
        key, trust = self._export_credentials(box)
        params = {"target_id": action.params["destination_id"], "box_id": box,
                  "run_id": action.params["run_id"], "snapshots": action.params["snapshots"]}
        point = self.backups._job(KIND, {**params, "operation": "prepare"}, action.id)
        units, backed_up = snapshot_evidence(point)
        refs = copy.References(
            repository=point["repository"], run_id=params["run_id"], snapshots=params["snapshots"],
            units=units)
        layer, excluded = box_config.layer(self.gw.db)
        now = utc(self.gw.clock())
        copy_id = secrets.token_hex(16)
        generation = point["generation"]
        source = Source(box, copy.decode(layer.data)["box"]["box_name"], __version__, generation=generation)
        recipient = copy.recipient(password)
        bundle = copy.seal(layer, refs, source, now, copy_id, key, recipient.public_key(), excluded)
        record = copy.Completion(format=1, box_id=box, copy_id=copy_id, generation=generation, created_at=now,
                                 backed_up_at=backed_up, size=len(bundle), sha256=sha256(bundle),
                                 repository=refs.repository, run_id=refs.run_id, snapshots=refs.snapshots)
        copy.open_bundle(bundle, record, key.public_key(), recipient)
        complete = canonical({"trust": trust, "completion": copy.signed(b"complete/", key, record.model_dump(mode="json"))})
        self.backups._job(KIND, {**params, "operation": "publish", "copy_id": copy_id, "generation": generation,
                                "repository": refs.repository, "bundle": copy.b64(bundle), "record": copy.b64(complete),
                                "recovery_key": password}, action.id)
        return record

    def discover(self, destination_id: str, box_id: str, root: str, password: str) -> tuple[copy.Completion | None, int]:
        self._target(destination_id)
        if self.backups.installed_apps():
            raise ApiError(409, "stale_precondition", "sovereign copy discovery is for a fresh box")
        try:
            recipient = copy.recipient(password)
        except UnsupportedAlgorithm:
            raise Unavailable("this box cannot open hybrid recovery bundles", "copy_crypto_unavailable") from None
        except copy.INVALID_COPY:
            raise ApiError(422, "conflict", "the printed recovery key is malformed") from None
        params = {"target_id": destination_id, "box_id": box_id}
        ids = self.backups._job(KIND, {**params, "operation": "list"}) or []
        records = []
        refused = 0
        for cid in ids:
            try:
                raw = copy.unb64(self.backups._job(KIND, {**params, "operation": "record", "copy_id": cid}))
                records.append(copy.open_record(raw, box_id, cid, root))
            except (AgentError, *copy.INVALID_COPY):
                refused += 1
        key = lambda pair: (pair[0].generation, pair[0].created_at, pair[0].copy_id)
        for record, signer in sorted(records, key=key, reverse=True):
            try:
                raw = copy.unb64(self.backups._job(KIND, {**params, "operation": "bundle", "copy_id": record.copy_id}))
                _, refs = copy.open_bundle(raw, record, signer, recipient)
                point = self.backups._job(KIND, {**params, "operation": "check", "copy_id": record.copy_id,
                                                "recovery_key": password, "generation": record.generation,
                                                "repository": record.repository, "snapshots": record.snapshots,
                                                "run_id": record.run_id})
                units, backed_up = snapshot_evidence(point)
                if units != [unit.model_dump() for unit in refs.units] or backed_up != record.backed_up_at:
                    raise copy.CopyRefused("repository snapshots do not match the verified bundle")
                return record, refused
            except (AgentError, *copy.INVALID_COPY):
                refused += 1
        return None, refused
