# SPDX-License-Identifier: Apache-2.0
"""Verified offline basemap packs on the app's volume. The viewer serves tile bytes."""
from __future__ import annotations

import base64
import hashlib
import os
import shutil
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ..actions import FeatureAction
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Action
from ..sections import config_section

PACK_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
PackID = Annotated[str, Field(pattern=PACK_ID_PATTERN, max_length=64)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
RegionName = Annotated[str, Field(min_length=1, max_length=160)]
PackBytes = Annotated[int, Field(gt=0, le=2**63 - 1)]
PACK_FILE = "archive.pmtiles"
RECORD_FILE = "pack.json"
MAX_REGIONS_BYTES = 512 * 1024
CHUNK_BYTES = 1024 * 1024


@config_section("map")
@dataclass(frozen=True)
class MapSettings:
    # Gateway-side path to the Offline Maps app volume's maps/packs directory.
    packs_dir: Path | None = None
    region_catalog: Path | None = None
    region_key_file: Path = Path("/usr/lib/onemind/keys/map-regions.pub")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AddPack(Record):
    region_id: PackID


class RemovePack(Record):
    pack_id: PackID


class InstalledPack(Record):
    id: PackID
    region: RegionName
    bytes: PackBytes
    sha256: Digest
    installed_at: AwareDatetime


class Packs(Record):
    packs: list[InstalledPack]
    # None when this box has no map packs volume configured (Offline Maps is not set up): there is
    # no disk to measure, and an empty list is the truthful answer, not a server fault.
    free_bytes: int | None = Field(ge=0)


class Region(Record):
    id: PackID
    region: RegionName
    bytes: PackBytes
    sha256: Digest
    url: str = Field(max_length=4096)

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        if any(ord(c) <= 32 or ord(c) >= 127 for c in value) or "\\" in value:
            raise ValueError("invalid region URL")
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username is not None or url.fragment:
            raise ValueError("region URL must be HTTPS without credentials or fragments")
        if url.port not in (None, 443):
            raise ValueError("region URL must use the HTTPS port")
        return value


class RegionCatalog(Record):
    format: Literal["onemind.map.regions/v1"] = Field(alias="schema")
    regions: list[Region] = Field(max_length=4096)


def _limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file is too large")
    return data


def _load_catalog(path: Path, key_path: Path) -> dict[str, Region]:
    key = serialization.load_pem_public_key(_limited(key_path, 4096))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("map region catalogue requires an Ed25519 public key")
    data = _limited(path, MAX_REGIONS_BYTES)
    sig = base64.b64decode(_limited(path.with_name(path.name + ".sig"), 512).strip(), validate=True)
    key.verify(sig, data)
    regions = RegionCatalog.model_validate_json(data).regions
    indexed = {region.id: region for region in regions}
    if len(indexed) != len(regions):
        raise ValueError("duplicate map region ids")
    return indexed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_download(region: Region):
    # Only the verified catalog supplies this URL. Use default TLS verification, no environment
    # proxies, and no redirects to unsigned targets.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(region.url, headers={"User-Agent": "onemind-map-packs"})
    return opener.open(request, timeout=30)


class MapPacks:
    def __init__(self, gateway: Gateway, settings: MapSettings):
        self.gateway, self.settings = gateway, settings
        self._mutations = threading.Lock()
        for kind, params, request_check, approve_check, run in (
            ("map.pack.add", AddPack, self._request_add, self._check_add, self._add),
            ("map.pack.remove", RemovePack, self._request_remove, self._check_remove, self._remove),
        ):
            gateway.actions.register_type(kind, FeatureAction(
                "write", run, frozenset({"person", "agent"}), check=approve_check,
                params_model=params, check_request=request_check, background=True,
            ))

    def _root(self) -> Path:
        path = self.settings.packs_dir
        if path is None:
            # A box without the Offline Maps volume is a state the owner can change (install and
            # provision the app), not a server fault: a request to add or remove a pack conflicts with it.
            raise ApiError(409, "conflict", "Offline Maps is not set up on this box: no map packs volume is configured",
                           reason="map_storage_not_configured")
        if path.is_symlink() or not path.is_dir():
            # Configured but missing: the volume did not mount, which is a real fault on this box.
            raise ApiError(503, "unavailable", "The map packs volume is not mounted", reason="map_storage_unavailable")
        return path

    @staticmethod
    def _usage(root: Path):
        try:
            return shutil.disk_usage(root)
        except OSError:
            raise ApiError(503, "unavailable", "The map packs volume could not be read",
                           reason="map_storage_unavailable") from None

    def _catalog(self) -> dict[str, Region]:
        path, key = self.settings.region_catalog, self.settings.region_key_file
        if path is None or not os.path.lexists(path) or not os.path.lexists(key):
            # A fresh box ships no signed region catalogue or key until the owner provisions them:
            # not set up is a state the owner can change, so adding a pack is a 409 with a reason.
            # Installed packs stay listable and removable, which never needs the catalogue.
            raise ApiError(409, "conflict", "Offline map regions are not set up on this box: "
                           "no signed region catalogue and key are installed", reason="map_catalog_not_configured")
        try:
            return _load_catalog(path, key)
        except (OSError, ValueError, InvalidSignature, UnsupportedAlgorithm, RecursionError):
            raise ApiError(503, "unavailable", "No verified map region catalog is available",
                           reason="map_catalog_unavailable") from None

    def _region(self, region_id: str) -> Region:
        region = self._catalog().get(region_id)
        if region is None:
            raise ApiError(404, "not_found", "Map region not found")
        return region

    @staticmethod
    def _installed(folder: Path) -> InstalledPack | None:
        try:
            archive = folder / PACK_FILE
            record = folder / RECORD_FILE
            if folder.is_symlink() or archive.is_symlink() or record.is_symlink():
                return None
            pack = InstalledPack.model_validate_json(_limited(record, 4096))
            if pack.id == folder.name and archive.is_file() and archive.stat().st_size == pack.bytes:
                return pack
        except (OSError, ValueError, RecursionError):
            return None
        return None

    def list(self) -> Packs:
        if self.settings.packs_dir is None:
            return Packs(packs=[], free_bytes=None)
        root = self._root()
        try:
            packs = [pack for folder in sorted(root.iterdir()) if not folder.name.startswith(".")
                     if (pack := self._installed(folder)) is not None]
        except OSError:
            raise ApiError(503, "unavailable", "The map packs volume could not be read",
                           reason="map_storage_unavailable") from None
        return Packs(packs=packs, free_bytes=self._usage(root).free)

    def _add_plan(self, region_id: str) -> tuple[Path, Region]:
        root = self._root()
        region = self._region(region_id)
        target = root / region.id
        if target.exists() or target.is_symlink():
            raise ApiError(409, "conflict", "That map pack is already installed", reason="map_pack_exists")
        usage = self._usage(root)
        reserve = (usage.total + 9) // 10
        if region.bytes > usage.free - reserve:
            raise ApiError(409, "conflict", "Installing this map pack would leave less than 10% free disk",
                           reason="map_disk_reserve")
        return root, region

    def _remove_plan(self, pack_id: str) -> tuple[Path, InstalledPack]:
        root = self._root()
        # Action params are checked against the strict identifier model before reaching here.
        installed = self._installed(root / pack_id)
        if installed is None:
            raise ApiError(404, "not_found", "Map pack not found")
        return root, installed

    def _request_add(self, params: dict, _: Principal) -> None:
        self._add_plan(params["region_id"])

    def _request_remove(self, params: dict, _: Principal) -> None:
        self._remove_plan(params["pack_id"])

    def _check_add(self, action: Action) -> str | None:
        try:
            self._add_plan(action.params["region_id"])
        except ApiError as exc:
            return str(exc)
        return None

    def _check_remove(self, action: Action) -> str | None:
        try:
            self._remove_plan(action.params["pack_id"])
        except ApiError as exc:
            return str(exc)
        return None

    @staticmethod
    def _download(region: Region, output: Path) -> None:
        seen = 0
        digest = hashlib.sha256()
        with _open_download(region) as response, output.open("xb") as archive:
            while chunk := response.read(CHUNK_BYTES):
                seen += len(chunk)
                if seen > region.bytes:
                    raise ValueError("map pack exceeds its signed size")
                digest.update(chunk)
                archive.write(chunk)
            if seen != region.bytes or digest.hexdigest() != region.sha256:
                raise ValueError("map pack failed its signed length or SHA-256 check")
            archive.flush()
            os.fsync(archive.fileno())

    def _add(self, action: Action, finish: Callable[[ExecResult], None]) -> None:
        with self._mutations:
            try:
                root, region = self._add_plan(action.params["region_id"])
                pack = InstalledPack(id=region.id, region=region.region, bytes=region.bytes,
                                     sha256=region.sha256, installed_at=self.gateway.clock())
                with tempfile.TemporaryDirectory(prefix=".map-stage-", dir=root) as stage:
                    staged = Path(stage) / "pack"
                    staged.mkdir()
                    self._download(region, staged / PACK_FILE)
                    (staged / RECORD_FILE).write_text(pack.model_dump_json(), encoding="utf-8")
                    staged.chmod(0o755)
                    for file in (PACK_FILE, RECORD_FILE):
                        (staged / file).chmod(0o644)
                    staged.rename(root / region.id)
            except ApiError as exc:
                finish(ExecResult("failed", str(exc)))
                return
            except (OSError, ValueError):
                finish(ExecResult("failed", "Map pack could not be downloaded and verified"))
                return
            self.gateway.events.publish_event("map", "pack_added", {"pack_id": pack.id, "bytes": pack.bytes},
                                              action_id=action.id)
            finish(ExecResult("succeeded", "Map pack installed"))

    def _remove(self, action: Action, finish: Callable[[ExecResult], None]) -> None:
        with self._mutations:
            try:
                root, pack = self._remove_plan(action.params["pack_id"])
                with tempfile.TemporaryDirectory(prefix=".map-stage-", dir=root) as stage:
                    (root / pack.id).rename(Path(stage) / "removed")
            except ApiError as exc:
                finish(ExecResult("failed", str(exc)))
                return
            except OSError:
                finish(ExecResult("failed", "Map pack could not be removed"))
                return
            self.gateway.events.publish_event("map", "pack_removed", {"pack_id": pack.id, "bytes": pack.bytes},
                                              action_id=action.id)
            finish(ExecResult("succeeded", "Map pack removed"))
