# SPDX-License-Identifier: Apache-2.0
"""Share links (FILES-02, #237): /v1/files/shares for the household, /v1/share/... for outsiders.

An owner or adult requests a link for files or photos with an expiry and optional password.
The answer carries the secret once. After owner approval, someone outside the household opens
`/v1/share/<secret>` without an account:
the item list, then each item by index. The rules are in files/shares.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, Path, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import ErrorBody
from ..files import errors as ferrors
from ..files.errors import FilesError
from ..files.service import REQUEST_TTL
from ..files.shares import MAX_ITEMS
from ..identity.scopes import register_route_scope
from .files import Root, file_response

TAG = ["files"]
ORDER = 305  # after files (300)

# Creating, listing and revoking links needs files:share (owner: every scope; adult: role default).
# A scoped API token without it cannot publish household files. The /v1/share routes take no
# principal at all: the link secret in the path is the only credential.
register_route_scope("GET,HEAD,POST", r"/v1/files/shares", ("files:share",))
register_route_scope("DELETE", r"/v1/files/shares/[^/]+", ("files:share",))
# Only the link-secret shape (TOKEN below) is anonymous: a looser pattern would also match the share sheet's
# /v1/share/types and /targets (routers/share.py) and, registered later, override their apps:read scope.
register_route_scope("GET,HEAD", r"/v1/share/oms_[A-Za-z0-9_-]{43}(/items/[0-9]+)?", None)

SHARE_ID = r"^shl_[0-9A-Z]{26}$"
TOKEN = r"^oms_[A-Za-z0-9_-]{43}$"

_ERR = {
    401: {"description": "Not signed in; on /v1/share: the link's password is missing or wrong (unauthenticated)"},
    403: {"description": "Only an owner or adult shares, and only what they can read (permission_denied)"},
    404: {"description": "No such link, file, photo or item (not_found)"},
    409: {"description": "Not a regular file (conflict)"},
    410: {"description": "The link expired, was revoked, or its creator can no longer share (expired)"},
    422: {"description": "Invalid body, expiry or photo hash (conflict)"},
    429: {"description": "Too many pending requests or live links for this person (rate_limited)"},
    503: {"description": "The files storage is not usable (unavailable)"},
}


def errs(*codes: int) -> dict:
    """OpenAPI `responses=` entries: every error body is the one ErrorBody (FilesError.body() is that shape)."""
    return {c: {"model": ErrorBody, **_ERR[c]} for c in codes}


class _ShareItem(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShareFileItem(_ShareItem):
    root: Root
    path: str = Field(min_length=1, max_length=4096)


class SharePhotoItem(_ShareItem):
    photo: str = Field(max_length=71, description="A photo in your library, by content: sha256:<hex>",
                       json_schema_extra={"pattern": r"^sha256:[0-9a-f]{64}$"})


class ShareBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=120)
    items: list[ShareFileItem | SharePhotoItem] = Field(min_length=1, max_length=MAX_ITEMS)
    expires_at: AwareDatetime = Field(description="Between 5 minutes and 30 days from now")
    password: str | None = Field(default=None, min_length=8, max_length=200,
                                 description="Optional; stored only as a hash")


SharePassword = Annotated[str | None, Header(alias="OneMind-Share-Password", max_length=200)]
TokenPath = Annotated[str, Path(max_length=60, json_schema_extra={"pattern": TOKEN})]
NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}


def register(app: FastAPI, gw: Gateway) -> None:
    svc = app.state.files_service
    shares = svc.shares
    principal = gw.principal
    app.add_exception_handler(FilesError, ferrors.handle)

    @app.post("/v1/files/shares", operation_id="files.shares.create", tags=TAG, status_code=202,
              responses=errs(401, 403, 404, 409, 422, 429, 503))
    def create_share(request: Request, body: ShareBody, p: Principal = Depends(principal)):
        """Request a public link. The secret is returned once and works only after owner approval."""
        items = [i.model_dump() for i in body.items]
        params, secret = shares.prepare(p, body.name, items, body.expires_at, body.password)
        plan = {"summary": f"Publish {len(items)} item(s) outside the household until {params['expires_at']}",
                "items": [{"path": i["path"]} if i.get("root") == "shared" else {"kind": i["kind"], "hidden": True}
                          for i in params["items"]],
                "password": params["password_hash"] is not None}
        out, _ = svc.create_request(p, "files.shares.create", params,
                                    expires_at=min(body.expires_at, svc.clock() + REQUEST_TTL),
                                    plan_and_risk=(plan, "sensitive"))
        base = (gw.settings.public_url or str(request.base_url)).rstrip("/")
        out["one_time"] = {**secret, "url": base + secret["path"]}
        return JSONResponse(out, status_code=202, headers={"Location": f"/v1/files/requests/{out['id']}", **NO_STORE})

    @app.get("/v1/files/shares", operation_id="files.shares.list", tags=TAG, responses=errs(401))
    def list_shares(p: Principal = Depends(principal)):
        """Your links, without their secrets. An owner also sees everyone else's, but not the paths,
        photos or names behind items from that person's Home or photo library."""
        return shares.list(p)

    @app.delete("/v1/files/shares/{share_id}", operation_id="files.shares.revoke", tags=TAG, status_code=202,
                responses=errs(401, 404, 429))
    def revoke_share(share_id: Annotated[str, Path(max_length=40, json_schema_extra={"pattern": SHARE_ID})],
                     p: Principal = Depends(principal)):
        """Request to end a link. The creator or an owner can ask, and only an owner can approve."""
        shares.require_visible(p, share_id)
        out, _ = svc.create_request(p, "files.shares.revoke", {"share_id": share_id},
                                    plan_and_risk=({"summary": f"End public share link {share_id}"}, "write"))
        return JSONResponse(out, status_code=202, headers={"Location": f"/v1/files/requests/{out['id']}"})

    @app.get("/v1/share/{token}", operation_id="share.open", tags=["share"], responses=errs(401, 404, 410))
    def open_share(token: TokenPath, password: SharePassword = None):
        """No account: the link secret is the credential. The items the link shares, by index."""
        return JSONResponse(shares.describe(token, password), headers=NO_STORE)

    @app.get("/v1/share/{token}/items/{index}", operation_id="share.download", tags=["share"],
             responses={206: {"description": "Partial content (Range)"}, **errs(401, 404, 410)})
    def download_share_item(request: Request, token: TokenPath, index: Annotated[int, Path(ge=0, lt=MAX_ITEMS)],
                            password: SharePassword = None, inline: bool = False):
        """One shared item's bytes, read with the creator's current rights."""
        res = file_response(request, shares.open_download(token, password, index), inline, cache="no-store")
        res.headers.update({k: v for k, v in NO_STORE.items() if k != "Cache-Control"})
        return res
