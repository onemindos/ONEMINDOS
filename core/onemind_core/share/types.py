# SPDX-License-Identifier: Apache-2.0
"""The share type registry and per-object deep links (#612).

A share type names what kind of object one app hands another, like the kinds a phone share sheet
knows. The names are the descriptor enum `$defs/shareType` in sdk/schema/onemind.builtin.schema.json
(test_share.py keeps the two equal), so an app that says `share.accepts: [file]` and this registry
always mean the same thing.

Each type carries the data class (`$defs/dataClass`) its objects belong to. An app may receive an
object only when it holds the grant for that class: its descriptor lists it under `data.owns` or
`data.reads`. A place is location data, so an app without the location grant is never handed one,
even if it says it accepts places.

A deep link names one object in one app: `onemind://<app>/<type>/<ref>`, with the ref
percent-encoded so a file path or an id with slashes stays one path segment. The desktop client
opens these links; the gateway only builds them, it never follows one.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

SCHEME = "onemind"


@dataclass(frozen=True)
class ShareType:
    name: str
    title: str
    data_class: str   # the descriptor data class an app must own or read to receive one
    ref: str          # what the object's ref names, for client authors


TYPES: dict[str, ShareType] = {t.name: t for t in (
    ShareType("note", "Note", "private", "the note id in the app that keeps it"),
    ShareType("task", "Task", "private", "the task id in the app that keeps it"),
    ShareType("event", "Event", "private", "the calendar event id"),
    ShareType("person", "Person", "private", "the contact id"),
    ShareType("file", "File", "private", "a Files location: <root>:<path>, as GET /v1/files/stat names it"),
    ShareType("place", "Place", "location", "the place id in the app that keeps it"),
    ShareType("track", "Track", "location", "the recorded track id"),
    ShareType("alert", "Alert", "owner", "the alert id"),
    ShareType("clip", "Clip", "private", "the clip id (a saved snippet of text, a link or an image)"),
)}

VERBS = ("open", "add")


def holds_grant(spec: dict, share_type: str) -> bool:
    """Whether a descriptor's data grants cover objects of this type."""
    data = spec.get("data") or {}
    granted = set(data.get("owns", [])) | set(data.get("reads", []))
    return TYPES[share_type].data_class in granted


def deep_link(app_id: str, share_type: str, ref: str) -> str:
    """onemind://<app>/<type>/<percent-encoded ref>: one object in one app."""
    return f"{SCHEME}://{app_id}/{share_type}/{quote(ref, safe='')}"

