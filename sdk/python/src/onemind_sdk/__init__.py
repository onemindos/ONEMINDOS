# SPDX-License-Identifier: Apache-2.0
"""onemind-sdk: the Python client for the OneMind gateway (docs/leap/dev/SDK.md).

    from onemind_sdk import Client
    om = Client.from_env()                      # ONEMIND_HUB + ONEMIND_TOKEN, or the agent Secret
    a = om.actions.request("app.install", "ntfy")
"""

from ._core import TERMINAL, VERSION
from ._gen.models import Action, AuditRecord, AuditVerify, CatalogApp, Instance, Node
from .client import Client
from .errors import (
    AmbiguousResult, Conflict, Expired, NetworkError, NotFound, OneMindError, OutcomeUnknown, PermissionDenied,
    RateLimited, StalePrecondition, Unauthenticated, UnexpectedResponse,
)

__version__ = VERSION
__all__ = [
    "TERMINAL", "Action", "AmbiguousResult", "AuditRecord", "AuditVerify", "CatalogApp", "Client", "Conflict",
    "Expired", "Instance", "NetworkError", "Node", "NotFound", "OneMindError", "OutcomeUnknown", "PermissionDenied",
    "RateLimited", "StalePrecondition", "Unauthenticated", "UnexpectedResponse", "__version__",
]
