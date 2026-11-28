# SPDX-License-Identifier: Apache-2.0
"""Desktop apps from Flathub (issue #1097, D-026, D-027): search, install, update, remove and launch.

Debian 13 packages Flatpak, so OneMind builds none of it. The box side is `onemindd host serve`
(internal/flatpak): it drives one Flatpak installation on /data, so the apps survive a reboot and an A/B update,
and writes every app's sandbox (no host files, no home folder, one granted folder). This module is the gateway's
half, and it holds no desired state of its own: Flatpak's installation is the truth, read from the host each time.

Rules this module keeps:
- Installing, updating, removing and launching require owner approval (risk "actuate").
  The request and approval are checked against the host so a stale card is refused.
- The host's list of Flathub apps is read through the gateway, never from the browser, so the dashboard needs no
  new network rule and the box's own remote is the only one used.
- When the host service or Flatpak is missing the routes say `available: false` with the reason; a request is
  refused instead of filed (nothing is approved that could not run).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .actions import FeatureAction
from .auth import Principal
from .context import Gateway
from .errors import ApiError
from .executors import ExecResult
from .jsonbody import JsonBody
from .sections import config_section
from .storage import StorageClient, StorageTimeout, StorageUnavailable

log = logging.getLogger("onemind.desktopapps")
TYPES = {"install": "desktop.app.install", "update": "desktop.app.update", "remove": "desktop.app.remove"}
LAUNCH = "desktop.app.launch"
APP_ID_RE = r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*){2,}$"
STREAM_APP = "desktop-apps"  # the Neko app that streams the session (apps/_bases/desktop, #799)
UNAVAILABLE = ("flatpak_unavailable",
               "This box cannot run desktop apps yet: the host service that drives Flatpak is not reachable.")
SANDBOX = ["no files of the box except one folder of its own", "no home folder", "no way back out to the box"]


@config_section("desktopapps")
@dataclass(frozen=True)
class DesktopAppsSettings:
    host_socket: Path = Path("/run/onemind/host.sock")   # ONEMIND_DESKTOPAPPS_HOST_SOCKET
    host_timeout_s: float = 1200.0                       # ONEMIND_DESKTOPAPPS_HOST_TIMEOUT_S: an install downloads
    read_timeout_s: float = 60.0                         # ONEMIND_DESKTOPAPPS_READ_TIMEOUT_S: search and list

    def validate(self) -> None:
        if not self.host_socket.is_absolute():
            raise ValueError("ONEMIND_DESKTOPAPPS_HOST_SOCKET must be an absolute path")
        if not 1 <= self.host_timeout_s <= 3600 or not 1 <= self.read_timeout_s <= 600:
            raise ValueError("ONEMIND_DESKTOPAPPS_HOST_TIMEOUT_S must be 1-3600 and ..._READ_TIMEOUT_S 1-600")


class FlatpakHostError(Exception):
    """The host refused or could not do it: a stable `reason` and a sentence for the owner."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


class FlatpakHost(Protocol):
    def status(self) -> tuple[bool, str, str, list[dict]]:
        """(available, reason, message, installed apps)."""

    def search(self, q: str) -> list[dict]: ...
    def install(self, app_id: str) -> None: ...
    def update(self, app_id: str) -> None: ...
    def remove(self, app_id: str) -> None: ...
    def launch(self, app_id: str) -> None: ...


class HostFlatpakClient:
    """The real FlatpakHost: JSON over the host service's Unix socket (internal/host/flatpak.go)."""

    def __init__(self, s: DesktopAppsSettings):
        self.read = StorageClient(s.host_socket, s.read_timeout_s)
        self.write = StorageClient(s.host_socket, s.host_timeout_s)

    def _call(self, client: StorageClient, method: str, path: str) -> tuple[int, dict]:
        try:
            status, doc = client.call(method, path)
        except StorageUnavailable:
            raise FlatpakHostError(*UNAVAILABLE) from None
        except StorageTimeout:
            raise FlatpakHostError("host_timeout", "The host service did not answer in time; check the app list before trying again.") from None
        return status, doc if isinstance(doc, dict) else {}

    def _ok(self, status: int, doc: dict) -> dict:
        if status == 200:
            return doc
        if status == 409 and isinstance(doc.get("reason"), str):
            raise FlatpakHostError(doc["reason"], str(doc.get("message") or "The host refused."))
        raise FlatpakHostError("host_error", "The host service could not do it; see the box's journal.")

    def status(self) -> tuple[bool, str, str, list[dict]]:
        try:
            status, doc = self._call(self.read, "GET", "/v1/flatpak")
        except FlatpakHostError as e:
            return False, e.reason, e.message, []
        if status == 200 and doc.get("available") is True:
            return True, "", "", [a for a in doc.get("installed") or [] if isinstance(a, dict)]
        why = doc.get("unavailable_reason") if status == 200 else None
        return False, "flatpak_unavailable", f"This box cannot run desktop apps yet: {why or 'the host service gave no answer.'}", []

    def search(self, q: str) -> list[dict]:
        from urllib.parse import quote
        doc = self._ok(*self._call(self.read, "GET", f"/v1/flatpak/search?q={quote(q, safe='')}"))
        return [a for a in doc.get("results") or [] if isinstance(a, dict)]

    def install(self, app_id: str) -> None:
        self._ok(*self._call(self.write, "POST", f"/v1/flatpak/apps/{app_id}/install"))

    def update(self, app_id: str) -> None:
        self._ok(*self._call(self.write, "POST", f"/v1/flatpak/apps/{app_id}/update"))

    def remove(self, app_id: str) -> None:
        self._ok(*self._call(self.write, "DELETE", f"/v1/flatpak/apps/{app_id}"))

    def launch(self, app_id: str) -> None:
        self._ok(*self._call(self.read, "POST", f"/v1/flatpak/apps/{app_id}/launch"))


class FlathubApp(BaseModel):
    """One app: from the Flathub search, or installed (then `installed`, `update_available` and `folder` are set)."""

    app_id: str
    name: str = ""
    summary: str = ""
    version: str = ""
    installed: bool = False
    update_available: bool = False
    folder: str | None = None


class ServiceInfo(BaseModel):
    available: bool
    reason: str | None = None
    message: str | None = None
    remote: str
    sandbox: list[str]


class StreamInfo(BaseModel):
    app_id: str
    installed: bool


class DesktopAppsView(BaseModel):
    service: ServiceInfo
    installed: list[FlathubApp]
    stream: StreamInfo


class SearchResult(BaseModel):
    results: list[FlathubApp]


class AppParams(JsonBody):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=APP_ID_RE, max_length=255)


class DesktopAppsService:
    def __init__(self, gw: Gateway, host: FlatpakHost | None = None):
        self.gw = gw
        self.host: FlatpakHost = host or HostFlatpakClient(gw.settings.section(DesktopAppsSettings))

    # ---- reads -----------------------------------------------------------------------------
    def stream(self) -> dict:
        st = self.gw.repo.list_app_states().get(STREAM_APP)
        return {"app_id": STREAM_APP, "installed": bool(st and st.status == "installed")}

    def view(self) -> dict:
        ok, reason, message, apps = self.host.status()
        return {"service": {"available": ok, "reason": None if ok else reason, "message": None if ok else message,
                            "remote": "flathub", "sandbox": SANDBOX},
                "installed": apps, "stream": self.stream()}

    def search(self, q: str) -> dict:
        try:
            return {"results": self.host.search(q)}
        except FlatpakHostError as e:
            raise ApiError(409, "policy_refused", e.message, reason=e.reason) from None

    # ---- approvals ------------------------------------------------------------------------
    def refusal(self, kind: str, params: dict) -> tuple[str, str] | None:
        """Why this change cannot be filed or approved now, as (reason, message), or None."""
        ok, reason, message, apps = self.host.status()
        if not ok:
            return reason, message
        have = {a.get("app_id") for a in apps}
        app_id = params["app_id"]
        if kind == "install" and app_id in have:
            return "already_installed", f"{app_id} is already installed."
        if kind != "install" and app_id not in have:
            return "not_installed", f"{app_id} is not installed."
        if kind == "update" and not any(a.get("app_id") == app_id and a.get("update_available") for a in apps):
            return "up_to_date", f"{app_id} has no update."
        return None

    def check_request(self, kind: str):
        def check(params: dict, _: Principal) -> None:
            if (r := self.refusal(kind, params)) is not None:
                raise ApiError(409, "policy_refused", r[1], reason=r[0])
        return check

    def recheck(self, kind: str):
        def check(a) -> str | None:
            r = self.refusal(kind, a.params)
            return r[1] if r else None
        return check

    def runner(self, kind: str):
        done = {"install": "installed, sandboxed to its own folder", "update": "updated",
                "remove": "removed (its folder of files stays)", "launch": "started in the desktop session"}

        def run(a, finish) -> None:
            app_id = a.params["app_id"]
            try:
                getattr(self.host, kind)(app_id)
            except FlatpakHostError as e:
                reason, message = e.reason, e.message
            except Exception as e:  # noqa: BLE001 - an approved action must always end
                log.exception("desktop app %s of %s failed", kind, app_id)
                reason, message = "internal_error", f"The {kind} failed on the gateway ({type(e).__name__}); check the app list."
            else:
                if kind == "launch":
                    self.gw.audit.append("desktopapp.launched", None, a.id, {"app_id": app_id})
                finish(ExecResult("succeeded", f"{app_id} {done[kind]}.", steps=[{"step": f"flatpak {kind}", "app_id": app_id, "result": "ok"}]))
                return
            finish(ExecResult("failed", message, steps=[{"step": f"flatpak {kind}", "app_id": app_id, "result": reason}]))
        return run

    def register(self) -> None:
        for kind, action in TYPES.items():
            # "actuate": the box downloads and runs software. Owners ask; an agent may ask too; only an owner approves.
            self.gw.actions.register_type(action, FeatureAction(
                "actuate", self.runner(kind), frozenset({"agent"}), check=self.recheck(kind), params_model=AppParams,
                check_request=self.check_request(kind), background=True))
        self.gw.actions.register_type(LAUNCH, FeatureAction(
            "actuate", self.runner("launch"), frozenset(), check=self.recheck("launch"), background=True))
