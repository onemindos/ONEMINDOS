# SPDX-License-Identifier: Apache-2.0
"""Browser downloads held in quarantine (#693; files/downloads.py has the model).

- GET    /v1/files/downloads                     held downloads: a person sees their own, an owner all
- POST   /v1/files/downloads/{id}/release        an owner files files.download.release; the file moves
                                                 to the person's Files only after an owner approves it
- DELETE /v1/files/downloads/{id}                discard a held download (the person who downloaded it, or an owner)

The quarantine worker starts with the gateway. Runs after routers/files.py, whose FilesService it shares.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..files.downloads import RELEASE_ACTION, DownloadSettings, Downloads

ORDER = 301  # after files (300): it reads app.state.files
RELEASE_TTL = timedelta(days=7)
TAG = ["files"]


class ReleaseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    download_id: str = Field(pattern=r"^dl_[0-9a-f]{24}$")
    verdict: Literal["infected", "name", "executable", "archive", "unscanned", "clean"]


class HeldDownload(BaseModel):
    id: str
    name: str = Field(description="The file name it gets in Files (a name Files refuses was replaced)")
    size: int
    sha256: str
    verdict: str = Field(description="Why it is held: infected | name | executable | archive | unscanned; "
                                     "clean = it passed and waits for room in Files")
    reason: str
    received_at: str
    state: Literal["held", "waiting_for_space"]
    person_id: str | None = Field(default=None, description="Who downloaded it (owners only)")


class HeldDownloads(BaseModel):
    items: list[HeldDownload]


def register(app: FastAPI, gw: Gateway) -> None:
    downloads = Downloads(app.state.files, gw.settings.section(DownloadSettings))
    app.state.downloads = downloads
    gw.actions.register_type(RELEASE_ACTION, FeatureAction(
        risk="sensitive", run=downloads.run_release, check=downloads.check_release, params_model=ReleaseParams,
        # Releasing a file ClamAV flagged is a destructive-risk approval (hold to approve).
        risk_for=lambda params: "destructive" if params.get("verdict") == "infected" else "sensitive",
    ))
    gw.on_startup(downloads.start)
    gw.on_shutdown(downloads.stop)
    principal = gw.principal

    @app.get("/v1/files/downloads", operation_id="files.downloads.list", tags=TAG, response_model=HeldDownloads,
             responses=error_responses(401, 503))
    def list_downloads(p: Principal = Depends(principal)):
        """Downloads held in quarantine. Nothing listed here is in Files or has been opened."""
        return {"items": downloads.list(p)}

    @app.post("/v1/files/downloads/{download_id}/release", operation_id="files.downloads.release", tags=TAG,
              status_code=202, response_model=Action, responses=error_responses(401, 403, 404, 409))
    def release(download_id: str, p: Principal = Depends(principal)):
        """Ask to move a held download into its person's Files. Nothing moves until an owner approves it."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "release a held download", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may ask to release a held download")
        rec = downloads.get(p, download_id)
        action, _ = gw.actions.request_feature(
            p, RELEASE_ACTION, {"download_id": rec.id, "verdict": rec.verdict},
            idempotency_key=f"download-release-{uuid.uuid4().hex}", expires_at=gw.clock() + RELEASE_TTL,
            reason=f"release held download {rec.name}")
        return JSONResponse(status_code=202, content=action)

    @app.delete("/v1/files/downloads/{download_id}", operation_id="files.downloads.discard", tags=TAG,
                responses=error_responses(401, 403, 404))
    def discard(download_id: str, p: Principal = Depends(principal)):
        """Delete a held download for good. It never reaches Files."""
        return downloads.discard(p, download_id)
