# SPDX-License-Identifier: Apache-2.0
"""Transfer owner-approved Files uploads into the matching halted machine's CDI volumes."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import ssl
import subprocess
import tempfile
from contextlib import contextmanager

import httpx
from pydantic import BaseModel

from ..auth import Principal
from ..errors import ApiError
from ..files import paths
from ..files.errors import FilesError
from ..files.service import FilesService
from .spec import NAMESPACE, DiskSource, IsoSource, MachineCreateParams, UploadMedia


class UploadedMedia(BaseModel):
    volume: str
    sha256: str
    size_bytes: int


class MachineUploadResult(BaseModel):
    name: str
    media: list[UploadedMedia]


def volumes(p: MachineCreateParams) -> list[tuple[str, UploadMedia]]:
    items = []
    if isinstance(p.source, (DiskSource, IsoSource)):
        suffix = "disk" if isinstance(p.source, DiskSource) else "installer"
        items.append((f"{p.name}-{suffix}", p.source))
    if p.virtio_drivers:
        items.append((f"{p.name}-drivers", p.virtio_drivers))
    return items


def staged(files: FilesService, media: UploadMedia, person_id: str):
    row = files.repo.upload(media.upload_id) if media.upload_id else None
    if not (row and row.state == "done" and row.principal_id == person_id and row.root == f"home:{person_id}"
            and row.length == media.size_bytes and row.sha256 == media.sha256):
        raise ApiError(409, "stale_precondition", "Select a completed upload from your Home with the approved size and SHA-256.",
                       reason="media_changed")
    return row


@contextmanager
def verified_file(files: FilesService, media: UploadMedia, owner: Principal):
    row = staged(files, media, owner.id)
    path = paths.join(paths.split_path(row.dir_path) + (row.name,))
    # Home entries can be overwritten after approval. Hash a private copy on the Files data disk
    # before giving CDI any bytes. Limit the copy even if the source grows while it is being read.
    changed = ApiError(409, "stale_precondition", "The media changed since the request was filed.", reason="media_changed")
    free = files.free_bytes()
    if free is None or free - media.size_bytes < files.settings.min_free_bytes:
        raise ApiError(413, "payload_too_large", "The data disk needs room for a verified copy of this media.", reason="insufficient_space")
    try:
        with files.open_file(owner, row.root, path) as (fd, st, _), tempfile.TemporaryFile(dir=files.settings.root) as copy:
            if st.st_size != media.size_bytes:
                raise changed
            digest, left = hashlib.sha256(), media.size_bytes
            while left:
                chunk = os.read(fd, min(left, 1024 * 1024))
                if not chunk:
                    raise changed
                digest.update(chunk)
                copy.write(chunk)
                left -= len(chunk)
            if os.read(fd, 1) or digest.hexdigest() != media.sha256:
                raise changed
            copy.seek(0)
            yield copy
    except FilesError as exc:
        raise changed from exc
    except OSError as exc:
        raise ApiError(503, "unavailable", "The hub could not read or stage this media. Check the data disk's free space.") from exc


class CDIUpload:
    def __init__(self, kubectl: str):
        self.kubectl = kubectl

    def _object(self, namespace: str, *args: str, body=None) -> dict:
        try:
            proc = subprocess.run([self.kubectl, "-n", namespace, *args, "-o", "json"], input=json.dumps(body) if body else None,
                                  text=True, capture_output=True, check=True, timeout=30)
            result = json.loads(proc.stdout)
            if isinstance(result, dict):
                return result
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        raise ApiError(503, "unavailable", "The hub could not reach the Machines extension. Retry once it is ready.")

    def phase(self, name: str, action_id: str, volume: str, digest: str, *, authorize: bool = False) -> str:
        vm = self._object(NAMESPACE, "get", "virtualmachine", name)
        dv = self._object(NAMESPACE, "get", "datavolume", volume)
        pvc = self._object(NAMESPACE, "get", "persistentvolumeclaim", volume)
        meta = vm.get("metadata", {})
        dv_meta = dv.get("metadata", {})
        if not (meta.get("uid") and meta.get("labels", {}).get("onemind.io/create-action") == action_id
                and vm.get("spec", {}).get("runStrategy") == "Halted"
                and dv.get("spec", {}).get("source", {}).get("upload") == {}
                and volume in [v.get("dataVolume", {}).get("name") for v in vm.get("spec", {}).get("template", {}).get("spec", {}).get("volumes", [])]
                and any(ref.get("kind") == "VirtualMachine" and ref.get("uid") == meta["uid"] and ref.get("controller")
                        for ref in dv_meta.get("ownerReferences", []))
                and dv_meta.get("uid") and any(ref.get("kind") == "DataVolume" and ref.get("uid") == dv_meta["uid"] and ref.get("controller")
                                               for ref in pvc.get("metadata", {}).get("ownerReferences", []))):
            raise ApiError(409, "stale_precondition", "The cluster volume no longer belongs to this approved machine.")
        # CDI may use a volume populator with a different underlying claim. The token endpoint
        # takes the target PVC name, as virtctl does; CDI resolves the upload pod for that claim.
        phase = dv.get("status", {}).get("phase", "")
        annotation = "onemind.io/verified-upload"
        receipt = f"{action_id}/{digest}"
        if phase == "Succeeded" and dv_meta.get("annotations", {}).get(annotation) != receipt:
            raise ApiError(409, "stale_precondition", "CDI populated the volume without a matching verified transfer from this gateway.")
        if authorize and phase == "UploadReady":
            # Bind the verified stream to this generation before sending. A lost proxy response
            # is recoverable from CDI's Succeeded phase without accepting an unrelated volume.
            patch = {"metadata": {"uid": dv_meta["uid"], "resourceVersion": dv_meta["resourceVersion"], "annotations": {annotation: receipt}}}
            self._object(NAMESPACE, "patch", "datavolume", volume, "--type=merge", "-p", json.dumps(patch))
        return phase

    def send(self, volume: str, stream, size: int) -> None:
        ca = self._object("cdi", "get", "configmap", "cdi-uploadproxy-signer-bundle")
        svc = self._object("cdi", "get", "service", "cdi-uploadproxy")
        token = self._object(NAMESPACE, "create", "-f", "-", body={
            "apiVersion": "upload.cdi.kubevirt.io/v1beta1", "kind": "UploadTokenRequest",
            "metadata": {"namespace": NAMESPACE, "generateName": "onemind-upload-"}, "spec": {"pvcName": volume},
        })
        try:
            addr = ipaddress.ip_address(svc["spec"]["clusterIP"])
            host = f"[{addr}]" if addr.version == 6 else str(addr)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cadata=ca["data"]["ca-bundle.crt"])
            bearer = token["status"]["token"]
            if not isinstance(bearer, str) or not bearer:
                raise ValueError("missing upload token")
            # The gateway is a host service. Reach CDI by its ClusterIP, validating its service
            # certificate against the dedicated signer. Never follow a redirect with a bearer.
            with httpx.Client(verify=context, trust_env=False, timeout=300) as client:
                reply = client.post(f"https://{host}/v1beta1/upload",
                                    content=iter(lambda: stream.read(1024 * 1024), b""),
                                    headers={"Authorization": f"Bearer {bearer}", "Content-Length": str(size),
                                             "Content-Type": "application/octet-stream", "Host": "cdi-uploadproxy.cdi.svc"},
                                    extensions={"sni_hostname": "cdi-uploadproxy.cdi.svc"})
                reply.raise_for_status()
        except (KeyError, TypeError, ValueError, ssl.SSLError, httpx.HTTPError):
            raise ApiError(503, "unavailable", "The CDI upload proxy could not confirm the transfer. Retry to check its status.") from None
