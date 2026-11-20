# SPDX-License-Identifier: Apache-2.0
"""Plugin principal with an immutable action-type grant snapshot (DEV-PLG-3).

Only a trusted credential resolver may supply approved grants. This module does
not issue credentials; HTTP authentication separately checks installed source and grants.
"""
from dataclasses import dataclass
import re

from ..auth import Principal
from .auth import plugin_app_id

_ACTION_TYPE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")


@dataclass(frozen=True)
class PluginPrincipal(Principal):
    action_types: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.kind != "plugin" or self.role != "plugin" or plugin_app_id(self.id) is None:
            raise ValueError("plugin principal needs kind/role plugin and a bound app id")
        grants = frozenset(self.action_types)
        if any(not isinstance(t, str) or _ACTION_TYPE.fullmatch(t) is None for t in grants):
            raise ValueError("plugin requests require exact action types, never wildcards")
        object.__setattr__(self, "action_types", grants)

    @property
    def can_request_actions(self) -> bool:
        return bool(self.action_types)

    def may_request_action(self, action_type: str) -> bool:
        return action_type in self.action_types
