# SPDX-License-Identifier: Apache-2.0
"""A site's surveyed anchors calibrate its local metre grid to WGS-84."""
from math import fsum
from typing import Annotated, Self

from pydantic import ConfigDict, Field, model_validator
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..jsonbody import JsonBody
from ..ledger import Base
from ..store import FeatureSchema
from ..subjects import position_problems

SCHEMA = FeatureSchema("geo")
FrameId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
# Finite metre coordinates. The generous bound also keeps calibration products finite.
Metres = Annotated[float, Field(strict=True, ge=-40_100_000, le=40_100_000)]


class GeoRecord(JsonBody):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class NamedPlace(GeoRecord):
    id: FrameId
    name: Annotated[str, Field(min_length=1, max_length=128)]


class SiteArea(NamedPlace):
    floor_id: FrameId | None = None


class Anchor(GeoRecord):
    x: Metres
    y: Metres
    lat: Annotated[float, Field(strict=True, ge=-90, le=90)]
    lon: Annotated[float, Field(strict=True, ge=-180, le=180)]

    @model_validator(mode="after")
    def valid_fix(self) -> Self:
        if problems := position_problems({"lat": self.lat, "lon": self.lon}):
            raise ValueError(problems[0])
        return self


def project(anchors: list[Anchor], x: float, y: float) -> tuple[float, float]:
    """Fit an affine map by least squares using *all* surveyed XY control points."""
    n = len(anchors)
    mx, my = (fsum(a.x for a in anchors) / n, fsum(a.y for a in anchors) / n)
    dx, dy = [a.x - mx for a in anchors], [a.y - my for a in anchors]
    def dot(a: list[float], b: list[float]) -> float:
        return fsum(u * v for u, v in zip(a, b, strict=True))
    xx, xy, yy = dot(dx, dx), dot(dx, dy), dot(dy, dy)
    det = xx * yy - xy * xy
    if det <= 1e-12 * (xx + yy) ** 2:
        raise ValueError("the local anchors must span a two-dimensional site")
    def fit(values: list[float]) -> float:
        mean = fsum(values) / n
        centered = [v - mean for v in values]
        xv, yv = dot(dx, centered), dot(dy, centered)
        return mean + ((yy * xv - xy * yv) * (x - mx) + (xx * yv - xy * xv) * (y - my)) / det
    # Unwrap longitudes about the first anchor before fitting across the dateline.
    origin = anchors[0].lon
    lon = fit([(a.lon - origin + 180) % 360 - 180 for a in anchors])
    return fit([a.lat for a in anchors]), (origin + lon + 180) % 360 - 180


_ADDRESS_CHAR = r"[^\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]"
_ADDRESS_VISIBLE = r"[^\s\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]"
ADDRESS_PATTERN = rf"^{_ADDRESS_CHAR}*{_ADDRESS_VISIBLE}{_ADDRESS_CHAR}*$"


class GeoSite(NamedPlace):
    # The owner's own words for where the place is, kept only on this box. The box never looks it up:
    # there is no address index on it, and nothing is sent to an outside service (first run, #1016).
    # One line, no control characters (NUL, newlines, escapes) and no bidirectional overrides that could
    # make the text read differently from what is stored; never blank. Readable by the owner only.
    address: Annotated[str, Field(min_length=1, max_length=256, pattern=ADDRESS_PATTERN)] | None = None
    floors: Annotated[list[NamedPlace], Field(max_length=128)] = []
    areas: Annotated[list[SiteArea], Field(max_length=512)] = []
    anchors: Annotated[list[Anchor], Field(min_length=3, max_length=128)]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        floors = {f.id for f in self.floors}
        if len(floors) != len(self.floors) or len({a.id for a in self.areas}) != len(self.areas):
            raise ValueError("area and floor IDs must each be unique within their site")
        if any(a.floor_id is not None and a.floor_id not in floors for a in self.areas):
            raise ValueError("area refers to an unknown floor")
        project(self.anchors, self.anchors[0].x, self.anchors[0].y)
        return self


class SiteRow(Base):
    """Areas, floors and anchors share the lifetime and coordinate frame of one site."""
    __tablename__ = "geo_sites"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record: Mapped[dict] = mapped_column(JSON)
