# SPDX-License-Identifier: Apache-2.0
"""Response models published in /openapi.json for the catalog (contract §3 and §11.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .ai_policy import policy_label


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
    reason: str | None = Field(
        default=None,
        description="Why the scan failed (CRITICAL fixable CVEs, secrets, malware, smoke) from scan.json's own "
        "counts, so the owner can see why an app is blocked; null on a pass",
    )


class CatalogSource(BaseModel):
    """§12.22: the community source an app comes from, pinned to a commit."""

    id: str
    name: str
    commit: str


class AppBuild(BaseModel):
    """metadata.build: OneMind rebuilt this app's image (sdk/tools/app-factory); upstream did not publish it."""

    builder: str
    revision: int = Field(description="OneMind rebuild number for this upstream release")
    upstream_tag: str = Field(description="The upstream release this image was built from")
    base: str = Field(description="The upstream image the build started from, pinned by digest")
    patched: list[str] = Field(description="Operating-system packages OneMind upgraded on top of the base")
    built_at: str = Field(description="RFC 3339 time of the build")
    image: str = Field(description="The OneMind-built image the app runs, pinned by digest")


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
    browser: bool = Field(default=False, description="A browser app (#692): open it with POST /v1/browsers/{app_id}/session, "
                          "which gives the person their own profile; its own app name is never served")
    ai_policy: Literal["allowed", "consent-required", "official-mcp-only", "display-only", "prohibited", "unknown"] | None = Field(
        default=None, alias="aiPolicy",
        description="#165: may this app's data go to an AI. null when the manifest declares none: agents see the "
        "catalog entry, never the app's data. Health and wellness apps default to display-only; unknown is a "
        "declared value the gateway does not know, treated as deny",
    )
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
    build: AppBuild | None = Field(
        default=None, description="Set when OneMind built the image itself; null when the app runs upstream's image"
    )
    catalog_source: CatalogSource | None = Field(
        default=None, description="§12.22: the community source and pinned commit; null for the official catalog"
    )

    @field_validator("ai_policy", mode="before")
    @classmethod
    def _known_ai_policy(cls, value: object) -> str:
        # Runs only when the row carries aiPolicy; a malformed manifest value must not break the list.
        return policy_label(value)
