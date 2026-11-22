# SPDX-License-Identifier: Apache-2.0
"""One current observation per physical asset in a surveyed site."""
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import JSON, BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..errors import ApiError
from ..ledger import Base
from ..store import Database
from ..subjects import position_problems
from .sites import FrameId, GeoRecord, GeoSite, Metres, SiteRow, project

AssetId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")]
# A closed set keeps personal-tracking kinds and reserved subject namespaces out.
AssetKind = Literal["camera", "device", "machine", "sensor", "node", "vehicle", "lora"]


class GeoObservation(GeoRecord):
    kind: AssetKind
    site_id: FrameId
    area_id: FrameId | None = None
    floor_id: FrameId | None = None
    x: Metres
    y: Metres
    z: Metres
    heading_deg: Annotated[float, Field(strict=True, ge=0, lt=360)]
    accuracy_m: Annotated[float, Field(strict=True, ge=0)]
    source: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
    time: AwareDatetime

    @field_validator("time", mode="before")
    @classmethod
    def observation_time(cls, value):
        # AwareDatetime otherwise also coerces epoch numbers and digit strings.
        if not isinstance(value, datetime) and not (isinstance(value, str) and value[10:11].upper() == "T"):
            raise ValueError("time requires an RFC 3339 date-time string with timezone")
        return value


class AssetPosition(GeoObservation):
    asset_id: AssetId
    lat: float
    lon: float
    age_s: float

    def datapoint(self) -> dict:
        return {
            "schema": "onemind.datapoint/v1", "nats_subject": f"onemind.asset.{self.kind}.{self.asset_id}.state",
            "time": self.time.isoformat(), "quality": "unknown", "source": {"kind": "gateway", "id": "geo"},
            "value": {"age_s": self.age_s, "source": self.source, "area_id": self.area_id, "floor_id": self.floor_id},
            "pose": {"frame": self.site_id, "x": self.x, "y": self.y, "z": self.z},
            "position": {"lat": self.lat, "lon": self.lon, "heading_deg": self.heading_deg, "accuracy_m": self.accuracy_m},
        }


class PositionRow(Base):
    __tablename__ = "geo_asset_positions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("geo_sites.id"))
    kind: Mapped[str] = mapped_column(String(32))
    observed_us: Mapped[int] = mapped_column(BigInteger)
    record: Mapped[dict] = mapped_column(JSON)


def observe(db: Database, asset_id: str, body: GeoObservation, now: datetime) -> AssetPosition:
    age_s = (now - body.time).total_seconds()
    if age_s < 0:
        raise ApiError(422, "policy_refused", "Observation time is in the future")
    with db.session.begin() as s:
        row = s.get(SiteRow, body.site_id)
        if row is None:
            raise ApiError(404, "not_found", "Unknown site")
        site = GeoSite.model_validate(row.record)
        if body.floor_id is not None and body.floor_id not in {f.id for f in site.floors}:
            raise ApiError(422, "policy_refused", "Unknown floor in this site")
        if body.area_id is not None:
            area = next((a for a in site.areas if a.id == body.area_id), None)
            if area is None or (body.floor_id and area.floor_id and body.floor_id != area.floor_id):
                raise ApiError(422, "policy_refused", "Area is outside the indicated site or floor")
        lat, lon = project(site.anchors, body.x, body.y)
        if reasons := position_problems({"lat": lat, "lon": lon}):
            raise ApiError(422, "policy_refused", reasons[0])
        pos = AssetPosition(**body.model_dump(), asset_id=asset_id, lat=lat, lon=lon, age_s=age_s)
        delta = body.time - datetime(1970, 1, 1, tzinfo=UTC)
        micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        stmt = db.insert()(PositionRow).values(id=asset_id, kind=body.kind, site_id=body.site_id,
                                               observed_us=micros, record=pos.model_dump(mode="json"))
        updated = s.scalar(stmt.on_conflict_do_update(
            index_elements=["id"], set_={k: getattr(stmt.excluded, k) for k in ("record", "site_id", "observed_us")},
            where=(PositionRow.kind == body.kind) & (PositionRow.observed_us <= micros),
        ).returning(PositionRow.id))
        if updated is None:
            raise ApiError(409, "conflict", "Asset kind changed or a newer position is already stored")
    return pos


def current(db: Database, asset_id: str, now: datetime) -> AssetPosition:
    with db.session() as s:
        row = s.get(PositionRow, asset_id)
        if row is None:
            raise ApiError(404, "not_found", "No position for this asset")
        pos = AssetPosition.model_validate(row.record)
        pos.age_s = max(0.0, (now - pos.time).total_seconds())
        return pos
