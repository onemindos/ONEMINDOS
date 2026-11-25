# SPDX-License-Identifier: Apache-2.0
"""A narrow app surface over the standard gateway client."""
from collections.abc import Mapping
from datetime import timedelta
from typing import NotRequired, TypedDict
from urllib.parse import urlencode

from onemind_sdk._core import Req
from onemind_sdk._gen.models import Action, SendIn, SeriesPoint
from onemind_sdk.client import Client


class AppDeclarations(TypedDict):
    tools: NotRequired[list[dict]]
    search: NotRequired[dict]
    notifications: NotRequired[list[dict]]
    layers: NotRequired[list[dict]]
    settings: NotRequired[dict]


def define_app(declarations: AppDeclarations) -> AppDeclarations:
    return declarations


class AppClient:
    def __init__(self, gateway: Client, own_secrets: Mapping[str, str] | None = None):
        self.__gateway = gateway
        self.__secrets = own_secrets if own_secrets is not None else {}

    def request_action(self, kind: str, app_id: str, *, expires_in: timedelta | None = None,
                       idempotency_key: str | None = None) -> Action:
        return self.__gateway.actions.request(kind, app_id, expires_in=expires_in, idempotency_key=idempotency_key)

    def file_roots(self) -> object:
        return self.__gateway.call(Req("GET", "/v1/files/roots", retry=True))

    def notify(self, body: SendIn) -> object:
        return self.__gateway.call(Req("POST", "/v1/notifications/send", body=body.model_dump(mode="json", exclude_none=True)))

    def series(self, **query: str | int) -> list[SeriesPoint]:
        values = self.__gateway.call(Req("GET", "/v1/series?" + urlencode(query), retry=True))
        return [SeriesPoint.model_validate(item) for item in values]

    def own_secret(self, name: str) -> str | None:
        return self.__secrets.get(name)
