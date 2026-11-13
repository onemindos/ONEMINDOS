# SPDX-License-Identifier: Apache-2.0
"""Response models published in /openapi.json for the catalog (contract §3 and §11.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AppLinks(BaseModel):
    """§9.3 metadata.links. Only absolute http(s) URLs are passed through; anything else is null."""

    docs: str | None = None
    github: str | None = None
    website: str | None = None
    support: str | None = None


class ScanSummary(BaseModel):
    """§11.1 apps/<id>/scan.json, reduced to what the catalog shows."""

    scanned_at: str = Field(description="RFC 3339 time of the last scan")
    result: Literal["pass", "fail"]


class CatalogApp(BaseModel):
    """One GET /v1/apps entry: the §3 fields plus links, tier and scan (§11.4)."""

    id: str
    name: str | None
    version: str | None
    description: str | None
    category: str | None
    icon: str | None
    license: str | None
    source: str | None
    archs: list[str]
    requires: dict
    web_port: int | None
    installed: bool
    status: str = Field(
        description="not_installed | installing | installed | stopped | starting | stopping | restarting | "
        "updating | configuring | removing | deleting_data | failed | unknown"
    )
    data_kept: bool = Field(
        default=False,
        description="True when the app was removed but its data volumes were kept (reinstall picks them up; "
        "app.delete_data erases them)",
    )
    links: AppLinks
    tier: Literal["verified", "community", "blocked"] | None = Field(
        description="Set by the app CI gate (§9.4); null when the manifest has none yet"
    )
    scan: ScanSummary | None = Field(
        description="Last scan, or null when apps/<id>/scan.json is missing or invalid. Install is "
        "refused (409 stale_precondition) unless result is pass and scanned_at is at most 7 days old"
    )
