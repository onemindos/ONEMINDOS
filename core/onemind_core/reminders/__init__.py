# SPDX-License-Identifier: Apache-2.0
"""Reminders, the proof app of OneMind Sync (D-032, docs/design/SYNC.md).

A reminder belongs to the person who created it. This spike has only the record and the sync routes
(/v1/sync/reminders/...); the REST API, CLI group, MCP read tools and screens come with the app.
onemind.app.yaml is read only once "reminders" is on the signed system apps list.
"""

from __future__ import annotations

from pydantic import AwareDatetime, ConfigDict, Field

from ..jsonbody import JsonBody
from ..sync import SyncApp


class ReminderData(JsonBody):
    """What a client sends for a reminder. The id is the operation's item_id; the gateway sets updated_at."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    due_at: AwareDatetime | None = None
    done: bool = False


SYNC = SyncApp("reminders", ReminderData)
