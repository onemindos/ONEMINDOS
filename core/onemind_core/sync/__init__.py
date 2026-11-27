# SPDX-License-Identifier: Apache-2.0
"""OneMind Sync (F1, docs/design/SYNC.md): one record-sync contract that every OneMind app uses offline.

Importing this package registers the "sync_changes" and "sync_receipts" tables and the "sync" schema
chain. log.py holds the change log, the push rule (idempotency keys, conflict copies) and the feed;
an app plugs in with one SyncApp (its id and its record model), see reminders/.
"""

from .log import CURSOR_RE, ITEM_RE, KEY_RE, PUSH_MAX, SCHEMA, SyncApp, SyncLog

__all__ = ["CURSOR_RE", "ITEM_RE", "KEY_RE", "PUSH_MAX", "SCHEMA", "SyncApp", "SyncLog"]
